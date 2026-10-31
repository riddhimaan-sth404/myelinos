#!/usr/bin/env python3
"""
MyelinOS LFS Bootstrap Script
Constructs a minimal, workable Linux distribution based on the Linux From Scratch (LFS)
systemd standard. Includes systemd as PID 1, core utilities, and standard LFS configuration.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
BUILD_DIR = BASE_DIR / "build"
ROOTFS_DIR = BUILD_DIR / "bootstrap" / "rootfs"
IMAGES_DIR = BUILD_DIR / "images"
ROOTFS_IMG = IMAGES_DIR / "myelinos-rootfs.ext4"
KERNEL_SRC = Path("/boot/vmlinuz-7.2.11-200.fc44.x86_64")
KERNEL_DEST = IMAGES_DIR / "vmlinuz"

def resolve_deps(binary_path, found_deps=None):
    """Recursively resolve all dynamic library dependencies using ldd."""
    if found_deps is None:
        found_deps = set()
    
    if not os.path.exists(binary_path):
        return found_deps
    
    try:
        out = subprocess.check_output(["ldd", binary_path], stderr=subprocess.DEVNULL, text=True)
    except Exception:
        return found_deps
    
    for line in out.splitlines():
        line = line.strip()
        if "=>" in line:
            parts = line.split("=>")
            right = parts[1].strip().split()[0]
            if right.startswith("/") and os.path.exists(right):
                if right not in found_deps:
                    found_deps.add(right)
                    resolve_deps(right, found_deps)
        elif line.startswith("/"):
            left = line.split()[0]
            if os.path.exists(left):
                if left not in found_deps:
                    found_deps.add(left)
                    resolve_deps(left, found_deps)
    return found_deps

def create_directory_hierarchy(root: Path):
    """Create standard LFS filesystem hierarchy (FHS 3.0 / UsrMerge)."""
    if root.exists():
        shutil.rmtree(root)

    dirs = [
        "usr/bin", "usr/sbin", "usr/lib", "usr/lib64",
        "usr/lib/systemd/system", "usr/lib/systemd/system-generators",
        "usr/local/bin", "usr/local/sbin", "usr/local/lib", "usr/local/lib/systemd/system",
        "etc/systemd/system", "etc/systemd/system/multi-user.target.wants",
        "etc/systemd/system/sysinit.target.wants", "etc/systemd/system/getty.target.wants",
        "etc/pam.d", "etc/selinux",
        "dev", "proc", "sys", "sys/fs/cgroup",
        "run", "run/systemd", "run/lock",
        "tmp", "root", "home", "mnt",
        "var/log", "var/tmp", "var/lib/systemd"
    ]
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)

    # Standard UsrMerge and LFS compatibility symlinks
    symlinks = [
        ("bin", "usr/bin"),
        ("sbin", "usr/sbin"),
        ("lib", "usr/lib"),
        ("lib64", "usr/lib64"),
        ("var/run", "../run"),
        ("var/lock", "../run/lock"),
        ("etc/mtab", "/proc/self/mounts"),
    ]
    for link, target in symlinks:
        link_path = root / link
        if link_path.exists() or link_path.is_symlink():
            if link_path.is_dir() and not link_path.is_symlink():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
        link_path.symlink_to(target)

    # /usr/sbin/init -> ../lib/systemd/systemd
    init_symlink = root / "usr/sbin/init"
    if not init_symlink.exists():
        init_symlink.symlink_to("../lib/systemd/systemd")

def install_binaries_and_libs(root: Path):
    """Collect and install the minimal binary set and all shared libraries."""
    binaries = [
        # Systemd core & helpers
        "/usr/lib/systemd/systemd",
        "/usr/lib/systemd/systemd-executor",
        "/usr/lib/systemd/systemd-journald",
        "/usr/lib/systemd/systemd-udevd",
        "/usr/lib/systemd/systemd-sysctl",
        "/usr/lib/systemd/systemd-modules-load",
        "/usr/lib/systemd/systemd-remount-fs",
        "/usr/lib/systemd/systemd-tmpfiles",
        "/usr/lib/systemd/systemd-random-seed",
        "/usr/lib/systemd/systemd-logind",
        "/usr/lib/systemd/systemd-user-runtime-dir",
        "/usr/lib/systemd/systemd-shutdown",
        "/usr/lib/systemd/systemd-sulogin-shell",
        "/usr/lib/systemd/systemd-vconsole-setup",
        
        # System management utilities
        "/usr/bin/systemctl",
        "/usr/bin/journalctl",
        "/usr/bin/udevadm",
        
        # Shell
        "/usr/bin/bash",
        "/usr/bin/sh",
        
        # GNU Core Utilities
        "/usr/bin/ls", "/usr/bin/cat", "/usr/bin/echo", "/usr/bin/mkdir",
        "/usr/bin/rmdir", "/usr/bin/cp", "/usr/bin/mv", "/usr/bin/rm",
        "/usr/bin/uname", "/usr/bin/ps", "/usr/bin/kill", "/usr/bin/stty",
        "/usr/bin/sync", "/usr/bin/sleep", "/usr/bin/env", "/usr/bin/id",
        "/usr/bin/whoami", "/usr/bin/pwd", "/usr/bin/grep", "/usr/bin/sed",
        "/usr/bin/find", "/usr/bin/head", "/usr/bin/tail", "/usr/bin/wc",
        "/usr/bin/date", "/usr/bin/touch", "/usr/bin/chmod", "/usr/bin/chown",
        "/usr/bin/true", "/usr/bin/false",
        
        # Util-linux
        "/usr/sbin/agetty",
        "/usr/bin/login",
        "/usr/bin/mount",
        "/usr/bin/umount",
        "/usr/sbin/sulogin",
        "/usr/bin/dmesg",
        "/usr/sbin/poweroff",
        "/usr/sbin/reboot",
        "/usr/sbin/halt",
    ]

    all_libs = set()

    # Copy binaries
    for b in binaries:
        if os.path.islink(b):
            target = os.readlink(b)
            dest = root / b.lstrip("/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_symlink() or dest.exists():
                dest.unlink()
            dest.symlink_to(target)
            real_b = os.path.realpath(b)
            if os.path.exists(real_b):
                real_dest = root / real_b.lstrip("/")
                real_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(real_b, real_dest)
                resolve_deps(real_b, all_libs)
        elif os.path.exists(b):
            dest = root / b.lstrip("/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(b, dest)
            resolve_deps(b, all_libs)

    # Copy all binaries in /usr/lib/systemd
    for item in Path("/usr/lib/systemd").iterdir():
        if item.is_file() and os.access(item, os.X_OK):
            dest = root / item.as_posix().lstrip("/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(item, dest)
                resolve_deps(str(item), all_libs)

    # Copy systemd system-generators
    if Path("/usr/lib/systemd/system-generators").exists():
        shutil.copytree("/usr/lib/systemd/system-generators", root / "usr/lib/systemd/system-generators", dirs_exist_ok=True)
        for gen in (root / "usr/lib/systemd/system-generators").iterdir():
            if gen.is_file() and os.access(gen, os.X_OK):
                resolve_deps(str(gen), all_libs)

    # Include NSS, PAM, BPF, kmod, seccomp, cryptsetup libs explicitly
    for p in Path("/usr/lib64").glob("libnss*"):
        all_libs.add(str(p))
    for p in Path("/usr/lib64").glob("libbpf*"):
        all_libs.add(str(p))
    for p in Path("/usr/lib64").glob("libkmod*"):
        all_libs.add(str(p))
    for p in Path("/usr/lib64").glob("libseccomp*"):
        all_libs.add(str(p))
    for p in Path("/usr/lib64").glob("libcryptsetup*"):
        all_libs.add(str(p))
    for p in Path("/usr/lib64/security").glob("*.so*"):
        all_libs.add(str(p))
    for p in Path("/usr/lib64/systemd").glob("*.so*"):
        all_libs.add(str(p))

    # Resolve dependencies transitively
    for lib in list(all_libs):
        resolve_deps(lib, all_libs)

    # Copy all libraries
    for lib in all_libs:
        if os.path.exists(lib):
            dest = root / lib.lstrip("/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(lib, dest)

    # Copy udev rules
    if Path("/usr/lib/udev/rules.d").exists():
        shutil.copytree("/usr/lib/udev/rules.d", root / "usr/lib/udev/rules.d", dirs_exist_ok=True)

def install_systemd_units(root: Path):
    """Install core systemd unit files and establish target relationships."""
    sysd_src = Path("/usr/lib/systemd/system")
    sysd_dest = root / "usr/lib/systemd/system"
    if sysd_src.exists():
        units_to_copy = [
            "basic.target", "sysinit.target", "multi-user.target", "default.target",
            "emergency.target", "emergency.service", "rescue.target", "rescue.service",
            "local-fs.target", "local-fs-pre.target", "remote-fs.target", "remote-fs-pre.target",
            "slices.target", "sockets.target", "timers.target", "paths.target",
            "shutdown.target", "reboot.target", "poweroff.target", "halt.target",
            "systemd-journald.service", "systemd-journald.socket",
            "systemd-journald-dev-log.socket", "systemd-journald-audit.socket",
            "systemd-udevd.service", "systemd-udevd-control.socket", "systemd-udevd-kernel.socket",
            "systemd-remount-fs.service", "systemd-tmpfiles-setup.service", "systemd-tmpfiles-setup-dev.service",
            "systemd-sysctl.service", "systemd-modules-load.service", "systemd-random-seed.service",
            "serial-getty@.service", "getty@.service", "console-getty.service",
            "systemd-logind.service", "systemd-user-sessions.service",
            "systemd-vconsole-setup.service"
        ]
        for u in units_to_copy:
            src_path = sysd_src / u
            if src_path.is_symlink():
                t = os.readlink(src_path)
                d = sysd_dest / u
                if d.exists() or d.is_symlink(): d.unlink()
                d.symlink_to(t)
            elif src_path.is_file():
                shutil.copy2(src_path, sysd_dest / u)
            elif src_path.is_dir():
                shutil.copytree(src_path, sysd_dest / u, dirs_exist_ok=True)

    # Set default target to multi-user.target
    default_target = root / "etc/systemd/system/default.target"
    if default_target.exists() or default_target.is_symlink():
        default_target.unlink()
    default_target.symlink_to("/usr/lib/systemd/system/multi-user.target")

    # Enable journald and udevd
    for s in ["systemd-journald.service", "systemd-udevd.service"]:
        link = root / "etc/systemd/system/sysinit.target.wants" / s
        if not link.exists():
            link.symlink_to(f"/usr/lib/systemd/system/{s}")

    # Clean serial getty unit without dev-ttyS0 device binding for direct serial boot
    serial_unit = root / "etc/systemd/system/serial-getty@.service"
    serial_unit.write_text("""[Unit]
