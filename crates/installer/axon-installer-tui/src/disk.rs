use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug, Clone)]
pub struct DiskDevice {
    pub device_name: String,        // e.g. "vda"
    pub device_path: PathBuf,      // e.g. "/dev/vda"
    pub size_gb: f64,              // e.g. 20.0
    pub model: String,             // e.g. "VirtIO Disk"
    pub is_rotational: bool,
    #[allow(dead_code)]
    pub existing_partitions: Vec<String>,
}

impl DiskDevice {
    pub fn scan_disks() -> Vec<DiskDevice> {
        let mut disks = Vec::new();
        let sys_block = Path::new("/sys/block");
        if let Ok(entries) = fs::read_dir(sys_block) {
            for entry in entries.flatten() {
                let name = entry.file_name().to_string_lossy().to_string();
                if name.starts_with("loop") || name.starts_with("ram") || name.starts_with("sr") || name.starts_with("zram") {
                    continue;
                }

                let dev_path = PathBuf::from(format!("/dev/{}", name));
                if !dev_path.exists() {
                    continue;
                }

                // Check if disk is read-only (e.g. installation source media)
                let ro_path = entry.path().join("ro");
                if let Ok(ro_content) = fs::read_to_string(ro_path) {
                    if ro_content.trim() == "1" {
                        // Skip read-only devices from target list
                        continue;
                    }
                }

                // Size in 512-byte sectors
                let mut size_gb = 0.0;
                let size_path = entry.path().join("size");
                if let Ok(content) = fs::read_to_string(size_path) {
                    if let Ok(sectors) = content.trim().parse::<u64>() {
                        let bytes = sectors * 512;
                        size_gb = (bytes as f64) / (1024.0 * 1024.0 * 1024.0);
                    }
                }

                // Model name
                let mut model = "Unknown Drive".to_string();
                let model_path = entry.path().join("device/model");
                if let Ok(content) = fs::read_to_string(model_path) {
                    let trimmed = content.trim();
                    if !trimmed.is_empty() {
                        model = trimmed.to_string();
                    }
                }

                // Rotational flag
                let mut is_rotational = false;
                let rot_path = entry.path().join("queue/rotational");
                if let Ok(content) = fs::read_to_string(rot_path) {
                    is_rotational = content.trim() == "1";
                }

                // Partitions
                let mut existing_partitions = Vec::new();
                if let Ok(sub_entries) = fs::read_dir(entry.path()) {
                    for sub in sub_entries.flatten() {
                        let sub_name = sub.file_name().to_string_lossy().to_string();
                        if sub_name.starts_with(&name) && sub_name != name {
                            existing_partitions.push(format!("/dev/{}", sub_name));
                        }
                    }
                }
                existing_partitions.sort();

                disks.push(DiskDevice {
                    device_name: name,
                    device_path: dev_path,
                    size_gb,
                    model,
                    is_rotational,
                    existing_partitions,
                });
            }
        }
        disks.sort_by(|a, b| a.device_name.cmp(&b.device_name));
        disks
    }

    /// Partitions the target disk into GPT with ESP (512MB) and Rootfs (ext4)
    pub fn partition_and_format(&self) -> Result<(String, String), String> {
        let dev_str = self.device_path.to_string_lossy().to_string();

        // 1. Wipe old signatures with wipefs if available
        let _ = Command::new("wipefs").args(["-a", &dev_str]).output();

        // Determine partition naming prefix: e.g. /dev/vda1 or /dev/nvme0n1p1
        let prefix = if dev_str.chars().last().map(|c| c.is_ascii_digit()).unwrap_or(false) {
            format!("{}p", dev_str)
        } else {
            dev_str.clone()
        };
        let esp_dev = format!("{}1", prefix);
        let root_dev = format!("{}2", prefix);

        // 2. Partition with parted or sfdisk
        let mut partitioned_ok = false;
        if let Ok(out) = Command::new("parted")
            .args([
                "-s", &dev_str,
                "mklabel", "gpt",
                "mkpart", "ESP", "fat32", "1MiB", "513MiB",
                "set", "1", "esp", "on",
                "mkpart", "MYELINOS_ROOT", "btrfs", "513MiB", "100%",
            ])
            .output()
        {
            if out.status.success() {
                partitioned_ok = true;
            }
        }

        if !partitioned_ok {
            // Fallback to sfdisk if parted failed or not found
            let sfdisk_input = "label: gpt\n,512M,U,*\n,,L\n";
            let mut child = Command::new("sfdisk")
                .arg(&dev_str)
                .stdin(std::process::Stdio::piped())
                .stdout(std::process::Stdio::null())
                .stderr(std::process::Stdio::null())
                .spawn()
                .map_err(|e2| format!("Failed to run sfdisk ({})", e2))?;

            if let Some(mut stdin) = child.stdin.take() {
                use std::io::Write;
                let _ = stdin.write_all(sfdisk_input.as_bytes());
            }
            let status = child.wait().map_err(|e| e.to_string())?;
            if !status.success() {
                return Err(format!("sfdisk partition failed on {}", dev_str));
            }
        }

        // Wait a moment for udev to populate partition nodes
        std::thread::sleep(std::time::Duration::from_millis(500));
        let _ = Command::new("partprobe")
            .arg(&dev_str)
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
        std::thread::sleep(std::time::Duration::from_millis(500));

        // 3. Format ESP (FAT32) silently to prevent corrupting TUI
        let vfat_status = Command::new("mkfs.vfat")
            .args(["-F32", "-n", "ESP", &esp_dev])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status()
            .map_err(|e| format!("mkfs.vfat failed: {}", e))?;

        if !vfat_status.success() {
            return Err(format!("Formatting ESP {} failed with status {:?}", esp_dev, vfat_status));
        }

        // 4. Format Root with Btrfs silently (default filesystem per user requirement)
        let btrfs_status = Command::new("mkfs.btrfs")
            .args(["-f", "-L", "MYELINOS_ROOT", &root_dev])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();

        match btrfs_status {
            Ok(status) if status.success() => {},
            _ => {
                // Graceful fallback to ext4 if btrfs tools are unavailable
                let ext4_status = Command::new("mkfs.ext4")
                    .args(["-F", "-E", "nodiscard", "-L", "MYELINOS_ROOT", &root_dev])
                    .stdout(std::process::Stdio::null())
                    .stderr(std::process::Stdio::null())
                    .status()
                    .map_err(|e| format!("Both mkfs.btrfs and mkfs.ext4 failed: {}", e))?;
                if !ext4_status.success() {
                    return Err(format!("Formatting Root {} failed", root_dev));
                }
            }
        }

        Ok((esp_dev, root_dev))
    }
}
