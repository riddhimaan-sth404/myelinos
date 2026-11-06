use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InstallProfile {
    DeveloperMinimal,
    GnomeDesktop,
}

impl InstallProfile {
    pub fn name(&self) -> &'static str {
        match self {
            Self::DeveloperMinimal => "MyelinOS Developer Minimal (Axon CLI + Headless)",
            Self::GnomeDesktop => "MyelinOS Full Desktop (GNOME 50 + Axon + Web/Apps)",
        }
    }

    pub fn description(&self) -> &'static str {
        match self {
            Self::DeveloperMinimal => "Lightweight generation with coreutils, systemd, networking, SSH, and Axon package manager.",
            Self::GnomeDesktop => "Complete desktop workstation with Wayland, Mutter, GNOME 50 suite, Firefox, and Axon GUI integration.",
        }
    }
}

fn discover_and_mount_payload(target_root_dev: &str) -> Option<PathBuf> {
    let source_dir = Path::new("/run/installer/source");
    let _ = fs::create_dir_all(source_dir);

    // Check if already mounted
    if source_dir.join("usr/bin").exists() || source_dir.join("bin").exists() {
        return Some(source_dir.to_path_buf());
    }

    // Check pre-existing candidate locations
    for cand in &[Path::new("/run/live/squashfs"), Path::new("/sysroot")] {
        if cand.join("usr/bin").exists() || cand.join("bin").exists() {
            return Some(cand.to_path_buf());
        }
    }

    // Scan block devices for OS payload
    if let Ok(entries) = fs::read_dir("/sys/block") {
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            if name.starts_with("loop") || name.starts_with("ram") || name.starts_with("zram") {
                continue;
            }

            let dev_path = format!("/dev/{}", name);
            if dev_path == target_root_dev || target_root_dev.starts_with(&dev_path) {
                continue;
            }

            // Try candidate devices (the device itself or partition 1)
            let dev_candidates = [
                format!("/dev/{}", name),
                format!("/dev/{}1", name),
                format!("/dev/{}2", name),
                format!("/dev/{}p1", name),
                format!("/dev/{}p2", name),
            ];

            for dev in &dev_candidates {
                if !Path::new(dev).exists() || dev == target_root_dev {
                    continue;
                }

                // Attempt read-only mount (with noload for ext4 journal bypass)
                let mut mounted = false;
                if let Ok(s) = Command::new("mount")
                    .args(["-o", "ro,noload", dev, source_dir.to_str().unwrap()])
                    .status()
                {
                    if s.success() {
                        mounted = true;
                    }
                }

                if !mounted {
                    if let Ok(s) = Command::new("mount")
                        .args(["-o", "ro", dev, source_dir.to_str().unwrap()])
                        .status()
                    {
                        if s.success() {
                            mounted = true;
                        }
                    }
                }

                if mounted {
                    if source_dir.join("usr").exists() || source_dir.join("bin").exists() {
                        return Some(source_dir.to_path_buf());
                    }
                    let _ = Command::new("umount").arg(source_dir).status();
                }
            }
        }
    }

    None
}

