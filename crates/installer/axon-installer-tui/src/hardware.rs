use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HardwareReport {
    pub cpu_model: String,
    pub cpu_cores: usize,
    pub has_virtualization: bool,
    pub total_ram_mb: u64,
    pub is_uefi: bool,
    pub secure_boot: bool,
    pub has_tpm2: bool,
    pub network_interfaces: Vec<String>,
    pub storage_devices_found: usize,
    pub meets_minimum_requirements: bool,
    pub warnings: Vec<String>,
}

impl HardwareReport {
    pub fn probe() -> Self {
        let (cpu_model, cpu_cores, has_virtualization) = probe_cpu();
        let total_ram_mb = probe_ram();
        let is_uefi = Path::new("/sys/firmware/efi").exists();
        let secure_boot = probe_secure_boot();
        let has_tpm2 = Path::new("/dev/tpm0").exists() || Path::new("/dev/tpmrm0").exists() || Path::new("/sys/class/tpm/tpm0").exists();
        let network_interfaces = probe_network();
        let storage_devices_found = probe_storage_count();

        let mut warnings = Vec::new();
        let mut meets_minimum = true;

        if total_ram_mb < 1800 {
            warnings.push("RAM is under recommended 2 GB minimum.".into());
            meets_minimum = false;
        } else if total_ram_mb < 3800 {
            warnings.push("RAM is under 4 GB: Minimal/Developer profile recommended over Full Desktop.".into());
        }

        if !is_uefi {
            warnings.push("System booted in legacy BIOS mode. MyelinOS requires UEFI for GPT ESP boot.".into());
        }

        if !has_tpm2 {
            warnings.push("TPM 2.0 device not detected: Hardware measured-boot protection unavailable.".into());
        }

        if storage_devices_found == 0 {
            warnings.push("No writable hard disk or SSD detected for installation.".into());
            meets_minimum = false;
        }

        Self {
            cpu_model,
            cpu_cores,
            has_virtualization,
            total_ram_mb,
            is_uefi,
            secure_boot,
            has_tpm2,
            network_interfaces,
            storage_devices_found,
            meets_minimum_requirements: meets_minimum,
            warnings,
        }
    }
}

fn probe_cpu() -> (String, usize, bool) {
    let mut model = "Unknown x86_64 CPU".to_string();
    let mut cores = 1;
    let mut virt = false;

    if let Ok(content) = fs::read_to_string("/proc/cpuinfo") {
        let mut count = 0;
        for line in content.lines() {
            if line.starts_with("model name") {
                if let Some(val) = line.split(':').nth(1) {
                    model = val.trim().to_string();
                }
            } else if line.starts_with("processor") {
                count += 1;
            } else if line.starts_with("flags") {
                if line.contains(" vmx ") || line.contains(" svm ") {
                    virt = true;
                }
            }
        }
        if count > 0 {
            cores = count;
        }
    }

    (model, cores, virt)
}

fn probe_ram() -> u64 {
    if let Ok(content) = fs::read_to_string("/proc/meminfo") {
        for line in content.lines() {
            if line.starts_with("MemTotal:") {
                let parts: Vec<&str> = line.split_whitespace().collect();
                if parts.len() >= 2 {
                    if let Ok(kb) = parts[1].parse::<u64>() {
                        return kb / 1024;
                    }
                }
            }
        }
    }
    1024
}

fn probe_secure_boot() -> bool {
    let efivars = Path::new("/sys/firmware/efi/efivars");
    if efivars.is_dir() {
        if let Ok(entries) = fs::read_dir(efivars) {
            for entry in entries.flatten() {
                let name = entry.file_name();
                let name_str = name.to_string_lossy();
                if name_str.starts_with("SecureBoot-") {
                    if let Ok(data) = fs::read(entry.path()) {
                        // In efivars, the last byte usually holds the boolean status (1 = enabled)
                        if let Some(&last) = data.last() {
                            return last == 1;
                        }
                    }
                }
            }
        }
    }
    false
}

fn probe_network() -> Vec<String> {
    let mut ifaces = Vec::new();
    let net = Path::new("/sys/class/net");
    if let Ok(entries) = fs::read_dir(net) {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if name != "lo" {
                ifaces.push(name);
            }
        }
    }
    ifaces.sort();
    ifaces
}

fn probe_storage_count() -> usize {
    let block = Path::new("/sys/block");
    let mut count = 0;
    if let Ok(entries) = fs::read_dir(block) {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if !name.starts_with("loop") && !name.starts_with("ram") && !name.starts_with("sr") {
                count += 1;
            }
        }
    }
    count
}
