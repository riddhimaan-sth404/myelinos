#!/usr/bin/env python3
"""
MyelinOS Live ISO Generator
Builds a bootable hybrid (BIOS + UEFI) Live ISO containing:
- Compressed SquashFS root filesystem with COSMIC Desktop Environment & systemd
- Live boot initramfs with overlayfs tmpfs copy-on-write layer
- Linux kernel 7.2.11-200.fc44.x86_64
- GRUB 2 bootloader with auto-boot configuration
"""

import sys
import os
import shutil
import subprocess
import lzma
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ROOTFS_DIR = BASE_DIR / "build" / "bootstrap" / "rootfs"
KERNEL_SRC = BASE_DIR / "build" / "images" / "vmlinuz"
STAGING_DIR = BASE_DIR / "build" / "iso_staging"
IMAGES_DIR = BASE_DIR / "build" / "images"
ISO_OUTPUT = IMAGES_DIR / "myelinos-live.iso"

BUSYBOX_BIN = Path("/home/admin/.local/bin/busybox")
KERNEL_VERSION = "7.2.11-200.fc44.x86_64"
MODULES_DIR = Path(f"/lib/modules/{KERNEL_VERSION}")

INIT_SCRIPT = """#!/bin/sh
export PATH=/bin:/sbin:/usr/bin:/usr/sbin

# 1. Mount pseudo-filesystems
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts
mount -t devpts devpts /dev/pts

echo "=========================================================="
echo "    MyelinOS Live Linux (LFS + systemd + COSMIC)          "
echo "=========================================================="

# 2. Insert kernel modules
for mod in isofs squashfs overlay loop virtio_scsi; do
    if [ -f "/lib/modules/${mod}.ko" ]; then
        insmod "/lib/modules/${mod}.ko" 2>/dev/null || true
    fi
done

sleep 1

# 3. Discover Live Media
echo "[*] Discovering MyelinOS Live media (LABEL=MYELINOS_LIVE)..."
LIVE_DEV=""
mkdir -p /run/live/medium

for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    # Try by filesystem label
    LBL_DEV=$(blkid -L MYELINOS_LIVE 2>/dev/null)
    if [ -n "$LBL_DEV" ] && [ -b "$LBL_DEV" ]; then
        if mount -t iso9660 -o ro "$LBL_DEV" /run/live/medium 2>/dev/null || mount -o ro "$LBL_DEV" /run/live/medium 2>/dev/null; then
            if [ -f /run/live/medium/LiveOS/squashfs.img ]; then
                LIVE_DEV="$LBL_DEV"
                echo "[+] Found Live medium on $LIVE_DEV (by label)"
                break
            fi
            umount /run/live/medium 2>/dev/null || true
        fi
    fi

    # Direct scan of possible block devices
    for dev in /dev/sr0 /dev/sr1 /dev/cdrom /dev/vda /dev/vdb /dev/sda /dev/sdb; do
        if [ -b "$dev" ]; then
            if mount -t iso9660 -o ro "$dev" /run/live/medium 2>/dev/null || mount -o ro "$dev" /run/live/medium 2>/dev/null; then
                if [ -f /run/live/medium/LiveOS/squashfs.img ]; then
                    LIVE_DEV="$dev"
                    echo "[+] Found Live medium on $LIVE_DEV (by probe)"
                    break 2
                fi
                umount /run/live/medium 2>/dev/null || true
            fi
        fi
    done
    sleep 1
done

if [ -z "$LIVE_DEV" ]; then
    echo "[-] FATAL: Failed to find MyelinOS Live media!"
    echo "Dropping to rescue shell..."
    exec /bin/sh
fi

# 4. Mount SquashFS root
echo "[*] Mounting compressed root filesystem..."
mkdir -p /run/live/squashfs
mount -t squashfs -o ro,loop /run/live/medium/LiveOS/squashfs.img /run/live/squashfs

# 5. Initializing OverlayFS with tmpfs
echo "[*] Initializing OverlayFS with tmpfs writable layer..."
mkdir -p /run/live/overlay
mount -t tmpfs -o mode=0755,size=1024M tmpfs /run/live/overlay
mkdir -p /run/live/overlay/upper /run/live/overlay/work
mkdir -p /sysroot
mount -t overlay overlay -o lowerdir=/run/live/squashfs,upperdir=/run/live/overlay/upper,workdir=/run/live/overlay/work /sysroot

# 6. Configure fstab for Live system
cat << 'EOF' > /sysroot/etc/fstab
# MyelinOS Live Overlay Rootfs
overlay / overlay defaults 0 0
tmpfs /tmp tmpfs defaults,nosuid,nodev 0 0
EOF

# 7. Move mount points to sysroot for switch_root
mkdir -p /sysroot/run
mount --move /run /sysroot/run
mount --move /dev /sysroot/dev
mount --move /proc /sysroot/proc
mount --move /sys /sysroot/sys

echo "[+] Initialization complete. Handing over control to systemd..."
exec switch_root /sysroot /usr/lib/systemd/systemd
"""

