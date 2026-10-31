#!/usr/bin/env python3
"""
MyelinOS Full-Featured Headless Linux Distribution Bootstrap
Constructs a complete, workable Linux distribution based on the Linux From Scratch (LFS)
systemd standard. Contains all standard CLI utilities, system administration tools, networking,
SSH server, Python 3 runtime, kernel modules, terminfo, SSL certificates, and systemd services.
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
        "usr/bin", "usr/lib", "usr/lib64",
        "usr/lib/systemd/system", "usr/lib/systemd/system-generators",
        "usr/lib/systemd/network",
        "usr/local/bin", "usr/local/lib", "usr/local/lib/systemd/system",
        "usr/share/terminfo", "usr/share/nano", "usr/share/vim", "usr/share/empty.sshd",
        "usr/libexec/openssh",
        "etc/systemd/system", "etc/systemd/system/multi-user.target.wants",
        "etc/systemd/system/sysinit.target.wants", "etc/systemd/system/getty.target.wants",
        "etc/systemd/network",
        "etc/pam.d", "etc/selinux", "etc/ssh", "etc/ssl/certs", "etc/pki/tls/certs",
        "dev", "proc", "sys", "sys/fs/cgroup",
        "run", "run/systemd", "run/lock",
        "tmp", "root", "home", "mnt", "opt",
        "var/log", "var/tmp", "var/lib/systemd", "var/empty/sshd"
    ]
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)

    # Standard UsrMerge and LFS compatibility symlinks
    symlinks = [
        ("bin", "usr/bin"),
        ("sbin", "usr/bin"),
        ("lib", "usr/lib"),
        ("lib64", "usr/lib64"),
        ("usr/sbin", "bin"),
        ("usr/local/sbin", "bin"),
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

    # /usr/bin/init -> ../lib/systemd/systemd
    init_symlink = root / "usr/bin/init"
    if not init_symlink.exists():
        init_symlink.symlink_to("../lib/systemd/systemd")

def install_binaries_and_libs(root: Path):
    """Collect and install the full CLI binary set and all shared libraries."""
    all_bins = [
        # Systemd core & helpers
        "systemd", "systemd-executor", "systemd-journald", "systemd-udevd",
        "systemd-sysctl", "systemd-modules-load", "systemd-remount-fs",
        "systemd-tmpfiles", "systemd-random-seed", "systemd-logind",
        "systemd-networkd", "systemd-resolved", "systemd-timesyncd",
        "systemd-user-runtime-dir", "systemd-shutdown", "systemd-sulogin-shell",
        "systemd-vconsole-setup",
        
        # System control & inspection
        "systemctl", "journalctl", "udevadm", "loginctl", "timedatectl",
        "localectl", "hostnamectl", "hostname", "bootctl", "busctl", "resolvectl", "networkctl",
        
        # Shells
        "bash", "sh",
        
        # GNU Core Utilities (Full Set)
        "cat", "chgrp", "chmod", "chown", "cp", "date", "dd", "df", "dmesg",
        "echo", "false", "ln", "ls", "mkdir", "mknod", "mktemp", "mv", "pwd",
        "rm", "rmdir", "sleep", "stty", "sync", "touch", "true", "uname",
        "readlink", "realpath", "truncate", "stat", "shred", "basename",
        "dirname", "cut", "head", "tail", "wc", "sort", "uniq", "tr", "tee",
        "fold", "split", "join", "comm", "paste", "csplit", "expand", "unexpand",
        "fmt", "pr", "nl", "od", "base64", "base32", "basenc", "md5sum",
        "sha1sum", "sha256sum", "sha512sum", "b2sum", "cksum", "env", "printenv",
        "expr", "factor", "seq", "shuf", "yes", "id", "whoami", "groups", "users",
        "who", "w", "uptime", "logname", "tty", "nproc", "du", "test", "[",
        
        # Find & text stream processing
        "find", "xargs", "grep", "egrep", "fgrep", "sed", "gawk", "awk",
        "which", "whereis", "file", "diff", "cmp", "patch",
        
        # Text editors & pagers
        "less", "more", "nano", "vi",
        
        # Terminal management
        "clear", "reset", "tput",
        
        # Process monitoring & control (procps-ng)
        "ps", "top", "free", "kill", "killall", "pkill", "pgrep", "pidof",
        "watch", "timeout", "nice", "renice", "nohup",
        
        # Archiving & compression
        "tar", "cpio", "gzip", "gunzip", "zcat", "bzip2", "bunzip2", "bzcat",
        "xz", "unxz", "xzcat", "zstd", "unzstd", "zstdcat",
        
        # Disk & filesystem administration
        "mount", "umount", "findmnt", "lsblk", "blkid", "fdisk", "cfdisk",
        "sfdisk", "partx", "wipefs", "losetup", "fallocate", "fstrim", "fsfreeze",
        "mke2fs", "mkfs", "mkfs.ext2", "mkfs.ext3", "mkfs.ext4", "e2fsck", "fsck",
        "fsck.ext4", "tune2fs", "resize2fs", "dumpe2fs", "chattr", "lsattr",
        "mkswap", "swapon", "swapoff",
        
        # Kernel modules & hardware
        "kmod", "modprobe", "insmod", "rmmod", "lsmod", "modinfo", "depmod",
        "lscpu", "setarch", "taskset", "chcpu", "ionice",
        
        # Networking & remote access
        "ip", "ss", "bridge", "rtmon", "ping", "curl", "wget",
        "ssh", "sshd", "scp", "sftp", "ssh-keygen", "ssh-agent", "ssh-add",
        
        # Account management
        "useradd", "userdel", "usermod", "groupadd", "groupdel", "groupmod",
        "passwd", "chage", "su", "sulogin", "agetty", "login",
        
        # Power & runlevel control
        "poweroff", "reboot", "halt", "shutdown",
        
        # Scripting & system inspection
        "python3", "ldconfig", "lsof", "man", "groff"
    ]

    all_libs = set()
    copied_bins = 0

    # Locate and copy all binaries
    for name in all_bins:
        # Search path or specific location
        path = shutil.which(name)
        if not path:
            candidate = Path("/usr/lib/systemd") / name
            if candidate.exists():
                path = str(candidate)
            else:
                candidate = Path("/usr/sbin") / name
                if candidate.exists():
                    path = str(candidate)
        
        if path and os.path.exists(path):
            if os.path.islink(path):
                target = os.readlink(path)
                dest = root / path.lstrip("/")
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.is_symlink() or dest.exists():
                    dest.unlink()
                dest.symlink_to(target)
                real_p = os.path.realpath(path)
                if os.path.exists(real_p):
                    real_dest = root / real_p.lstrip("/")
                    real_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(real_p, real_dest)
                    resolve_deps(real_p, all_libs)
            else:
                dest = root / path.lstrip("/")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
                resolve_deps(path, all_libs)
            copied_bins += 1

    # Python link /usr/bin/python -> python3
    py_link = root / "usr/bin/python"
    if py_link.exists() or py_link.is_symlink():
        py_link.unlink()
    py_link.symlink_to("python3")

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

    # Copy Python 3.14 standard library
    py_lib_src = Path("/usr/lib64/python3.14")
    py_lib_dest = root / "usr/lib64/python3.14"
    if py_lib_src.exists():
        print("Copying Python 3.14 standard library...")
        shutil.copytree(py_lib_src, py_lib_dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        # Resolve dependencies of python dynload C extensions
        dynload = py_lib_src / "lib-dynload"
        if dynload.exists():
            for so in dynload.glob("*.so"):
                resolve_deps(str(so), all_libs)

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
    print(f"Installing {len(all_libs)} shared libraries...")
    for lib in all_libs:
        if os.path.exists(lib):
            dest = root / lib.lstrip("/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(lib, dest)

    # Copy terminfo database
    if Path("/usr/share/terminfo").exists():
        print("Copying terminfo database...")
        shutil.copytree("/usr/share/terminfo", root / "usr/share/terminfo", dirs_exist_ok=True)

    # Copy C.utf8 locale
    loc_src = Path("/usr/lib/locale/C.utf8")
    if loc_src.exists():
        print("Copying C.utf8 locale...")
        loc_dest = root / "usr/lib/locale/C.utf8"
        loc_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(loc_src, loc_dest, dirs_exist_ok=True)
        c_upper = root / "usr/lib/locale/C.UTF-8"
        if not c_upper.exists():
            c_upper.symlink_to("C.utf8")

    # Copy nano syntax definitions
    if Path("/usr/share/nano").exists():
        shutil.copytree("/usr/share/nano", root / "usr/share/nano", dirs_exist_ok=True)
    if Path("/etc/nanorc").exists():
        shutil.copy2("/etc/nanorc", root / "etc/nanorc")

    # Copy vim runtime
    if Path("/usr/share/vim").exists():
        shutil.copytree("/usr/share/vim", root / "usr/share/vim", dirs_exist_ok=True)

    # Copy CA certificates
    ca_file = Path("/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem")
    if ca_file.exists():
        print("Copying SSL CA certificates...")
        (root / "etc/ssl/certs").mkdir(parents=True, exist_ok=True)
        (root / "etc/pki/tls/certs").mkdir(parents=True, exist_ok=True)
        shutil.copy2(ca_file, root / "etc/ssl/certs/ca-certificates.crt")
        shutil.copy2(ca_file, root / "etc/pki/tls/certs/ca-bundle.crt")

    # Copy kernel modules
    mod_src = Path("/lib/modules/7.2.11-200.fc44.x86_64")
    mod_dest = root / "lib/modules/7.2.11-200.fc44.x86_64"
    if mod_src.exists():
        print("Copying kernel modules...")
        shutil.copytree(mod_src, mod_dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("build", "source"))

    # Copy all helpers in /usr/libexec/openssh
    ssh_libexec = Path("/usr/libexec/openssh")
    if ssh_libexec.exists():
        dest_ssh_libexec = root / "usr/libexec/openssh"
        shutil.copytree(ssh_libexec, dest_ssh_libexec, dirs_exist_ok=True)
        for item in dest_ssh_libexec.iterdir():
            if item.is_file() and os.access(item, os.X_OK):
                resolve_deps(str(item), all_libs)

    # Copy udev rules
    if Path("/usr/lib/udev/rules.d").exists():
        shutil.copytree("/usr/lib/udev/rules.d", root / "usr/lib/udev/rules.d", dirs_exist_ok=True)

    print(f"Installed {copied_bins} binaries and {len(all_libs)} dynamic libraries.")

def install_systemd_units(root: Path):
    """Install core systemd unit files, targets, and networking services."""
    sysd_src = Path("/usr/lib/systemd/system")
    sysd_dest = root / "usr/lib/systemd/system"
    if sysd_src.exists():
        units_to_copy = [
            "basic.target", "sysinit.target", "multi-user.target", "default.target",
            "emergency.target", "emergency.service", "rescue.target", "rescue.service",
            "local-fs.target", "local-fs-pre.target", "remote-fs.target", "remote-fs-pre.target",
            "network.target", "network-online.target", "network-pre.target",
            "slices.target", "sockets.target", "timers.target", "paths.target",
            "shutdown.target", "reboot.target", "poweroff.target", "halt.target",
            "systemd-journald.service", "systemd-journald.socket",
            "systemd-journald-dev-log.socket", "systemd-journald-audit.socket",
            "systemd-udevd.service", "systemd-udevd-control.socket", "systemd-udevd-kernel.socket",
            "systemd-remount-fs.service", "systemd-tmpfiles-setup.service", "systemd-tmpfiles-setup-dev.service",
            "systemd-sysctl.service", "systemd-modules-load.service", "systemd-random-seed.service",
            "systemd-networkd.service", "systemd-networkd.socket", "systemd-networkd-wait-online.service",
            "systemd-resolved.service", "systemd-timesyncd.service",
            "serial-getty@.service", "getty@.service", "console-getty.service",
            "systemd-logind.service", "systemd-user-sessions.service",
            "systemd-vconsole-setup.service",
            "sshd.service", "sshd@.service", "sshd.socket"
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

    # Enable essential services in sysinit / multi-user targets
    for s in ["systemd-journald.service", "systemd-udevd.service"]:
        link = root / "etc/systemd/system/sysinit.target.wants" / s
        if not link.exists():
            link.symlink_to(f"/usr/lib/systemd/system/{s}")

    for s in ["systemd-networkd.service", "systemd-resolved.service", "sshd.service"]:
        src_unit = sysd_src / s
        if src_unit.exists():
            link = root / "etc/systemd/system/multi-user.target.wants" / s
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(f"/usr/lib/systemd/system/{s}")

    # DHCP Network configuration for all ethernet interfaces
    (root / "etc/systemd/network/80-dhcp.network").write_text("""[Match]
