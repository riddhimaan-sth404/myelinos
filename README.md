# MyelinOS — Full-Featured Headless Linux Distribution (LFS + systemd)

A complete, workable headless Linux distribution bootstrapped following the **Linux From Scratch (LFS) systemd** standard.

This distribution includes **the complete set of standard CLI utilities, system administration tools, networking, SSH server, Python 3 runtime, kernel modules, terminfo, SSL certificates, and systemd as PID 1** (without any GUI or display server bloat).

---

## Included Subsystems & Command Coverage

### 1. Init System & Process Management (systemd)
- **PID 1**: `systemd` v259 running in system mode, reaching `multi-user.target`.
- **System Services Active**:
  - `systemd-journald` (logging & journal management)
  - `systemd-udevd` (kernel device events & dynamic dev nodes)
  - `systemd-networkd` (DHCP & network interface configuration)
  - `systemd-resolved` (DNS resolution & caching)
  - `systemd-timesyncd` (NTP clock synchronization)
  - `sshd.service` (OpenSSH server daemon with pre-generated host keys)
  - `serial-getty@ttyS0.service` (auto-login console on `/dev/ttyS0`)
- **System Control Tools**:
  `systemctl`, `journalctl`, `udevadm`, `loginctl`, `timedatectl`, `localectl`, `hostnamectl`, `bootctl`, `busctl`, `resolvectl`, `networkctl`, `poweroff`, `reboot`, `halt`, `shutdown`.

### 2. Standard Shell & GNU Coreutils (Full Suite)
- **Shells**: `bash` (with custom `/etc/profile` and `/root/.bashrc`), `sh`.
- **File Manipulation**: `cp`, `mv`, `rm`, `mkdir`, `rmdir`, `touch`, `ln`, `chmod`, `chown`, `chgrp`, `stat`, `truncate`, `dd`, `install`, `mktemp`, `mkfifo`, `mknod`, `sync`, `readlink`, `realpath`, `shred`, `vdir`, `dir`.
- **Text & Stream Processing**: `cat`, `tac`, `nl`, `head`, `tail`, `cut`, `paste`, `join`, `split`, `csplit`, `sort`, `uniq`, `wc`, `comm`, `tr`, `expand`, `unexpand`, `fmt`, `pr`, `fold`, `tee`, `od`, `base64`, `base32`, `basenc`.
- **Pattern Matching & Filtering**: `grep`, `egrep`, `fgrep`, `sed`, `gawk`, `awk`, `find`, `xargs`, `file`, `diff`, `cmp`, `patch`.
- **Checksums**: `md5sum`, `sha1sum`, `sha224sum`, `sha256sum`, `sha384sum`, `sha512sum`, `b2sum`, `cksum`.
- **Shell Logic & Testing**: `test`, `[`, `expr`, `env`, `printenv`, `echo`, `printf`, `yes`, `true`, `false`, `seq`, `shuf`, `basename`, `dirname`, `factor`.

### 3. Process & System Monitoring (Procps-ng)
- `ps`, `top`, `free`, `vmstat`, `pkill`, `pgrep`, `pidof`, `kill`, `killall`, `watch`, `timeout`, `nice`, `renice`, `nohup`.

### 4. Disk, Storage & Filesystems (util-linux & e2fsprogs)
- `mount`, `umount`, `findmnt`, `lsblk`, `blkid`, `fdisk`, `cfdisk`, `sfdisk`, `partx`, `wipefs`, `losetup`, `fallocate`, `fstrim`, `fsfreeze`.
- `mke2fs`, `mkfs`, `mkfs.ext2`, `mkfs.ext3`, `mkfs.ext4`, `e2fsck`, `fsck`, `fsck.ext4`, `tune2fs`, `resize2fs`, `dumpe2fs`, `chattr`, `lsattr`, `mkswap`, `swapon`, `swapoff`.

### 5. Archiving & Compression
- `tar`, `cpio`, `gzip`, `gunzip`, `zcat`, `bzip2`, `bunzip2`, `bzcat`, `xz`, `unxz`, `xzcat`, `zstd`, `unzstd`, `zstdcat`.

### 6. Text Editors, Pagers & Terminal
- **Editors & Pagers**: `nano` (with full syntax highlighting in `/usr/share/nano` & `/etc/nanorc`), `vi` (with `/usr/share/vim`), `less`, `more`.
- **Terminal Control**: `clear`, `reset`, `tput`, `stty`.
- **Terminfo**: Complete `/usr/share/terminfo` database (supports `linux`, `xterm`, `xterm-256color`, `vt100`, `screen`, `tmux`).

### 7. Networking & Remote Access
- **Network Tools**: `ip` (`iproute2`), `ss`, `bridge`, `rtmon`, `ping`, `curl`, `wget`.
- **OpenSSH**: `ssh`, `sshd`, `scp`, `sftp`, `ssh-keygen`, `ssh-agent`, `ssh-add`, `/usr/libexec/openssh/sftp-server`, `/usr/libexec/openssh/sshd-session`.
- **SSL / CA Certificates**: Global CA bundle at `/etc/ssl/certs/ca-certificates.crt` and `/etc/pki/tls/certs/ca-bundle.crt` for HTTPS with `curl` and Python.

### 8. Python 3 Runtime
- `python3` (v3.14) and `/usr/bin/python` symlink.
- Full standard library installed in `/usr/lib64/python3.14` (including compiled C extensions: `math`, `json`, `sqlite3`, `ssl`, `ctypes`, `socket`, `urllib`, `hashlib`, etc.).

### 9. Kernel Modules & Hardware
- `kmod`: `modprobe`, `insmod`, `rmmod`, `lsmod`, `modinfo`, `depmod`.
- Complete kernel module tree installed in `/lib/modules/7.2.11-200.fc44.x86_64` (drivers for network, virtio, crypto, filesystems).

### 10. User Account Management & Security
- `useradd`, `userdel`, `usermod`, `groupadd`, `groupdel`, `groupmod`, `passwd`, `chage`, `su`, `sulogin`.
- Setuid binaries configured: `su`, `passwd`, `ping`, `mount`, `umount`.

---

## Directory Structure

```
MyelinOS/
├── Makefile                          # Build, run, test targets
├── README.md                         # Documentation
├── build/
│   ├── bootstrap/
│   │   ├── bootstrap.py              # Full headless distribution builder
│   │   └── rootfs/                   # Root filesystem tree
│   └── images/
│       ├── vmlinuz                   # Linux kernel image
│       └── myelinos-rootfs.ext4      # 1.5GB ext4 bootable disk image
└── tools/
    ├── run_qemu.sh                   # QEMU runner (interactive & test modes)
    └── test_boot.py                  # Automated verification test suite
```

---

## Usage

### 1. Run Interactive QEMU Session
```bash
make run
# or: ./tools/run_qemu.sh
```
- Drops directly into a root prompt (`[root@myelinos ~]#`).
- Port forwarding is active: host `localhost:2222` forwards to guest SSH port `22`.
- To exit QEMU: type `poweroff` or press `Ctrl-a x`.

### 2. Run Automated Verification Test
```bash
make test
# or: ./tools/run_qemu.sh --test
```
Verifies PID 1 systemd, network interface, ping, coreutils, pipes, checksums, Python 3 runtime & stdlib, compression tools, editors, kernel modules, disk reporting, sshd status, and ACPI poweroff.

### 3. Rebuild from Scratch
```bash
make build
# or: python3 build/bootstrap/bootstrap.py
```