GRUB_CFG = """# MyelinOS Live GRUB Configuration
set default="0"
set timeout=3

menuentry "MyelinOS Live (COSMIC Desktop & systemd)" {
    linux /boot/vmlinuz root=live:LABEL=MYELINOS_LIVE rd.live.image quiet console=ttyS0 console=tty1 audit=0 selinux=0 enforcing=0
    initrd /boot/initrd.img
}

menuentry "MyelinOS Live (Debug Shell)" {
    linux /boot/vmlinuz root=live:LABEL=MYELINOS_LIVE rd.live.image console=ttyS0 console=tty1 audit=0 selinux=0 enforcing=0 systemd.debug_shell=1
    initrd /boot/initrd.img
}
"""


def check_prerequisites():
    """Verify all build tools, kernel, rootfs, and binaries exist."""
    print("[*] Checking build prerequisites...")
    if not ROOTFS_DIR.exists():
        print(f"[*] Rootfs missing at {ROOTFS_DIR}. Bootstrapping first...")
        subprocess.check_call([sys.executable, str(BASE_DIR / "build" / "bootstrap" / "bootstrap.py")])

    if not KERNEL_SRC.exists():
        raise FileNotFoundError(f"Kernel not found at {KERNEL_SRC}")

    if not BUSYBOX_BIN.exists():
        raise FileNotFoundError(f"Static BusyBox not found at {BUSYBOX_BIN}")

    for tool in ["grub2-mkrescue", "xorriso", "mksquashfs", "cpio", "gzip"]:
        if not shutil.which(tool) and not Path(f"/home/admin/.local/bin/{tool}").exists():
            raise FileNotFoundError(f"Required tool not found: {tool}")
    print("[+] All prerequisites satisfied.")


def build_squashfs(force: bool = False):
    """Compress rootfs into SquashFS with zstd."""
    squashfs_dir = STAGING_DIR / "LiveOS"
    squashfs_dir.mkdir(parents=True, exist_ok=True)
    squashfs_img = squashfs_dir / "squashfs.img"

    if squashfs_img.exists() and not force:
        print(f"[+] Reusing existing SquashFS image: {squashfs_img} ({squashfs_img.stat().st_size / (1024*1024):.1f} MB)")
        return

    print(f"[*] Compressing {ROOTFS_DIR} into {squashfs_img} (zstd)...")
    if squashfs_img.exists():
        squashfs_img.unlink()

    cmd = f"podman unshare mksquashfs {ROOTFS_DIR} {squashfs_img} -comp zstd -processors 2"
    subprocess.check_call(cmd, shell=True)
    size_mb = squashfs_img.stat().st_size / (1024 * 1024)
    print(f"[+] SquashFS image generated: {squashfs_img} ({size_mb:.1f} MB)")