Name=en* eth*

[Network]
DHCP=yes
""")

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
ExecStart=-/usr/bin/agetty --autologin root --noclear 115200 %I linux
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
    """Install LFS system configuration files, SSH host keys, user databases, and shell profiles."""
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

    # /etc/resolv.conf
    (root / "etc/resolv.conf").write_text("""nameserver 8.8.8.8
nameserver 1.1.1.1
""")

    # /etc/nsswitch.conf
    (root / "etc/nsswitch.conf").write_text("""passwd:      files
group:       files
shadow:      files
hosts:       files resolve [!UNAVAIL=return] dns
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
sync:x:5:0:sync:/sbin:/bin/sync
shutdown:x:6:0:shutdown:/sbin:/sbin/shutdown
halt:x:7:0:halt:/sbin:/sbin/halt
mail:x:8:12:mail:/var/spool/mail:/bin/false
operator:x:11:0:operator:/root:/bin/false
sshd:x:74:74:Privilege-separated SSH:/usr/share/empty.sshd:/bin/false
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
sync:*:19000:0:99999:7:::
shutdown:*:19000:0:99999:7:::
halt:*:19000:0:99999:7:::
mail:*:19000:0:99999:7:::
operator:*:19000:0:99999:7:::
sshd:*:19000:0:99999:7:::
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
mem:x:8:
kmem:x:9:
wheel:x:10:root
cdrom:x:11:
mail:x:12:
audio:x:63:
video:x:39:
utmp:x:43:
sshd:x:74:
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
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export HOME=/root
export USER=root
export PS1='[\u@\h \W]\$ '
umask 022
cd /root

