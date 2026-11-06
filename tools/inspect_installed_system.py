#!/usr/bin/env python3
import sys
import os
import time
import subprocess
from pathlib import Path
import pexpect

BASE_DIR = Path(__file__).resolve().parent.parent
TARGET_DISK = BASE_DIR / "build" / "images" / "target-disk.raw"
OVMF_PATH = Path("/usr/share/OVMF/OVMF_CODE.fd")
if not OVMF_PATH.exists():
    OVMF_PATH = Path("/usr/share/edk2/ovmf/OVMF_CODE.fd")

qemu_cmd = (
    f"qemu-system-x86_64 -enable-kvm -m 4096M -smp 2 "
    f"-bios {OVMF_PATH} "
    f"-drive file={TARGET_DISK},format=raw,if=virtio "
    f"-device virtio-vga "
    f"-display none "
    f"-serial mon:stdio"
)

print("[*] Spawning QEMU to inspect target-disk.raw...")
child = pexpect.spawn(qemu_cmd, encoding="utf-8", timeout=30)

try:
    # Wait for root shell prompt
    child.expect(r"\[root@.*\]#", timeout=25)
    print("[+] Root shell prompt detected! Sending commands...")
    
    child.sendline("cat /var/lib/myelin/generations/gen-1.json")
    child.sendline("which htop tmux rg jq")
    child.sendline("ls -la /var/lib/myelin/profiles/system/bin/")
    child.sendline("echo '=== POWEROFF ==='")
    child.sendline("poweroff")
    
    child.expect(pexpect.EOF, timeout=25)
    print(child.before)

except Exception as e:
    print(f"Inspection error: {e}")
    if child.isalive():
        print("Last output:", child.before)
        child.terminate(force=True)
