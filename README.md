# MyelinOS — Linux Distribution (LFS + systemd + GNOME 50 Desktop + Rust for Linux)

A complete, bootable Linux distribution bootstrapped following the **Linux From Scratch (LFS) systemd** standard, featuring a **modern Wayland Display Server architecture**, **GNOME 50 Desktop Environment**, and **Linux Kernel 7.2.13 compiled from source with Rust for Linux enabled**.

MyelinOS combines the reliability and transparency of an LFS system with `systemd` v259 as PID 1, GNOME Shell 50 compositor and Mutter display server, X11 compatibility via `Xwayland`, Mesa DRM/KMS VirtIO graphics acceleration, D-Bus session and system message bus, PipeWire/WirePlumber audio stack, and a complete suite of standard desktop applications (Firefox, LibreOffice, Ptyxis terminal, Nautilus file manager, GNOME Calculator, GNOME Text Editor, Loupe, Papers, and GNOME System Monitor).

---

## Architecture & Subsystems

```
+--------------------------------------------------------------------------+
|                        MyelinOS Desktop System                           |
+--------------------------------------------------------------------------+
|  Applications & Office Suite:                                            |
|    * Web Browser:            Mozilla Firefox                             |
|    * Productivity:           LibreOffice Suite (Writer, Calc, Draw, etc) |
|    * Terminal Emulator:      Ptyxis 50 (GTK 4 / VTE / container-ready)   |
|    * File Manager:           Nautilus 50 (TinySPARQL / LocalSearch)      |
|    * Utilities:              GNOME Calculator, Text Editor, Loupe, Papers|
|    * System Monitor:         GNOME System Monitor, Baobab Disk Usage     |
|    * Python Runtime:         Python 3.14 Runtime & Full Standard Library |
|    * GNU Core:               Full Coreutils, Procps-ng, Util-Linux, Sudo |
+--------------------------------------------------------------------------+
|  Display Server & Desktop Layer:                                         |
|    * Wayland Compositor:     GNOME Shell 50.6 (native Wayland compositor)|
|    * Display Server Core:    Mutter 50.6 (DRM/KMS scanout, GBM, GL)      |
|    * X11 Display Server:     Xwayland (seamless X11 compatibility)       |
|    * Portals & Session:      XDG Desktop Portal (GNOME & GTK backends)   |
|    * Login & Display:        GDM 50 (GNOME Display Manager) / start-gnome|
+--------------------------------------------------------------------------+
|  Audio & Multimedia Stack:                                               |
|    * Sound Server:           PipeWire 1.4 & PipeWire-Pulse               |
|    * Session Manager:        WirePlumber 0.5 (ALSA, SPA plugins)         |
|    * Real-time Scheduling:   RealtimeKit (rtkit-daemon)                  |
+--------------------------------------------------------------------------+
|  Graphics & Acceleration Stack:                                          |
|    * Mesa 26.2:              Gallium, GBM, EGL, GL, GLESv2, Vulkan       |
|    * DRI Drivers:            virtio_gpu_dri.so, swrast_dri.so            |
|    * Input & Seat:           libseat, libinput, libxkbcommon, xkeyboard |
+--------------------------------------------------------------------------+
|  System & Service Infrastructure:                                        |
|    * Kernel:                 Linux 7.2.13 compiled with Rust for Linux   |
|    * Init System:            systemd v259 (PID 1, graphical.target)      |
|    * Message Bus:            D-Bus (dbus-daemon.service, dbus.socket)    |
|    * Privilege Escalation:   Sudo (wheel group NOPASSWD) & PolicyKit 1   |
|    * Networking:             systemd-networkd (DHCP), systemd-resolved   |
|    * Target Image Formats:   UEFI GPT Disk, Hybrid Live ISO, Ext4 Rootfs |
+--------------------------------------------------------------------------+
```

---

## Included Subsystems & Command Coverage

### 1. Kernel & Rust for Linux
- **Kernel Version**: Linux `7.2.13` compiled directly from source.
- **Rust for Linux**: Enabled with `CONFIG_RUST=y`, initialization of kernel Rust modules (`rust_minimal` sample verified in dmesg).
- **Core Drivers**: Built-in support for `virtio-gpu`, `virtio-net`, `virtio-blk`, `virtio-scsi`, `overlayfs`, `squashfs`, `ext4`, `vfat`, and `snd_hda_intel`.

### 2. Display Server & GNOME 50 Desktop Environment
- **Compositor & Shell**: GNOME Shell `50.6` running natively on Wayland.
- **Display Server Core**: Mutter `50.6` managing KMS page flips, GBM buffers, software GL fallback, and X11 frame clients.
- **X11 Compatibility**: `Xwayland` managed seamlessly with frame client support (`/usr/libexec/mutter-x11-frames`).
- **Standard Desktop Applications**:
  - **Firefox**: Mozilla Firefox web browser.
  - **LibreOffice Suite**: Complete office productivity suite (`soffice`, `oowriter`, `oocalc`, etc.).
  - **Ptyxis**: Modern GTK 4 terminal emulator (`/usr/bin/ptyxis`).
  - **Nautilus**: GNOME file manager with TinySPARQL and LocalSearch indexing.
  - **GNOME Calculator**: Mathematical and scientific calculation tool.
  - **GNOME Text Editor**: Modern GNOME editor.
  - **Loupe**: High-performance image viewer.
  - **Papers**: Modern document and PDF viewer.
  - **GNOME System Monitor**: Interactive process and resource inspection tool.

