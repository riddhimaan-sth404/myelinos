#!/usr/bin/env python3
"""
MyelinOS UEFI GPT Disk Image Generator
Constructs a bootable UEFI GPT hard disk image:
- Partition 1: EFI System Partition (ESP, FAT32, 64 MB)
    - /EFI/BOOT/BOOTX64.EFI (GRUB 2 EFI bootloader)
    - /EFI/BOOT/grub.cfg (Automatic search for MYELINOS_ROOT and boot)
    - /EFI/BOOT/vmlinuz (Dual-boot direct EFI Stub executable)
- Partition 2: Root Filesystem (ext4, ~5.5 GB, labeled MYELINOS_ROOT)
    - Full MyelinOS system with systemd 259.10, GNOME 50 Desktop, and all apps
"""

import sys
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
IMAGES_DIR = BASE_DIR / "build" / "images"
KERNEL_SRC = IMAGES_DIR / "vmlinuz"
ROOTFS_IMG = IMAGES_DIR / "myelinos-rootfs.ext4"
UEFI_DISK_IMG = IMAGES_DIR / "myelinos-uefi.img"

GRUB_CFG = """# MyelinOS UEFI GRUB Configuration
set default="0"
set timeout=3

# Load video drivers for graphical GRUB
insmod efi_gop
insmod efi_uga
insmod font
insmod gfxterm

menuentry "MyelinOS (UEFI GPT + GNOME 50 Desktop)" {
    search --no-floppy --label --set=root MYELINOS_ROOT
    if [ -f ($root)/boot/vmlinuz ]; then
        linux ($root)/boot/vmlinuz root=/dev/vda2 rw console=ttyS0 console=tty1 audit=0 selinux=0 enforcing=0 quiet
    else
        search --no-floppy --label --set=esp ESP
        linux ($esp)/EFI/BOOT/vmlinuz root=/dev/vda2 rw console=ttyS0 console=tty1 audit=0 selinux=0 enforcing=0 quiet
    fi
}

menuentry "MyelinOS (UEFI Direct EFI Stub Kernel - /dev/sda)" {
    search --no-floppy --label --set=esp ESP
    linux ($esp)/EFI/BOOT/vmlinuz root=/dev/sda2 rw console=ttyS0 console=tty1 audit=0 selinux=0 enforcing=0 quiet
}

menuentry "MyelinOS (Debug Shell)" {
    search --no-floppy --label --set=root MYELINOS_ROOT
    if [ -f ($root)/boot/vmlinuz ]; then
        linux ($root)/boot/vmlinuz root=/dev/vda2 rw console=ttyS0 console=tty1 audit=0 selinux=0 enforcing=0 systemd.debug_shell=1
    else
        search --no-floppy --label --set=esp ESP
        linux ($esp)/EFI/BOOT/vmlinuz root=/dev/vda2 rw console=ttyS0 console=tty1 audit=0 selinux=0 enforcing=0 systemd.debug_shell=1
    fi
}
"""


def check_prerequisites():
    """Verify kernel, rootfs, and build tools exist."""
    print("[*] Checking UEFI build prerequisites...")
    if not KERNEL_SRC.exists():
        raise FileNotFoundError(f"Kernel not found at {KERNEL_SRC}")
    if not ROOTFS_IMG.exists():
        raise FileNotFoundError(f"Rootfs image not found at {ROOTFS_IMG}")
    for tool in ["grub2-mkimage", "parted", "mkfs.vfat", "mcopy", "mmd", "truncate", "dd"]:
        if not shutil.which(tool):
            raise FileNotFoundError(f"Required tool not found: {tool}")
    print("[+] All UEFI prerequisites satisfied.")


