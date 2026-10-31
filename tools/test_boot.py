#!/usr/bin/env python3
"""
MyelinOS Automated Boot & System Utilities Verification Test
Comprehensive test suite asserting PID 1 systemd, network, coreutils, text processing,
python3 runtime, compression tools, disk utilities, and system shutdown.
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
    f"-netdev user,id=net0,hostfwd=tcp::2222-:22 "
    f"-device virtio-net-pci,netdev=net0 "
    '-append "root=/dev/vda rw console=ttyS0 init=/usr/lib/systemd/systemd audit=0 selinux=0 enforcing=0 quiet" '
    "-nographic"
)

print(f"[*] Starting QEMU boot test: {cmd}")
child = pexpect.spawn(cmd, encoding="utf-8", timeout=30)
child.logfile_read = sys.stdout

passed = False

def send_check(prompt_str, command, expected_pattern, test_name):
    print(f"\n[*] Testing: {test_name} ('{command}')...")
    child.sendline(command)
    child.expect(expected_pattern)
    child.expect(prompt_str)
    print(f"[+] Passed: {test_name}")

try:
    prompt = r"\[root@myelinos.*\]#"
    idx = child.expect([prompt, pexpect.TIMEOUT, pexpect.EOF])
    if idx == 0:
        print("\n\n[+] Successfully reached root shell via systemd!")
        
        # 1. Init System
        send_check(prompt, "ps -p 1 -o comm=", r"systemd", "PID 1 is systemd")
        send_check(prompt, "systemctl is-active multi-user.target", r"active", "multi-user.target is active")
        send_check(prompt, "systemctl is-active systemd-journald", r"active", "journald is active")

        # 2. Distro Identity
        send_check(prompt, "cat /etc/os-release", r'NAME="MyelinOS"', "OS Release identity")
        send_check(prompt, "hostname", r"myelinos", "Hostname")

        # 3. GNU Coreutils & File Operations
        send_check(prompt, "mkdir -p /test_dir && touch /test_dir/test_file && ls -la /test_dir", r"test_file", "File operations (mkdir/touch/ls)")
        send_check(prompt, "rm -rf /test_dir && ls -d /test_dir 2>&1", r"No such file", "File removal (rm -rf)")
        send_check(prompt, "df -h /", r"/dev/(root|vda)", "Disk free reporting (df)")

        # 4. Text Stream Processing (grep, sed, awk)
        send_check(prompt, "echo 'foo myelinos bar' | grep myelinos | sed 's/foo/alpha/' | awk '{print $1,$2}'", r"alpha myelinos", "Pipes (grep, sed, awk)")
        send_check(prompt, 'echo -n "test" | sha256sum', r"9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08", "SHA-256 Checksum")

        # 5. Process & Memory Management
        send_check(prompt, "free -m", r"Mem:", "Memory reporting (free)")
        send_check(prompt, "top -b -n 1 | head -n 5", r"Tasks:", "Process monitor (top)")

        # 6. Python 3 Runtime & Standard Library
        send_check(prompt, 'python3 -c "import sys, json, math; print(\'MATH:\', math.sqrt(16), \'PYTHON:\', sys.version.split()[0])"', r"MATH: 4.0 PYTHON: 3.14.", "Python 3 runtime & stdlib")

        # 7. Archival & Compression Tools
        send_check(prompt, "tar --version | head -n 1", r"tar \(GNU tar\)", "GNU tar")
        send_check(prompt, "gzip --version | head -n 1", r"gzip", "gzip")
        send_check(prompt, "xz --version | head -n 1", r"xz", "xz")
        send_check(prompt, "zstd --version | head -n 1", r"zstd", "zstd")

        # 8. Text Editors & Pagers
        send_check(prompt, "which nano vi less more", r"/usr/(bin|sbin)/nano", "Editors (nano, vi, less, more)")

        # 9. Hardware & Kernel Modules
        send_check(prompt, "lsmod", r"Module", "Kernel module listing (lsmod)")
        send_check(prompt, "lsblk", r"vda", "Block devices (lsblk)")

        # 10. Networking & Services
        send_check(prompt, "ip link show", r"(eth|enp|lo)", "Network interface presence (ip link)")
        send_check(prompt, "ping -c 1 -W 1 127.0.0.1", r"1 packets transmitted, 1 (packets )?received", "Loopback Ping")
        send_check(prompt, "systemctl is-active sshd.service", r"active", "SSHD Service is active")

        # 11. Clean System Shutdown
        print("\n[*] Testing clean system shutdown via poweroff...")
        child.sendline("poweroff -f")
        child.expect(pexpect.EOF, timeout=10)
        passed = True
        print("\n[+] === ALL TESTS PASSED: FULL HEADLESS DISTRO WORKING AS STATED ===")
    else:
        print("\n[-] Failed to reach root shell: Boot timeout or unexpected EOF")
except Exception as e:
    print(f"\n[-] Test Exception: {e}")
finally:
    if child.isalive():
        child.terminate(force=True)

if not passed:
    sys.exit(1)