def build_initramfs():
    """Build Live initramfs containing static BusyBox, essential kernel modules, and /init."""
    boot_dir = STAGING_DIR / "boot"
    boot_dir.mkdir(parents=True, exist_ok=True)
    initrd_img = boot_dir / "initrd.img"

    print(f"[*] Constructing Live initramfs -> {initrd_img}...")

    with tempfile.TemporaryDirectory() as td:
        init_root = Path(td)
        # Create directory skeleton
        for d in ["bin", "sbin", "usr/bin", "usr/sbin", "proc", "sys", "dev", "run", "mnt", "sysroot", "lib/modules"]:
            (init_root / d).mkdir(parents=True, exist_ok=True)

        # Copy static Busybox
        dest_busybox = init_root / "bin" / "busybox"
        shutil.copy2(BUSYBOX_BIN, dest_busybox)
        dest_busybox.chmod(0o755)

        # Create Busybox symlinks
        applets = [
            "sh", "bash", "mount", "umount", "mkdir", "rmdir", "switch_root",
            "sleep", "echo", "cat", "ls", "ps", "kill", "mknod", "blkid",
            "modprobe", "insmod", "rmmod", "grep", "sed", "awk", "cut",
            "test", "[", "which", "cp", "mv", "rm", "find", "uname"
        ]
        for app in applets:
            (init_root / "bin" / app).symlink_to("busybox")
            (init_root / "sbin" / app).symlink_to("../bin/busybox")

        # Decompress and install kernel modules
        modules = {
            "isofs": "kernel/fs/isofs/isofs.ko.xz",
            "squashfs": "kernel/fs/squashfs/squashfs.ko.xz",
            "overlay": "kernel/fs/overlayfs/overlay.ko.xz",
            "loop": "kernel/drivers/block/loop.ko.xz",
            "virtio_scsi": "kernel/drivers/scsi/virtio_scsi.ko.xz",
        }
        for name, rel_path in modules.items():
            mod_file = MODULES_DIR / rel_path
            if mod_file.exists():
                decompressed = lzma.decompress(mod_file.read_bytes())
                out_mod = init_root / "lib" / "modules" / f"{name}.ko"
                out_mod.write_bytes(decompressed)
                out_mod.chmod(0o644)
            else:
                print(f"[!] Warning: Kernel module {mod_file} not found")

        # Write /init
        init_file = init_root / "init"
        init_file.write_text(INIT_SCRIPT)
        init_file.chmod(0o755)

        # Pack cpio gzip archive
        pack_cmd = f"find . | cpio -o -H newc | gzip -9 > {initrd_img}"
        subprocess.check_call(pack_cmd, shell=True, cwd=str(init_root))

    size_mb = initrd_img.stat().st_size / (1024 * 1024)
    print(f"[+] Live initramfs generated: {initrd_img} ({size_mb:.2f} MB)")


def setup_boot_files():
    """Copy kernel and write GRUB 2 configuration."""
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
    """Run grub2-mkrescue to build hybrid bootable ISO image."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    if ISO_OUTPUT.exists():
        ISO_OUTPUT.unlink()

    print(f"[*] Generating hybrid Live ISO via grub2-mkrescue -> {ISO_OUTPUT}...")
    cmd = [
        "grub2-mkrescue",
        "-o", str(ISO_OUTPUT),
        str(STAGING_DIR),
        "--",
        "-volid", "MYELINOS_LIVE"
    ]
    subprocess.check_call(cmd)
    size_mb = ISO_OUTPUT.stat().st_size / (1024 * 1024)
    print(f"\n[+] ========================================================")
    print(f"[+] MyelinOS Live ISO successfully built!")
    print(f"[+] Output: {ISO_OUTPUT} ({size_mb:.1f} MB)")
    print(f"[+] Format: Hybrid ISO 9660 (BIOS El Torito + UEFI GPT/MBR)")
    print(f"[+] Volume Label: MYELINOS_LIVE")
    print(f"[+] ========================================================")


def main():
    force = "--force" in sys.argv
    print("=== MyelinOS Live ISO Builder ===")
    check_prerequisites()
    build_squashfs(force=force)
    build_initramfs()
    setup_boot_files()
    generate_iso()


if __name__ == "__main__":
    main()