def build_esp_image(dest_esp: Path):
    """Create FAT32 EFI System Partition containing GRUB EFI and EFI Stub kernel."""
    print(f"[*] Building EFI System Partition (ESP) image -> {dest_esp}...")
    dest_esp.parent.mkdir(parents=True, exist_ok=True)
    if dest_esp.exists():
        dest_esp.unlink()

    # 1. Create 64MB empty FAT32 image
    subprocess.check_call(["truncate", "-s", "64M", str(dest_esp)])
    subprocess.check_call(["mkfs.vfat", "-F", "32", "-n", "ESP", str(dest_esp)], stdout=subprocess.DEVNULL)

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        bootx64_efi = tmp_dir / "BOOTX64.EFI"
        grub_cfg = tmp_dir / "grub.cfg"

        # 2. Build GRUB 2 EFI executable with embedded modules
        grub_modules = [
            "part_gpt", "part_msdos", "fat", "ext2", "normal", "boot",
            "linux", "search", "search_label", "search_fs_uuid", "echo",
            "test", "configfile", "ls", "cat", "reboot", "sleep", "gfxterm",
            "font", "terminfo", "efi_gop", "efi_uga"
        ]
        cmd = [
            "grub2-mkimage",
            "-O", "x86_64-efi",
            "-o", str(bootx64_efi),
            "-p", "/EFI/BOOT",
            *grub_modules
        ]
        print(f"  Generating GRUB EFI application ({bootx64_efi.name})...")
        subprocess.check_call(cmd)

        # 3. Write grub.cfg
        grub_cfg.write_text(GRUB_CFG)

        # 4. Copy files into ESP using mtools
        print("  Populating ESP directory structure...")
        subprocess.check_call(["mmd", "-i", str(dest_esp), "::EFI", "::EFI/BOOT"])
        subprocess.check_call(["mcopy", "-i", str(dest_esp), str(bootx64_efi), "::EFI/BOOT/BOOTX64.EFI"])
        subprocess.check_call(["mcopy", "-i", str(dest_esp), str(grub_cfg), "::EFI/BOOT/grub.cfg"])
        # Also copy kernel for direct EFI stub booting
        subprocess.check_call(["mcopy", "-i", str(dest_esp), str(KERNEL_SRC), "::EFI/BOOT/vmlinuz"])

    print(f"[+] ESP image ready: {dest_esp} (64 MB)")


def assemble_gpt_disk(esp_img: Path):
    """Assemble final GPT disk image containing ESP and Rootfs partitions."""
    print(f"[*] Assembling GPT disk image -> {UEFI_DISK_IMG}...")
    if UEFI_DISK_IMG.exists():
        UEFI_DISK_IMG.unlink()

    # Sizes in MB
    esp_size_mb = 64
    rootfs_size_mb = int(ROOTFS_IMG.stat().st_size / (1024 * 1024)) + 1
    total_size_mb = esp_size_mb + rootfs_size_mb + 10  # 10MB padding for GPT headers

    esp_start_mb = 1
    esp_end_mb = esp_start_mb + esp_size_mb
    rootfs_start_mb = esp_end_mb
    rootfs_end_mb = rootfs_start_mb + rootfs_size_mb

    print(f"  Disk geometry: ESP: {esp_start_mb}MiB-{esp_end_mb}MiB | Rootfs: {rootfs_start_mb}MiB-{rootfs_end_mb}MiB | Total: {total_size_mb}MiB")

    # 1. Truncate disk image
    subprocess.check_call(["truncate", "-s", f"{total_size_mb}M", str(UEFI_DISK_IMG)])

    # 2. Partition with parted
    subprocess.check_call(["parted", "-s", str(UEFI_DISK_IMG), "mklabel", "gpt"])
    subprocess.check_call(["parted", "-s", str(UEFI_DISK_IMG), "mkpart", "ESP", "fat32", f"{esp_start_mb}MiB", f"{esp_end_mb}MiB"])
    subprocess.check_call(["parted", "-s", str(UEFI_DISK_IMG), "set", "1", "esp", "on"])
    subprocess.check_call(["parted", "-s", str(UEFI_DISK_IMG), "mkpart", "MYELINOS_ROOT", "ext4", f"{rootfs_start_mb}MiB", f"{rootfs_end_mb}MiB"])

    # 3. Write ESP partition data
    print("  Writing ESP partition...")
    subprocess.check_call([
        "dd", f"if={esp_img}", f"of={UEFI_DISK_IMG}",
        f"bs=1M", f"seek={esp_start_mb}", "conv=notrunc"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 4. Write Rootfs partition data
    print("  Writing Rootfs partition...")
    subprocess.check_call([
        "dd", f"if={ROOTFS_IMG}", f"of={UEFI_DISK_IMG}",
        f"bs=1M", f"seek={rootfs_start_mb}", "conv=notrunc"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    size_mb = UEFI_DISK_IMG.stat().st_size / (1024 * 1024)
    print(f"\n[+] ========================================================")
    print(f"[+] MyelinOS UEFI GPT Disk Image successfully built!")
    print(f"[+] Output: {UEFI_DISK_IMG} ({size_mb:.1f} MB)")
    print(f"[+] Partition Table: GPT (GUID Partition Table)")
    print(f"[+] Partition 1: EFI System Partition (FAT32, {esp_size_mb} MB, type=esp)")
    print(f"[+] Partition 2: Root Filesystem (ext4, {rootfs_size_mb} MB, label=MYELINOS_ROOT)")
    print(f"[+] Boot Support: Dual-mode (GRUB 2.12 EFI + Linux 7.2.13 EFI Stub)")
    print(f"[+] ========================================================")


def main():
    print("=== MyelinOS UEFI GPT Disk Builder ===")
    check_prerequisites()
    with tempfile.TemporaryDirectory() as td:
        esp_tmp = Path(td) / "esp.img"
        build_esp_image(esp_tmp)
        assemble_gpt_disk(esp_tmp)


if __name__ == "__main__":
    main()
