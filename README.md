# MyelinOS — Minimal LFS Distribution with systemd

A simple, workable Linux distribution bootstrapped following the **Linux From Scratch (LFS) systemd** architecture.

This distribution is purposely minimal: it contains **only the Linux kernel, systemd as PID 1, glibc, essential core utilities, and standard LFS configuration**.

---

## Architecture Overview

- **Init System**: `systemd` (PID 1) running in full system mode.
- **Boot Target**: `multi-user.target` reached cleanly on boot.
- **Filesystem Standard**: Modern FHS 3.0 + UsrMerge (`/bin -> usr/bin`, `/sbin -> usr/sbin`, `/lib -> usr/lib`, `/lib64 -> usr/lib64`).
- **Core Units**:
  - `systemd-journald.service` & sockets
  - `systemd-udevd.service` & sockets
  - `systemd-remount-fs.service`
  - `tmp.mount` (tmpfs on `/tmp`)
  - `serial-getty@ttyS0.service` (auto-login root on serial console)
- **Standard LFS Configuration**:
  - `/etc/os-release` (`NAME="MyelinOS"`, `ID_LIKE=lfs`, `VERSION="0.1"`)
  - `/etc/hostname` (`myelinos`)
  - `/etc/hosts`
  - `/etc/fstab` (ext4 `/dev/vda` root, tmpfs `/tmp`)
  - `/etc/passwd`, `/etc/shadow`, `/etc/group`
  - `/etc/nsswitch.conf`
  - Standard minimal `/etc/pam.d` configuration

---

## Project Structure

```
MyelinOS/
├── Makefile                          # Build, run, test targets
├── README.md                         # Documentation
├── build/
│   ├── bootstrap/
│   │   ├── bootstrap.py              # LFS bootstrap generator
│   │   └── rootfs/                   # Assembled root filesystem
│   └── images/
│       ├── vmlinuz                   # Linux kernel image
│       └── myelinos-rootfs.ext4      # 200MB ext4 bootable disk image
└── tools/
    ├── run_qemu.sh                   # QEMU runner (interactive & test modes)
    └── test_boot.py                  # Automated boot assertion suite
```

---

## Quick Start

### 1. Build the Distribution
To assemble the rootfs and generate the ext4 disk image:

```bash
make build
# or: python3 build/bootstrap/bootstrap.py
```

### 2. Run Interactive QEMU Session
To boot the distribution interactively:

```bash
./tools/run_qemu.sh
# or: make run
```

Inside the VM:
- You land directly in a root bash prompt (`[root@myelinos ~]#`).
- You can inspect systemd status with `systemctl status` or `systemctl list-units`.
- Check OS identity with `cat /etc/os-release`.
- To exit QEMU: run `poweroff` inside the shell, or press `Ctrl-a x`.

### 3. Run Automated Boot Test
To run the automated verification test suite:

```bash
./tools/run_qemu.sh --test
# or: make test
```

The test boots the system in QEMU, verifies:
1. PID 1 is `systemd`
2. `/etc/os-release` contains `MyelinOS`
3. Root `/` is mounted read-write as `ext4`
4. `multi-user.target` is active
5. System cleanly powers off via ACPI S5
