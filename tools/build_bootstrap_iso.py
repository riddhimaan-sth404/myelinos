#!/usr/bin/env python3
"""
MyelinOS Ultra-Lightweight Bootstrap Installer ISO Builder (Stage 1)
Constructs a hybrid UEFI+BIOS bootable ISO image (~25-35 MB) that boots directly
into the Rust Ratatui TUI installer (axon-bootstrap).
"""

import os
import sys
import shutil
import subprocess
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BUILD_DIR = BASE_DIR / "build"
IMAGES_DIR = BUILD_DIR / "images"
KERNEL_SRC = IMAGES_DIR / "vmlinuz"
STAGING_DIR = BUILD_DIR / "bootstrap_iso_staging"
ISO_OUTPUT = IMAGES_DIR / "myelinos-bootstrap.iso"
def get_busybox_path() -> Path:
    candidates = [
        Path("/home/admin/.local/bin/busybox"),
        Path("/usr/bin/busybox"),
        BASE_DIR / "build" / "bootstrap" / "rootfs" / "bin" / "busybox",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError("Static BusyBox binary not found in candidates")

BUSYBOX_BIN = get_busybox_path()
AXON_BOOTSTRAP_BIN = BASE_DIR / "target" / "release" / "axon-bootstrap"

INIT_SCRIPT = """#!/bin/sh
# MyelinOS Stage 1 Bootstrap Installer Init
export PATH=/usr/bin:/usr/sbin:/bin:/sbin
export TERM=xterm-256color

mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev 2>/dev/null || mount -t tmpfs tmpfs /dev
mkdir -p /dev/pts /dev/shm /run /tmp /mnt /boot/efi /run/installer/source /run/installer/medium
mount -t devpts devpts /dev/pts 2>/dev/null || true
mount -t tmpfs tmpfs /run
mount -t tmpfs tmpfs /tmp

# Silence kernel messages from corrupting console TUI
echo 0 > /proc/sys/kernel/printk 2>/dev/null || true
dmesg -n 1 2>/dev/null || true

# Mount live medium if available
if [ -e /dev/sr0 ]; then
    mount -t iso9660 -o ro /dev/sr0 /run/installer/medium 2>/dev/null || true
fi

# Detect console geometry dynamically so TUI fills the full terminal window
resize 2>/dev/null || true
CUR_SIZE=$(stty size 2>/dev/null || echo "")
if [ -z "$CUR_SIZE" ] || [ "$CUR_SIZE" = "0 0" ]; then
    stty cols 128 rows 40 2>/dev/null || true
fi

# Launch the interactive Rust TUI installer with controlling tty
AUTO_FLAG=""
if grep -q -E "(myelin\\.auto|unattended|installer\\.auto)" /proc/cmdline 2>/dev/null; then
    AUTO_FLAG="--auto"
fi

BOOTSTRAP_EXIT=0
if [ -x /bin/axon-bootstrap ]; then
    setsid cttyhack /bin/axon-bootstrap $AUTO_FLAG
    BOOTSTRAP_EXIT=$?
elif [ -x /usr/bin/axon-bootstrap ]; then
    setsid cttyhack /usr/bin/axon-bootstrap $AUTO_FLAG
    BOOTSTRAP_EXIT=$?
else
    echo "[-] Error: axon-bootstrap binary missing!"
    exec /bin/sh
fi

# If automated mode was active OR installer requested reboot (exit code 0)
if [ -n "$AUTO_FLAG" ] || [ "$BOOTSTRAP_EXIT" -eq 0 ]; then
    echo ""
    echo "[+] Rebooting system into target hard drive..."
    sync
    sleep 1
    reboot -f 2>/dev/null || poweroff -f
fi

echo ""
echo "[*] Installation wizard finished. Dropping to rescue shell."
echo "Type 'reboot' to boot into the target disk, or 'poweroff' to halt."
exec setsid cttyhack /bin/sh
"""

GRUB_CFG = """# MyelinOS Bootstrap Installer GRUB Configuration
serial --speed=115200 --unit=0 --word=8 --parity=no --stop=1
terminal_input console serial
terminal_output console serial

set default="0"
set timeout=1

menuentry "Install MyelinOS (Stage 1 TUI Bootstrap - Graphical / VGA)" {
    linux /boot/vmlinuz console=ttyS0 console=tty0 quiet loglevel=0 rd.udev.log_level=0 vt.global_cursor_default=0
    initrd /boot/initrd.img
}

menuentry "Install MyelinOS (Serial Console Headless)" {
    linux /boot/vmlinuz console=tty0 console=ttyS0 quiet loglevel=0 rd.udev.log_level=0 vt.global_cursor_default=0
    initrd /boot/initrd.img
}

menuentry "Install MyelinOS (Automated Stage 1 Bootstrap)" {
    linux /boot/vmlinuz console=ttyS0 console=tty0 myelin.auto=1 quiet loglevel=0 rd.udev.log_level=0 vt.global_cursor_default=0
    initrd /boot/initrd.img
}
"""

def check_prerequisites():
    print("[*] Checking build dependencies...")
    if not KERNEL_SRC.exists():
        raise FileNotFoundError(f"Kernel image not found at {KERNEL_SRC}")
    if not BUSYBOX_BIN.exists():
        raise FileNotFoundError(f"Static BusyBox not found at {BUSYBOX_BIN}")
    for tool in ["grub2-mkrescue", "xorriso", "cpio", "gzip"]:
        if not shutil.which(tool):
            raise FileNotFoundError(f"Required host tool missing: {tool}")
    print("[+] All dependencies satisfied.")

def build_installer_binary():
    print("[*] Building release binary for axon-installer-tui and axon...")
    cmd = ["cargo", "build", "--release", "-p", "axon-installer-tui", "-p", "axon"]
    subprocess.check_call(cmd, cwd=str(BASE_DIR))
    if not AXON_BOOTSTRAP_BIN.exists():
        raise FileNotFoundError(f"Compiled binary missing at {AXON_BOOTSTRAP_BIN}")
    size_kb = AXON_BOOTSTRAP_BIN.stat().st_size / 1024
    print(f"[+] axon-bootstrap binary ready ({size_kb:.1f} KB)")

def build_bootx64_efi(output_path: Path):
    """Build standalone UEFI GRUB 2 EFI application with Btrfs & FAT support."""
    print(f"[*] Building standalone UEFI GRUB 2 bootloader -> {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    modules = [
        "part_gpt", "fat", "btrfs", "ext2", "normal", "boot", "linux",
        "search", "search_fs_file", "search_fs_uuid", "search_label",
        "configfile", "echo", "test", "all_video", "font", "gfxterm",
        "gzio", "reboot", "halt", "zstd"
    ]
    cmd = [
        "grub2-mkimage",
        "-O", "x86_64-efi",
        "-o", str(output_path),
        "-p", "/EFI/BOOT",
        *modules
    ]
    subprocess.check_call(cmd)
    size_kb = output_path.stat().st_size / 1024
    print(f"[+] BOOTX64.EFI ready ({size_kb:.1f} KB)")

def build_initramfs():
    boot_dir = STAGING_DIR / "boot"
    boot_dir.mkdir(parents=True, exist_ok=True)
    initrd_img = boot_dir / "initrd.img"
    print(f"[*] Constructing Bootstrap initramfs -> {initrd_img}...")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for d in ["bin", "sbin", "usr/bin", "usr/sbin", "usr/share/myelin", "lib64", "proc", "sys", "dev", "run", "tmp", "mnt", "etc"]:
            (root / d).mkdir(parents=True, exist_ok=True)
        (root / "lib").symlink_to("lib64")

        # 1. BusyBox & Applets
        shutil.copy2(BUSYBOX_BIN, root / "bin" / "busybox")
        (root / "bin" / "busybox").chmod(0o755)
        for app in [
            "sh", "bash", "mount", "umount", "mkdir", "rmdir", "sleep", "echo",
            "cat", "ls", "ps", "kill", "mknod", "blkid", "grep", "sed", "awk",
            "cp", "mv", "rm", "find", "uname", "sync", "poweroff", "reboot",
            "clear", "reset", "setsid", "cttyhack", "stty", "resize"
        ]:
            (root / "bin" / app).symlink_to("busybox")
            (root / "sbin" / app).symlink_to("../bin/busybox")

        # 2. axon-bootstrap binary
        shutil.copy2(AXON_BOOTSTRAP_BIN, root / "bin" / "axon-bootstrap")
        (root / "bin" / "axon-bootstrap").chmod(0o755)

        # 3. Copy disk and installation tools
        tools_to_copy = ["sfdisk", "parted", "mkfs.vfat", "mkfs.ext4", "mkfs.btrfs", "btrfs", "rsync"]
        for tool_name in tools_to_copy:
            tool_path = shutil.which(tool_name)
            if tool_path and Path(tool_path).exists():
                dest = root / "sbin" / tool_name
                shutil.copy2(tool_path, dest)
                dest.chmod(0o755)
                # Copy dynamic libraries for tool
                try:
                    ldd_out = subprocess.check_output(["ldd", tool_path], text=True)
                    for line in ldd_out.splitlines():
                        if "=>" in line:
                            src_lib = line.split("=>")[1].split("(")[0].strip()
                        elif "/" in line:
                            src_lib = line.split("(")[0].strip()
                        else:
                            continue
                        if os.path.exists(src_lib):
                            lib_name = os.path.basename(src_lib)
                            target_lib = root / "lib64" / lib_name
                            if not target_lib.exists():
                                shutil.copy2(src_lib, target_lib)
                except Exception:
                    pass

        # 4. Copy required shared libraries for axon-bootstrap
        for lib in ["libc.so.6", "libgcc_s.so.1", "ld-linux-x86-64.so.2", "libm.so.6", "libblkid.so.1", "libuuid.so.1"]:
            host_lib = Path("/lib64") / lib
            if host_lib.exists() and not (root / "lib64" / lib).exists():
                shutil.copy2(host_lib, root / "lib64" / lib)

        # 5. Embed UEFI Bootloader, Kernel, and Stage 2 GUI installer
        myelin_share = root / "usr" / "share" / "myelin"
        build_bootx64_efi(myelin_share / "BOOTX64.EFI")
        
        print(f"[*] Embedding kernel {KERNEL_SRC} into initramfs...")
        shutil.copy2(KERNEL_SRC, myelin_share / "vmlinuz")

        gui_script = BASE_DIR / "crates" / "installer" / "gui" / "myelin_installer_gui.py"
        if gui_script.exists():
            print(f"[*] Embedding Stage 2 GUI installer script into initramfs...")
            shutil.copy2(gui_script, myelin_share / "myelin_installer_gui.py")

        axon_bin = BASE_DIR / "target" / "release" / "axon"
        if axon_bin.exists():
            print(f"[*] Embedding axon package manager into initramfs...")
            shutil.copy2(axon_bin, myelin_share / "axon")
            (myelin_share / "axon").chmod(0o755)

        cache_dir = BASE_DIR / "build" / "packages" / "cache"
        if cache_dir.exists():
            dest_cache = myelin_share / "packages"
            dest_cache.mkdir(parents=True, exist_ok=True)
            for pkg in sorted(list(cache_dir.glob("*.pkg.tar.zst")) + list(cache_dir.glob("*.mpkg"))):
                print(f"[*] Embedding cached package {pkg.name} into initramfs...")
                shutil.copy2(pkg, dest_cache / pkg.name)

        # 6. Write /init
        init_file = root / "init"
        init_file.write_text(INIT_SCRIPT)
        init_file.chmod(0o755)

        # 7. Pack initramfs
        pack_cmd = f"find . | cpio -o -H newc | gzip -9 > {initrd_img}"
        subprocess.check_call(pack_cmd, shell=True, cwd=str(root))

    size_mb = initrd_img.stat().st_size / (1024 * 1024)
    print(f"[+] Bootstrap initramfs generated: {initrd_img} ({size_mb:.2f} MB)")

def setup_boot_files():
    boot_dir = STAGING_DIR / "boot"
    grub_dir = boot_dir / "grub"
    grub_dir.mkdir(parents=True, exist_ok=True)

    dest_kernel = boot_dir / "vmlinuz"
    print(f"[*] Copying kernel {KERNEL_SRC} -> {dest_kernel}...")
    shutil.copy2(KERNEL_SRC, dest_kernel)

    grub_cfg = grub_dir / "grub.cfg"
    print(f"[*] Writing GRUB configuration -> {grub_cfg}...")
    grub_cfg.write_text(GRUB_CFG)

def generate_iso():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    if ISO_OUTPUT.exists():
        ISO_OUTPUT.unlink()

    print(f"[*] Generating hybrid bootstrap ISO -> {ISO_OUTPUT}...")
    cmd = [
        "grub2-mkrescue",
        "-o", str(ISO_OUTPUT),
        str(STAGING_DIR),
        "--",
        "-volid", "MYELIN_BOOTSTRAP",
        "-joliet", "on",
    ]
    subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    size_mb = ISO_OUTPUT.stat().st_size / (1024 * 1024)
    print(f"\n[+] ========================================================")
    print(f"[+] MyelinOS Bootstrap Installer ISO successfully generated!")
    print(f"[+] Output: {ISO_OUTPUT} ({size_mb:.1f} MB)")
    print(f"[+] Hybrid Boot: UEFI + BIOS MBR compatible")
    print(f"[+] ========================================================")

def main():
    print("=== MyelinOS Bootstrap Installer ISO Builder ===")
    check_prerequisites()
    build_installer_binary()
    build_initramfs()
    setup_boot_files()
    generate_iso()

if __name__ == "__main__":
    main()