alias ls='ls --color=auto'
alias ll='ls -la --color=auto'
alias la='ls -A --color=auto'
alias l='ls -CF --color=auto'
alias grep='grep --color=auto'
alias egrep='egrep --color=auto'
alias fgrep='fgrep --color=auto'
""")

    # /root/.bashrc
    (root / "root/.bashrc").write_text(r"""export PS1='[\u@\h \W]\$ '
alias ll='ls -la --color=auto'
alias la='ls -A --color=auto'
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
    (root / "etc/pam.d/sshd").write_text("""#%PAM-1.0
auth        sufficient  pam_permit.so
auth        required    pam_unix.so nullok
account     required    pam_permit.so
password    required    pam_permit.so
session     required    pam_permit.so
""")

    # OpenSSH Server configuration
    ssh_dir = root / "etc/ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    (ssh_dir / "sshd_config").write_text("""Port 22
ListenAddress 0.0.0.0
PermitRootLogin yes
PermitEmptyPasswords yes
PasswordAuthentication yes
ChallengeResponseAuthentication no
UsePAM yes
PrintMotd no
Subsystem sftp /usr/libexec/openssh/sftp-server
""")

    # Pre-generate SSH Host Keys
    for ktype in ["ed25519", "rsa", "ecdsa"]:
        key_file = ssh_dir / f"ssh_host_{ktype}_key"
        if not key_file.exists():
            subprocess.run(
                ["ssh-keygen", "-t", ktype, "-f", str(key_file), "-N", "", "-q"],
                check=False
            )

def build_disk_image():
    """Create a 1.5GB ext4 filesystem disk image using podman unshare for proper root permissions."""
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
    chmod 4755 {ROOTFS_DIR}/usr/bin/su
    chmod 4755 {ROOTFS_DIR}/usr/bin/passwd
    chmod 4755 {ROOTFS_DIR}/usr/bin/ping
    chmod 600 {ROOTFS_DIR}/etc/shadow
    chmod 600 {ROOTFS_DIR}/etc/ssh/*_key 2>/dev/null || true
    chmod 644 {ROOTFS_DIR}/etc/passwd {ROOTFS_DIR}/etc/group
    chmod 664 {ROOTFS_DIR}/var/run/utmp {ROOTFS_DIR}/var/log/wtmp {ROOTFS_DIR}/var/log/lastlog
    chown -R 0:0 {ROOTFS_DIR}
    mke2fs -t ext4 -d {ROOTFS_DIR} -m 0 -F {ROOTFS_IMG} 1500M
    """
    subprocess.check_call(["podman", "unshare", "sh", "-c", cmd])
    print(f"Successfully generated bootable rootfs image: {ROOTFS_IMG}")

def main():
    print("=== MyelinOS Full Headless LFS Bootstrap Starting ===")
    print(f"Target Rootfs Directory: {ROOTFS_DIR}")
    print(f"Target Image:            {ROOTFS_IMG}")
    print(f"Target Kernel:           {KERNEL_DEST}")
    
    create_directory_hierarchy(ROOTFS_DIR)
    install_binaries_and_libs(ROOTFS_DIR)
    install_systemd_units(ROOTFS_DIR)
    install_configuration_files(ROOTFS_DIR)
    build_disk_image()
    print("=== MyelinOS Full Headless LFS Bootstrap Complete ===")

if __name__ == "__main__":
    main()