Description=Serial Getty on %I
Documentation=man:agetty(8)
After=systemd-user-sessions.service getty-pre.target
Before=getty.target
Conflicts=rescue.service
Before=rescue.service

[Service]
ExecStart=-/usr/sbin/agetty --autologin root --noclear 115200 %I linux
Type=idle
Restart=always
UtmpIdentifier=%I
StandardInput=tty
StandardOutput=tty
TTYPath=/dev/%I
TTYReset=yes
TTYVHangup=yes
IgnoreSIGPIPE=no
SendSIGHUP=yes

[Install]
WantedBy=getty.target
""")
    # Link serial-getty@ttyS0 to multi-user.target.wants
    ttyS0_link = root / "etc/systemd/system/multi-user.target.wants/serial-getty@ttyS0.service"
    if ttyS0_link.exists() or ttyS0_link.is_symlink():
        ttyS0_link.unlink()
    ttyS0_link.symlink_to("/etc/systemd/system/serial-getty@.service")

    # Link console-getty to getty.target.wants
    console_link = root / "etc/systemd/system/getty.target.wants/console-getty.service"
    if not console_link.exists():
        console_link.symlink_to("/usr/lib/systemd/system/console-getty.service")

def install_configuration_files(root: Path):
    """Install LFS system configuration files."""
    # /etc/os-release
    (root / "etc/os-release").write_text("""NAME="MyelinOS"