pub fn stage_installation<F>(
    esp_dev: &str,
    root_dev: &str,
    profile: InstallProfile,
    mut progress_cb: F,
) -> Result<(), String>
where
    F: FnMut(&str, u16),
{
    let target_mount = Path::new("/mnt");
    let esp_mount = target_mount.join("boot/efi");

    // 1. Mount target root filesystem
    progress_cb("Mounting target root filesystem (Btrfs)...", 10);
    fs::create_dir_all(target_mount).map_err(|e| e.to_string())?;

    let mount_root = Command::new("mount")
        .args([root_dev, target_mount.to_str().unwrap()])
        .status()
        .map_err(|e| format!("Mounting root partition failed: {}", e))?;
    if !mount_root.success() {
        return Err(format!("mount {} /mnt returned {:?}", root_dev, mount_root));
    }

    // 2. Discover OS payload source
    progress_cb("Locating MyelinOS installation source payload...", 18);
    let payload_source = discover_and_mount_payload(root_dev);

    // 3. Staging base OS payload to target root
    if let Some(ref src_path) = payload_source {
        progress_cb(&format!("Transferring OS packages from {} to Btrfs root...", src_path.display()), 25);
        
        let mut rsync_ok = false;
        let rsync_bin = if Path::new("/sbin/rsync").exists() {
            Some("/sbin/rsync")
        } else if Path::new("/usr/bin/rsync").exists() {
            Some("/usr/bin/rsync")
        } else if Path::new("/bin/rsync").exists() {
            Some("/bin/rsync")
        } else {
            None
        };

        if let Some(rbin) = rsync_bin {
            let rsync_status = Command::new(rbin)
                .args(["-a", "--exclude=/boot/efi/*", &format!("{}/.", src_path.display()), target_mount.to_str().unwrap()])
                .status();
            if let Ok(s) = rsync_status {
                if s.success() {
                    rsync_ok = true;
                }
            }
        }

        if !rsync_ok {
            progress_cb("Copying system root tree to target...", 40);
            let cp_status = Command::new("cp")
                .args(["-a", &format!("{}/.", src_path.display()), target_mount.to_str().unwrap()])
                .status()
                .map_err(|e| format!("cp payload failed: {}", e))?;
            if !cp_status.success() {
                let _ = Command::new("umount").arg(target_mount).status();
                return Err("Failed to copy system files from installation source".into());
            }
        }
    } else {
        // Fallback skeleton
        progress_cb("Creating base filesystem skeleton & CAS store...", 30);
        for dir in &[
            "bin", "sbin", "usr/bin", "usr/sbin", "usr/lib", "usr/lib64", "usr/share",
            "etc/myelin", "var/lib/myelin/store", "var/lib/myelin/generations",
            "var/log", "root", "home", "proc", "sys", "dev", "run", "tmp",
        ] {
            let _ = fs::create_dir_all(target_mount.join(dir));
        }

        if Path::new("/bin/busybox").exists() {
            let _ = fs::copy("/bin/busybox", target_mount.join("bin/busybox"));
        }
        if Path::new("/bin/axon").exists() {
            let _ = fs::copy("/bin/axon", target_mount.join("usr/bin/axon"));
            let _ = Command::new("ln").args(["-sf", "axon", target_mount.join("usr/bin/ax").to_str().unwrap()]).status();
        }
    }

    // 4. Mount target ESP
    progress_cb("Mounting target EFI System Partition (ESP)...", 60);
    fs::create_dir_all(&esp_mount).map_err(|e| e.to_string())?;

    let mount_esp = Command::new("mount")
        .args([esp_dev, esp_mount.to_str().unwrap()])
        .status()
        .map_err(|e| format!("Mounting ESP failed: {}", e))?;
    if !mount_esp.success() {
        let _ = Command::new("umount").arg(target_mount).status();
        return Err(format!("mount {} /mnt/boot/efi returned {:?}", esp_dev, mount_esp));
    }

    let efi_boot_dir = esp_mount.join("EFI/BOOT");
    fs::create_dir_all(&efi_boot_dir).map_err(|e| e.to_string())?;
    fs::create_dir_all(target_mount.join("boot")).map_err(|e| e.to_string())?;

    // 5. Install UEFI Bootloader (BOOTX64.EFI)
    progress_cb("Installing UEFI GRUB 2 bootloader binary (BOOTX64.EFI)...", 70);
    let mut bootloader_installed = false;
    for cand in &[
        "/usr/share/myelin/BOOTX64.EFI",
        "/boot/efi/EFI/BOOT/BOOTX64.EFI",
        "/EFI/BOOT/BOOTX64.EFI",
    ] {
        if Path::new(cand).exists() {
            if let Ok(_) = fs::copy(cand, efi_boot_dir.join("BOOTX64.EFI")) {
                bootloader_installed = true;
                break;
            }
        }
    }
    if !bootloader_installed {
        // Generate with grub2-mkimage if host has it
        let _ = Command::new("grub2-mkimage")
            .args([
                "-O", "x86_64-efi",
                "-o", efi_boot_dir.join("BOOTX64.EFI").to_str().unwrap(),
                "-p", "/EFI/BOOT",
                "part_gpt", "fat", "btrfs", "ext2", "normal", "boot", "linux", "search", "search_label", "configfile", "echo",
            ])
            .status();
    }

    // 6. Install Linux Kernel (vmlinuz)
    progress_cb("Installing Linux 7.2 kernel (vmlinuz) with Btrfs support...", 78);
    let mut kernel_copied = false;
    for kern_cand in &[
        "/usr/share/myelin/vmlinuz",
        "/run/installer/source/boot/vmlinuz",
        "/boot/vmlinuz",
        "/vmlinuz",
    ] {
        if Path::new(kern_cand).exists() {
            let _ = fs::copy(kern_cand, target_mount.join("boot/vmlinuz"));
            let _ = fs::copy(kern_cand, efi_boot_dir.join("vmlinuz"));
            kernel_copied = true;
            break;
        }
    }
    if !kernel_copied {
        // Fallback: copy from target /boot/vmlinuz if payload already contained it
        if target_mount.join("boot/vmlinuz").exists() {
            let _ = fs::copy(target_mount.join("boot/vmlinuz"), efi_boot_dir.join("vmlinuz"));
        }
    }

    // 7. Write UEFI GRUB Configuration
    progress_cb("Configuring UEFI GRUB boot menu...", 84);
    let grub_cfg_content = format!(
        "# MyelinOS Stage 2 Bootloader Configuration\n\
        set default=\"0\"\n\
        set timeout=2\n\
        insmod efi_gop\n\
        insmod font\n\
        insmod gfxterm\n\
        insmod btrfs\n\
        insmod fat\n\
        \n\
        menuentry \"MyelinOS (Btrfs Root - GNOME Desktop)\" {{\n\
            search --no-floppy --label --set=root MYELINOS_ROOT\n\
            if [ -f ($root)/boot/vmlinuz ]; then\n\
                linux ($root)/boot/vmlinuz root={} rootfstype=btrfs rw console=tty0 console=ttyS0 audit=0 selinux=0 enforcing=0 quiet\n\
            else\n\
                search --no-floppy --label --set=esp ESP\n\
                linux ($esp)/EFI/BOOT/vmlinuz root={} rootfstype=btrfs rw console=tty0 console=ttyS0 audit=0 selinux=0 enforcing=0 quiet\n\
            fi\n\
        }}\n\
        \n\
        menuentry \"MyelinOS (SATA / NVMe Fallback - /dev/sda2)\" {{\n\
            search --no-floppy --label --set=esp ESP\n\
            linux ($esp)/EFI/BOOT/vmlinuz root=/dev/sda2 rootfstype=btrfs rw console=tty0 console=ttyS0 audit=0 selinux=0 enforcing=0 quiet\n\
        }}\n\
        \n\
        menuentry \"MyelinOS Stage 2 Setup (Console Recovery)\" {{\n\
            search --no-floppy --label --set=root MYELINOS_ROOT\n\
            linux ($root)/boot/vmlinuz root={} rootfstype=btrfs rw console=tty0 console=ttyS0 audit=0 systemd.unit=rescue.target\n\
        }}\n",
        root_dev, root_dev, root_dev
    );
    let _ = fs::write(efi_boot_dir.join("grub.cfg"), grub_cfg_content);

    // 8. Configure Stage 2 Graphical Installer & System Services
    progress_cb("Configuring Stage 2 Graphical Installer (Libadwaita)...", 88);
    
    // Copy myelin_installer_gui.py
    let dest_gui_bin = target_mount.join("usr/bin/myelin-installer-gui");
    for cand in &[
        "/usr/share/myelin/myelin_installer_gui.py",
        "/run/installer/source/usr/bin/myelin-installer-gui",
    ] {
        if Path::new(cand).exists() {
            let _ = fs::copy(cand, &dest_gui_bin);
            let mut perms = fs::metadata(&dest_gui_bin).unwrap().permissions();
            perms.set_mode(0o755);
            let _ = fs::set_permissions(&dest_gui_bin, perms);
            break;
        }
    }

    // Deploy latest axon package manager and ax symlink
    let dest_axon_bin = target_mount.join("usr/bin/axon");
    for cand in &[
        "/usr/share/myelin/axon",
        "/usr/bin/axon",
    ] {
        if Path::new(cand).exists() {
            let _ = fs::copy(cand, &dest_axon_bin);
            if let Ok(meta) = fs::metadata(&dest_axon_bin) {
                let mut perms = meta.permissions();
                perms.set_mode(0o755);
                let _ = fs::set_permissions(&dest_axon_bin, perms);
            }
            let ax_symlink = target_mount.join("usr/bin/ax");
            let _ = fs::remove_file(&ax_symlink);
            let _ = std::os::unix::fs::symlink("axon", &ax_symlink);
            break;
        }
    }

    // Deploy pre-cached package archives into /var/cache/myelin/packages
    let target_cache_dir = target_mount.join("var/cache/myelin/packages");
    let _ = fs::create_dir_all(&target_cache_dir);
    for cand_cache in &[
        Path::new("/usr/share/myelin/packages"),
        Path::new("/run/installer/medium/packages"),
    ] {
        if cand_cache.exists() {
            if let Ok(entries) = fs::read_dir(cand_cache) {
                for entry in entries.flatten() {
                    let src = entry.path();
                    if src.is_file() {
                        let dest = target_cache_dir.join(src.file_name().unwrap());
                        let _ = fs::copy(&src, &dest);
                    }
                }
            }
        }
    }

    // Ensure Stage 2 GUI launches reliably upon graphical desktop initialization
    let gnome_session = target_mount.join("usr/bin/gnome-session");
    let gnome_session_real = target_mount.join("usr/bin/gnome-session-real");
    if gnome_session.exists() && !gnome_session_real.exists() {
        let _ = fs::rename(&gnome_session, &gnome_session_real);
    }
    let wrapper_script = r#"#!/bin/bash
if [ ! -f /var/lib/myelin/installed ] && [ -x /usr/bin/myelin-installer-gui ]; then
    (
        for i in $(seq 1 60); do
            if [ -S "/run/user/$(id -u)/wayland-0" ]; then break; fi
            sleep 0.5
        done
        sleep 1.5
        export WAYLAND_DISPLAY=wayland-0
        export XDG_RUNTIME_DIR="/run/user/$(id -u)"
        /usr/bin/python3 /usr/bin/myelin-installer-gui >> /tmp/myelin-installer.log 2>&1
    ) &
fi
if [ -x /usr/bin/gnome-session-real ]; then
    exec /usr/bin/gnome-session-real "$@"
else
    exec /usr/bin/gnome-shell --mode=user
fi
"#;
    let _ = fs::write(&gnome_session, wrapper_script);
    if let Ok(meta) = fs::metadata(&gnome_session) {
        let mut perms = meta.permissions();
        perms.set_mode(0o755);
        let _ = fs::set_permissions(&gnome_session, perms);
    }

    // Install XDG desktop autostart entry for Stage 2 GUI
    let autostart_dir = target_mount.join("etc/xdg/autostart");
    let _ = fs::create_dir_all(&autostart_dir);
    let desktop_entry = "\
[Desktop Entry]
Type=Application
Name=MyelinOS Stage 2 Setup
Comment=Configure user accounts, timezone, and complete installation
Exec=/usr/bin/python3 /usr/bin/myelin-installer-gui
Icon=system-software-install
Terminal=false
Categories=System;
X-GNOME-Autostart-enabled=true
";
    let _ = fs::write(autostart_dir.join("org.myelinos.Installer.desktop"), desktop_entry);

    // Also write to user autostart if myelinos user home exists
    let user_autostart = target_mount.join("home/myelinos/.config/autostart");
    if target_mount.join("home/myelinos").exists() {
        let _ = fs::create_dir_all(&user_autostart);
        let _ = fs::write(user_autostart.join("org.myelinos.Installer.desktop"), desktop_entry);
        let _ = Command::new("chown").args(["-R", "1000:1000", target_mount.join("home/myelinos/.config").to_str().unwrap()]).status();
    }

    // Ensure Axon CAS, log, and myelin configuration dirs are writable by primary user
    let _ = Command::new("chmod").args(["-R", "777", target_mount.join("var/lib/myelin").to_str().unwrap()]).status();
    let _ = Command::new("chmod").args(["-R", "777", target_mount.join("etc/myelin").to_str().unwrap()]).status();
    let _ = Command::new("chmod").args(["-R", "777", target_mount.join("var/log").to_str().unwrap()]).status();
    let _ = Command::new("chown").args(["-R", "1000:1000", target_mount.join("var/lib/myelin").to_str().unwrap()]).status();
    let _ = Command::new("chown").args(["-R", "1000:1000", target_mount.join("etc/myelin").to_str().unwrap()]).status();
    let _ = Command::new("chown").args(["-R", "1000:1000", target_mount.join("var/lib/myelin").to_str().unwrap()]).status();
    let _ = Command::new("chown").args(["-R", "1000:1000", target_mount.join("etc/myelin").to_str().unwrap()]).status();

    // Systemd target configuration
    let systemd_system = target_mount.join("etc/systemd/system");
    let _ = fs::create_dir_all(&systemd_system);
    match profile {
        InstallProfile::DeveloperMinimal => {
            let _ = Command::new("ln").args(["-sf", "/lib/systemd/system/multi-user.target", systemd_system.join("default.target").to_str().unwrap()]).status();
        }
        InstallProfile::GnomeDesktop => {
            let _ = Command::new("ln").args(["-sf", "/lib/systemd/system/graphical.target", systemd_system.join("default.target").to_str().unwrap()]).status();
        }
    }

    // 9. Configure /etc/fstab for Btrfs root and VFAT ESP
    let fstab_content = "\
# /etc/fstab: static file system information for MyelinOS
LABEL=MYELINOS_ROOT  /          btrfs  defaults,noatime,compress=zstd:1  0 0
LABEL=ESP            /boot/efi  vfat   defaults,noatime                  0 2
";
    let _ = fs::write(target_mount.join("etc/fstab"), fstab_content);

    // 10. Write installation metadata marker
    let manifest_path = target_mount.join("etc/myelin/bootstrap-manifest.json");
    let manifest_json = format!(
        "{{\n  \"installed_by\": \"axon-bootstrap-v0.1.0\",\n  \"stage\": 2,\n  \"filesystem\": \"btrfs\",\n  \"profile\": \"{:?}\",\n  \"root_dev\": \"{}\",\n  \"esp_dev\": \"{}\"\n}}\n",
        profile, root_dev, esp_dev
    );
    let _ = fs::write(manifest_path, manifest_json);

    // 11. Sync and unmount
    progress_cb("Flushing disk caches and unmounting partitions...", 95);
    let _ = Command::new("sync").status();
    let _ = Command::new("umount").arg(&esp_mount).status();
    let _ = Command::new("umount").arg(target_mount).status();

    if let Some(_) = payload_source {
        let _ = Command::new("umount").arg("/run/installer/source").status();
    }

    progress_cb("Stage 1 Bootstrap successfully completed!", 100);
    Ok(())
}
