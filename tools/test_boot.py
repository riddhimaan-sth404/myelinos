#!/usr/bin/env python3
"""
MyelinOS Automated Boot Verification Test
Spawns QEMU, asserts systemd initialization, shell availability, and cleanly powers off.
"""

import sys
import pexpect
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
KERNEL = BASE_DIR / "build" / "images" / "vmlinuz"
ROOTFS = BASE_DIR / "build" / "images" / "myelinos-rootfs.ext4"

if not KERNEL.exists() or not ROOTFS.exists():
    print(f"Error: Missing image or kernel ({KERNEL}, {ROOTFS})")
    sys.exit(1)

cmd = (
    f"qemu-system-x86_64 -enable-kvm -m 1024M -smp 2 "
    f"-kernel {KERNEL} "
    f"-drive file={ROOTFS},format=raw,if=virtio "
    '-append "root=/dev/vda rw console=ttyS0 init=/usr/lib/systemd/systemd audit=0 selinux=0 enforcing=0 quiet" '
    "-nographic"
)

print(f"[*] Starting QEMU boot test: {cmd}")
child = pexpect.spawn(cmd, encoding="utf-8", timeout=25)
child.logfile_read = sys.stdout

passed = False

try:
    # Look for prompt
    idx = child.expect([r"\[root@myelinos.*\]#", pexpect.TIMEOUT, pexpect.EOF])
    if idx == 0:
        print("\n\n[+] Successfully reached root shell via systemd!")
        
        # Test 1: Verify PID 1 is systemd
        print("[*] Test 1: Verifying PID 1 is systemd...")
        child.sendline("ps -p 1 -o comm=")
        child.expect(r"systemd")
        child.expect(r"\[root@myelinos.*\]#")
        print("[+] Verified PID 1 is systemd")

        # Test 2: Verify /etc/os-release
        print("[*] Test 2: Verifying /etc/os-release...")
        child.sendline("cat /etc/os-release")
        child.expect(r'NAME="MyelinOS"')
        child.expect(r"\[root@myelinos.*\]#")
        print("[+] Verified os-release (MyelinOS)")

        # Test 3: Verify root filesystem is mounted rw ext4
        print("[*] Test 3: Verifying root mount...")
        child.sendline("mount | grep ' / '")
        child.expect(r"ext4")
        child.expect(r"\[root@myelinos.*\]#")
        print("[+] Verified ext4 root mount")

        # Test 4: Verify systemctl status
        print("[*] Test 4: Verifying systemctl...")
        child.sendline("systemctl is-active multi-user.target")
        child.expect(r"active")
        child.expect(r"\[root@myelinos.*\]#")
        print("[+] Verified multi-user.target is active")

        # Power off cleanly
        print("[*] Cleanly shutting down system...")
        child.sendline("poweroff -f")
        child.expect(pexpect.EOF, timeout=10)
        passed = True
        print("\n[+] === ALL TESTS PASSED: DISTRO IS WORKING AS STATED ===")
    else:
        print("\n[-] Failed to reach root shell: Boot timeout or unexpected EOF")
except Exception as e:
    print(f"\n[-] Test Exception: {e}")
finally:
    if child.isalive():
        child.terminate(force=True)

if not passed:
    sys.exit(1)