PRETTY_NAME="MyelinOS 0.1 (LFS systemd)"
ID=myelinos
ID_LIKE=lfs
VERSION="0.1"
VERSION_ID="0.1"
HOME_URL="https://github.com/myelinos"
""")

    # /etc/hostname
    (root / "etc/hostname").write_text("myelinos\n")

    # /etc/hosts
    (root / "etc/hosts").write_text("""127.0.0.1   localhost myelinos
::1         localhost ip6-localhost ip6-loopback
""")

    # /etc/nsswitch.conf
    (root / "etc/nsswitch.conf").write_text("""passwd:      files
group:       files
shadow:      files
hosts:       files dns
networks:    files
protocols:   files
services:    files
ethers:      files
rpc:         files
""")

    # /etc/passwd
    (root / "etc/passwd").write_text("""root:x:0:0:root:/root:/bin/bash
bin:x:1:1:bin:/bin:/bin/false
daemon:x:2:2:daemon:/sbin:/bin/false
adm:x:3:4:adm:/var/adm:/bin/false
lp:x:4:7:lp:/var/spool/lpd:/bin/false
systemd-journal:x:999:999:systemd-journal:/:/bin/false
systemd-network:x:998:998:systemd-network:/:/bin/false
systemd-resolve:x:997:997:systemd-resolve:/:/bin/false
systemd-timesync:x:996:996:systemd-timesync:/:/bin/false
systemd-coredump:x:995:995:systemd-coredump:/:/bin/false
nobody:x:65534:65534:Kernel Overflow User:/:/bin/false
""")

    # /etc/shadow - root with blank password
    (root / "etc/shadow").write_text("""root::19000:0:99999:7:::
bin:*:19000:0:99999:7:::
daemon:*:19000:0:99999:7:::
adm:*:19000:0:99999:7:::
lp:*:19000:0:99999:7:::
systemd-journal:*:19000:0:99999:7:::
systemd-network:*:19000:0:99999:7:::
systemd-resolve:*:19000:0:99999:7:::
systemd-timesync:*:19000:0:99999:7:::
systemd-coredump:*:19000:0:99999:7:::
nobody:*:19000:0:99999:7:::
""")

    # /etc/group
    (root / "etc/group").write_text("""root:x:0:
bin:x:1:
daemon:x:2:
sys:x:3:
adm:x:4:
tty:x:5:
disk:x:6:
lp:x:7:
kmem:x:9:
wheel:x:10:root
cdrom:x:11:
audio:x:63:
video:x:39:
utmp:x:43:
systemd-journal:x:999:
systemd-network:x:998:
systemd-resolve:x:997:
systemd-timesync:x:996:
systemd-coredump:x:995:
nogroup:x:65534:
""")

    # /etc/fstab
    (root / "etc/fstab").write_text("""/dev/vda    /       ext4    defaults,noatime    0 1
tmpfs       /tmp    tmpfs   defaults,nosuid,nodev 0 0
""")

    # /etc/profile
    (root / "etc/profile").write_text(r"""export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export TERM=linux
export HOME=/root
export USER=root
export PS1='[\u@\h \W]\$ '
umask 022
cd /root
""")

    # /root/.bashrc
    (root / "root/.bashrc").write_text(r"""export PS1='[\u@\h \W]\$ '
""")

    # /etc/issue
    (root / "etc/issue").write_text(r"""\S - MyelinOS LFS (systemd) 0.1 (\l)
Kernel \r on an \m

""")

    # /etc/systemd/system.conf
    (root / "etc/systemd/system.conf").write_text("""[Manager]
LogLevel=info
LogTarget=console
ShowStatus=yes
StatusUnitFormat=combined
""")

    # Empty machine-id so systemd commits its generated machine-id
    (root / "etc/machine-id").touch()

    # Log files
    for lf in ["var/run/utmp", "var/log/wtmp", "var/log/lastlog"]:
        (root / lf).touch()

    # Minimal PAM configuration
    (root / "etc/pam.d/other").write_text("""#%PAM-1.0
auth        required    pam_permit.so
account     required    pam_permit.so
password    required    pam_permit.so
session     required    pam_permit.so
""")
    (root / "etc/pam.d/system-auth").write_text("""#%PAM-1.0
auth        sufficient  pam_permit.so
auth        required    pam_unix.so nullok
account     required    pam_permit.so
password    required    pam_permit.so
session     required    pam_permit.so
""")
    (root / "etc/pam.d/login").write_text("""#%PAM-1.0
auth        sufficient  pam_permit.so
auth        required    pam_unix.so nullok
account     required    pam_permit.so
password    required    pam_permit.so
session     required    pam_permit.so
""")

def build_disk_image():
    """Create ext4 filesystem disk image using podman unshare for proper root permissions."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy kernel if not already in images
    if not KERNEL_DEST.exists():
        if KERNEL_SRC.exists():
            print(f"Copying kernel {KERNEL_SRC} -> {KERNEL_DEST}...")
            shutil.copy2(KERNEL_SRC, KERNEL_DEST)
        else:
            raise FileNotFoundError(f"Kernel source not found at {KERNEL_SRC}")

    print("Setting permissions and formatting ext4 image via podman unshare...")
    cmd = f"""
    chmod 1777 {ROOTFS_DIR}/tmp
    chmod 4755 {ROOTFS_DIR}/usr/bin/mount
    chmod 4755 {ROOTFS_DIR}/usr/bin/umount
    chmod 600 {ROOTFS_DIR}/etc/shadow
    chmod 644 {ROOTFS_DIR}/etc/passwd {ROOTFS_DIR}/etc/group
    chmod 664 {ROOTFS_DIR}/var/run/utmp {ROOTFS_DIR}/var/log/wtmp {ROOTFS_DIR}/var/log/lastlog
    chown -R 0:0 {ROOTFS_DIR}
    mke2fs -t ext4 -d {ROOTFS_DIR} -m 0 -F {ROOTFS_IMG} 200M
    """
    subprocess.check_call(["podman", "unshare", "sh", "-c", cmd])
    print(f"Successfully generated bootable rootfs image: {ROOTFS_IMG}")

def main():
    print("=== MyelinOS LFS Bootstrap Starting ===")
    print(f"Target Rootfs Directory: {ROOTFS_DIR}")
    print(f"Target Image:            {ROOTFS_IMG}")
    print(f"Target Kernel:           {KERNEL_DEST}")
    
    create_directory_hierarchy(ROOTFS_DIR)
    install_binaries_and_libs(ROOTFS_DIR)
    install_systemd_units(ROOTFS_DIR)
    install_configuration_files(ROOTFS_DIR)
    build_disk_image()
    print("=== MyelinOS LFS Bootstrap Complete ===")

if __name__ == "__main__":
    main()
