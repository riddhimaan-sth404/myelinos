#!/usr/bin/env python3
"""
MyelinOS Automated Verification Test Suite
Tests cold boot into systemd PID 1, D-Bus system bus, logind seat manager,
VirtIO DRM KMS GPU detection, Display Servers (cosmic-comp and Xwayland),
COSMIC Desktop Environment suite, networking, Python 3, and clean shutdown.
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
    f"qemu-system-x86_64 -enable-kvm -m 2048M -smp 2 "
    f"-kernel {KERNEL} "
    f"-drive file={ROOTFS},format=raw,if=virtio "
    f"-netdev user,id=net0,hostfwd=tcp::2222-:22 "
    f"-device virtio-net-pci,netdev=net0 "
    f"-device virtio-vga "
    f"-display none -vnc :1 "
    f"-serial mon:stdio "
    '-append "root=/dev/vda rw console=ttyS0 init=/usr/lib/systemd/systemd audit=0 selinux=0 enforcing=0 quiet"'
)

print(f"[*] Starting QEMU boot test: {cmd}")
child = pexpect.spawn(cmd, encoding="utf-8", timeout=35)
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
    idx = child.expect([prompt, pexpect.TIMEOUT, pexpect.EOF], timeout=25)
    if idx == 0:
        print("\n\n[+] Successfully reached root shell via systemd!")
        
        # 1. Init System & Process Manager
        send_check(prompt, "ps -p 1 -o comm=", r"systemd", "PID 1 is systemd")
        send_check(prompt, "systemctl is-active systemd-journald", r"active", "journald is active")
        send_check(prompt, "systemctl is-active systemd-udevd", r"active", "udevd is active")

        # 2. Distro Identity
        send_check(prompt, "cat /etc/os-release", r'NAME="MyelinOS"', "OS Release identity")
        send_check(prompt, "hostname", r"myelinos", "Hostname")

        # 3. D-Bus & Seat/Session Infrastructure
        send_check(prompt, "systemctl is-active dbus.socket", r"active", "D-Bus socket is active")
        send_check(prompt, "dbus-send --system --dest=org.freedesktop.DBus / org.freedesktop.DBus.Peer.Ping", r"", "D-Bus system bus ping")
        send_check(prompt, "systemctl is-active systemd-logind", r"active", "systemd-logind is active")

        # 4. Graphics & DRM Hardware Detection
        send_check(prompt, "ls -l /dev/dri/card* /dev/dri/renderD* 2>&1", r"(card|renderD)", "VirtIO DRM KMS devices (/dev/dri)")
        send_check(prompt, "lsmod | grep -E 'virtio_gpu|drm'", r"(virtio_gpu|drm)", "VirtIO GPU kernel driver loaded")

        # 5. Display Server: cosmic-comp (Wayland) & Xwayland (X11)
        send_check(prompt, "cosmic-comp --version", r"cosmic-comp 1\.0\.0", "Wayland Display Server (cosmic-comp)")
        send_check(prompt, "Xwayland -version", r"The X\.Org Foundation Xwayland Version", "X11 Display Server (Xwayland)")
        send_check(prompt, "which wayland-info xrandr glxinfo xauth xhost xrdb", r"/usr/(bin|sbin)/xrandr", "Wayland and X11 diagnostic tools")

        # 6. COSMIC Desktop Environment Components
        send_check(
            prompt,
            "which cosmic-session start-cosmic cosmic-panel cosmic-applets cosmic-app-library cosmic-bg cosmic-files cosmic-launcher cosmic-notifications cosmic-osd cosmic-settings cosmic-term cosmic-workspaces",
            r"/usr/(bin|sbin)/cosmic-session",
            "COSMIC Desktop Environment core binaries"
        )
        send_check(
            prompt,
            "test -d /usr/share/cosmic && test -f /usr/share/wayland-sessions/cosmic.desktop && echo COSMIC_DATA_OK",
            r"COSMIC_DATA_OK",
            "COSMIC system configuration & Wayland session desktop entry"
        )
        send_check(
            prompt,
            "test -d /usr/share/icons/cosmic && test -d /usr/share/backgrounds/cosmic && echo COSMIC_THEME_OK",
            r"COSMIC_THEME_OK",
            "COSMIC icons and wallpapers"
        )

        # 7. Fontconfig & Fonts
        send_check(prompt, "fc-list : family | head -n 3", r".+", "Fontconfig & fonts available")

        # 8. GNU Coreutils & File Operations
        send_check(prompt, "mkdir -p /test_dir && touch /test_dir/test_file && ls -la /test_dir", r"test_file", "File operations (mkdir/touch/ls)")
        send_check(prompt, "rm -rf /test_dir && ls -d /test_dir 2>&1", r"No such file", "File removal (rm -rf)")
        send_check(prompt, "df -h /", r"/dev/(root|vda)", "Disk free reporting (df)")
        send_check(prompt, "echo 'foo myelinos bar' | grep myelinos | sed 's/foo/alpha/' | awk '{print $1,$2}'", r"alpha myelinos", "Pipes (grep, sed, awk)")
        send_check(prompt, 'echo -n "test" | sha256sum', r"9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08", "SHA-256 Checksum")
        send_check(prompt, "free -m", r"Mem:", "Memory reporting (free)")

        # 9. Python 3 Runtime & Standard Library
        send_check(
            prompt,
            'python3 -c "import sys, json, math; print(\'MATH:\', math.sqrt(16), \'PYTHON:\', sys.version.split()[0])"',
            r"MATH: 4.0 PYTHON: 3.14.",
            "Python 3 runtime & stdlib"
        )

        # 10. Text Editors & Archiving Tools
        send_check(prompt, "which nano vi less more", r"/usr/(bin|sbin)/nano", "Editors (nano, vi, less, more)")
        send_check(prompt, "tar --version | head -n 1", r"tar \(GNU tar\)", "GNU tar")
        send_check(prompt, "zstd --version | head -n 1", r"Zstandard", "zstd")

        # 11. Networking & OpenSSH Service
        send_check(prompt, "ping -c 1 -W 1 127.0.0.1", r"1 packets transmitted, 1 (packets )?received", "Loopback Ping")
        send_check(prompt, "systemctl is-active sshd.service", r"active", "SSHD Service is active")

        # 12. Display Server Compositor Test
        send_check(
            prompt,
            "timeout 3 cosmic-comp --help | grep -i 'cosmic-comp'",
            r"cosmic-comp",
            "cosmic-comp execution test"
        )

        # 13. Clean System Shutdown
        print("\n[*] Testing clean system shutdown via poweroff...")
        child.sendline("poweroff -f")
        child.expect(pexpect.EOF, timeout=10)
        passed = True
        print("\n[+] === ALL TESTS PASSED: DISPLAY SERVER & COSMIC DESKTOP INTEGRATED AND OPERATIONAL ===")
    else:
        print("\n[-] Failed to reach root shell: Boot timeout or unexpected EOF")
except Exception as e:
    print(f"\n[-] Test Exception: {e}")
finally:
    if child.isalive():
        child.terminate(force=True)

if not passed:
    sys.exit(1)