### 3. Privilege Escalation & Security
- **Sudo**: `/usr/bin/sudo` with SUID root permissions (`4755`), configured with `/etc/sudoers.d/10-wheel` granting full passwordless administration privileges to the `wheel` group.
- **PolicyKit**: `polkitd` daemon and `/usr/lib/polkit-1/polkit-agent-helper-1` with universal rule allowing `root`, `myelinos`, `wheel`, and `gdm`.
- **Default User**: `myelinos` (UID 1000, GID 1000) added to `wheel`, `video`, `audio`, `render`, `input`, and `seat` groups.

### 4. Audio & Multimedia Infrastructure
- **PipeWire & WirePlumber**: User-level sound management running under systemd user manager (`pipewire.service`, `pipewire-pulse.service`, `wireplumber.service`).
- **RealtimeKit**: `rtkit-daemon` providing real-time CPU scheduling priorities to audio and compositor threads.

### 5. Two-Stage Bootstrap Installer & Presets Architecture
1. **Stage 1: Ultra-Lightweight TUI Bootstrap Installer (`axon-installer-tui`)**:
   - Packaged in `build/images/myelinos-bootstrap.iso` (~73 MB).
   - Interactive terminal UI built with Rust and Ratatui.
   - Partitions target disk into UEFI GPT: 512 MB ESP (FAT32) and native Btrfs root (`MYELINOS_ROOT`).
   - Copies minimal base system and installs standalone UEFI GRUB 2 bootloader with built-in Btrfs drivers.
2. **Stage 2: Personalization & Software Presets Wizard (`myelin-installer-gui`)**:
   - Modern GTK 4 / Libadwaita application that launches on first boot of target disk.
   - Provides account creation, hostname configuration, and timezone localization.
   - Offers **11 specialized package presets**: Developer Workstation, Full-Stack & Web Dev, Data Science & AI/ML, DevOps & Cloud, Office & Productivity, Creative Studio, Gaming & Entertainment, Cybersecurity & Audit, Pro Audio, STEM & Education, Minimal Server & Hardened Workstation.
   - Seals system state into Axon CAS Generation 1 (`/var/lib/myelin/generations/gen-1.json`).
   - Permanently deletes autostart entries and configures GDM for the newly created user—the installer never reappears on reboot.

### 6. Multi-Target Boot Artifacts
1. **Bootstrap Installer ISO (`build/images/myelinos-bootstrap.iso`)**:
   - ~73 MB lightweight hybrid ISO (UEFI + BIOS).
2. **Target Disk Image (`build/images/target-disk.raw`)**:
   - 20 GB GPT virtual disk with Btrfs root and UEFI ESP partition.
3. **UEFI GPT Disk Image (`build/images/myelinos-uefi.img`)**:
   - GPT partition layout: ESP (64 MB, FAT32) + Root Filesystem (ext4, ~5.5 GB).
4. **Hybrid Live ISO Image (`build/images/myelinos-live.iso`)**:
   - High-compression zstd SquashFS root filesystem with OverlayFS.

---

## Quick Start & Build Instructions

### Prerequisites
- Linux host system with `cargo`, `podman`, `qemu-system-x86_64`, `ovmf`, `mksquashfs`, `xorriso`, and `grub2-mkimage`.

### Build Installer and System Images
```bash
# 1. Build Stage 1 Bootstrap Installer ISO (~73 MB)
make installer-iso
# or: python3 tools/build_bootstrap_iso.py

# 2. Build Hybrid Live ISO
make iso

# 3. Build UEFI GPT Disk Image
make uefi
```

### Running the Systems in QEMU
```bash
# Launch Stage 1 Bootstrap Installer (4 GB RAM, dual display VGA/GTK + TUI stdio)
./run_installer.sh

# Launch Stage 1 automated non-interactive install
./run_installer.sh --auto --headless --reset-disk

# Launch installed MyelinOS system from target disk
./run_system.sh -t

# Launch installed MyelinOS system with graphical window
./run_system.sh -t -g
```
- **Serial Console**: Automatic root login attached directly to standard input/output.
- **GNOME 50 Graphical Desktop**: Rendered via VirtIO GPU on VNC display `localhost:5901` (`:1`).
- **SSH Access**: Forwarded to host port 2222 (`ssh -p 2222 myelinos@localhost`).

---

## Project Structure

```
MyelinOS/
├── build/
│   ├── bootstrap/
│   │   ├── bootstrap.py            # Complete rootfs generator and image builder
│   │   └── rootfs/                 # Staged rootfs directory
│   ├── images/
│   │   ├── myelinos-rootfs.ext4    # 5.5GB sparse bootable ext4 disk image
│   │   ├── myelinos-uefi.img       # UEFI GPT bootable disk image
│   │   ├── myelinos-live.iso       # Hybrid Live ISO with SquashFS & OverlayFS
│   │   └── vmlinuz                 # Linux 7.2.13 kernel with Rust for Linux
│   └── packages/
│       ├── desktop_apps/           # Cached desktop application RPMs
│       ├── sudo/                   # Cached sudo RPMs
│       └── polkit/                 # Cached polkit RPMs
├── tools/
│   ├── build_uefi_disk.py          # UEFI GPT disk builder
│   ├── build_iso.py                # Hybrid Live ISO builder
│   ├── run_qemu.sh                 # Unified QEMU launcher
│   ├── test_boot.py                # Automated direct ext4 boot test suite
│   ├── test_uefi_boot.py           # Automated UEFI GPT test suite
│   ├── test_iso_boot.py            # Automated Live ISO test suite
│   └── system_audit.py             # In-depth systemd & compositor audit
├── Makefile                        # Top-level build, test, and run automation
└── README.md                       # Comprehensive documentation
```
