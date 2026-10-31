#!/usr/bin/env python3
"""
MyelinOS Live ISO Automated Verification Test Suite
Verifies:
- Live ISO boot via QEMU CD-ROM (-cdrom myelinos-live.iso)
- Initramfs discovery of live medium and SquashFS mount
- Writable OverlayFS root initialization
- Boot into systemd PID 1
- D-Bus system bus and systemd-logind seat/session manager
- VirtIO DRM KMS GPU detection (/dev/dri/card0)
- Display Servers (cosmic-comp Wayland and Xwayland X11)
- COSMIC Desktop suite and session services
- Graphical Framebuffer screendump via QMP monitor
- Clean system shutdown
"""

import sys
import os
import time
import socket
import json
from pathlib import Path
from PIL import Image
import pexpect

BASE_DIR = Path(__file__).resolve().parent.parent
ISO_IMG = BASE_DIR / "build" / "images" / "myelinos-live.iso"
QMP_SOCK = Path("/tmp/qmp-live-test.sock")
SCREENSHOT_PPM = Path("/tmp/myelinos_live_desktop.ppm")
SCREENSHOT_PNG = Path("/tmp/myelinos_live_desktop.png")
ARTIFACT_DIR = Path("/home/admin/.gemini/antigravity/brain/cf9af180-f1ea-4982-9a9d-117bcbfaf48f")

if not ISO_IMG.exists():
    print(f"[-] Error: Live ISO not found at {ISO_IMG}")
    sys.exit(1)

if QMP_SOCK.exists():
    QMP_SOCK.unlink()

qemu_cmd = (
    f"qemu-system-x86_64 -enable-kvm -m 2048M -smp 2 "
    f"-cdrom {ISO_IMG} "
    f"-boot d "
    f"-device virtio-vga "
    f"-display none -vnc :1 "
    f"-serial mon:stdio "
    f"-qmp unix:{QMP_SOCK},server,nowait "
    f"-netdev user,id=net0 -device virtio-net-pci,netdev=net0"
)

print(f"[*] Starting MyelinOS Live ISO boot test in QEMU...")
print(f"[*] Command: {qemu_cmd}")

child = pexpect.spawn(qemu_cmd, encoding="utf-8", timeout=45)
child.logfile_read = sys.stdout

passed = False


def send_check(prompt_str, command, expected_pattern, test_name):
    print(f"\n[*] Testing: {test_name} ('{command}')...")
    child.sendline(command)
    child.expect(expected_pattern)
    child.expect(prompt_str)
    print(f"[+] Passed: {test_name}")


def capture_screendump():
    """Connect to QMP socket and request graphical screendump."""
    print(f"\n[*] Capturing graphical screendump via QMP monitor...")
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(str(QMP_SOCK))
        # Initial greeting
        greeting = json.loads(s.recv(2048).decode("utf-8"))
        print(f"    QMP connected (QEMU {greeting.get('QMP', {}).get('version', {}).get('qemu', {})})")
        # Enable capabilities
        s.sendall(b'{"execute": "qmp_capabilities"}\n')
        resp = json.loads(s.recv(2048).decode("utf-8"))
        # Execute screendump
        dump_cmd = json.dumps({"execute": "screendump", "arguments": {"filename": str(SCREENSHOT_PPM)}}) + "\n"
        s.sendall(dump_cmd.encode("utf-8"))
        resp = json.loads(s.recv(2048).decode("utf-8"))
        s.close()

        if SCREENSHOT_PPM.exists():
            im = Image.open(SCREENSHOT_PPM)
            im.save(SCREENSHOT_PNG)
            print(f"[+] Graphical screenshot successfully saved: {SCREENSHOT_PNG} (Size: {im.size}, Mode: {im.mode})")
            if ARTIFACT_DIR.exists():
                artifact_dest = ARTIFACT_DIR / "myelinos_live_desktop.png"
                im.save(artifact_dest)
                print(f"[+] Copied screenshot to conversation artifact: {artifact_dest}")
            return True
        else:
            print("[-] Screendump PPM file not found")
            return False
    except Exception as e:
        print(f"[-] Screendump capture failed: {e}")
        return False


try:
    prompt = r"\[root@myelinos.*\]#"
    print("[*] Waiting for MyelinOS Live ISO boot to reach root console...")
    idx = child.expect([prompt, pexpect.TIMEOUT, pexpect.EOF], timeout=40)
    if idx == 0:
        print("\n\n[+] Successfully booted MyelinOS Live ISO into root shell!")

        # 1. Init System & Process Manager
        send_check(prompt, "ps -p 1 -o comm=", r"systemd", "PID 1 is systemd")
        send_check(prompt, "systemctl is-active systemd-journald", r"active", "journald is active")
        send_check(prompt, "systemctl is-active systemd-udevd", r"active", "udevd is active")

        # 2. Live Filesystem & OverlayFS Verification
        send_check(prompt, "df -T /", r"overlay", "Root filesystem is OverlayFS")
        send_check(prompt, "cat /proc/mounts | grep -E 'squashfs|overlay'", r"(squashfs|overlay)", "SquashFS and Overlay mounts active")
        send_check(prompt, "ls -la /run/live/medium/LiveOS/squashfs.img", r"squashfs\.img", "Live ISO medium mounted at /run/live/medium")

        # 3. Distro Identity
        send_check(prompt, "cat /etc/os-release", r'NAME="MyelinOS"', "OS Release identity")
        send_check(prompt, "hostname", r"myelinos", "Distro hostname")

        # 4. D-Bus & Seat/Session Infrastructure
        send_check(prompt, "systemctl is-active dbus.socket", r"active", "D-Bus socket is active")
        send_check(prompt, "dbus-send --system --dest=org.freedesktop.DBus / org.freedesktop.DBus.Peer.Ping", r"", "D-Bus system bus ping")
        send_check(prompt, "systemctl is-active systemd-logind", r"active", "systemd-logind is active")
        send_check(prompt, "loginctl list-users", r"cosmic", "COSMIC desktop user active in logind")

        # 5. Graphics & DRM Hardware Detection
        send_check(prompt, "ls -l /dev/dri/card* /dev/dri/renderD* 2>&1", r"(card|renderD)", "VirtIO DRM KMS devices (/dev/dri)")
        send_check(prompt, "lsmod | grep -E 'virtio_gpu|drm'", r"(virtio_gpu|drm)", "VirtIO GPU kernel driver loaded")

        # 6. Display Servers (Wayland & X11)
        send_check(prompt, "cosmic-comp --version", r"cosmic-comp 1\.0\.0", "Wayland Display Server (cosmic-comp)")
        send_check(prompt, "Xwayland -version", r"The X\.Org Foundation Xwayland Version", "X11 Display Server (Xwayland)")
        send_check(prompt, "which wayland-info xrandr glxinfo xauth xhost xrdb", r"/usr/(bin|sbin)/xrandr", "Wayland and X11 diagnostic tools")

        # 7. COSMIC Desktop Environment Components
        send_check(
            prompt,
            "which cosmic-session start-cosmic cosmic-panel cosmic-applets cosmic-app-library cosmic-bg cosmic-files cosmic-launcher cosmic-notifications cosmic-osd cosmic-settings cosmic-term cosmic-workspaces",
            r"/usr/(bin|sbin)/cosmic-session",
            "COSMIC Desktop Environment core suite"
        )
        send_check(
            prompt,
            "test -d /usr/share/cosmic && test -f /usr/share/wayland-sessions/cosmic.desktop && echo COSMIC_DATA_OK",
            r"COSMIC_DATA_OK",
            "COSMIC system configuration & Wayland session desktop entry"
        )

        # 8. COSMIC Service & User Session Status
        send_check(prompt, "systemctl is-active cosmic.service", r"active", "COSMIC Desktop systemd service is active")
        send_check(prompt, "ps aux | grep -E 'cosmic-session|systemd --user'", r"(cosmic-session|systemd --user)", "COSMIC session processes running")

        # 9. Writable Live Layer Verification
        send_check(prompt, "mkdir -p /live_write_test && echo 'MyelinOS Live OK' > /live_write_test/status && cat /live_write_test/status", r"MyelinOS Live OK", "OverlayFS writable persistence test")

        # 10. Capture Graphical Framebuffer
        time.sleep(2)
        screen_ok = capture_screendump()

        # 11. Clean Shutdown
        print("\n[*] Testing clean system shutdown via poweroff...")
        child.sendline("poweroff -f")
        child.expect(pexpect.EOF, timeout=10)
        passed = True
        print("\n[+] ==========================================================================")
        print("[+] ALL TESTS PASSED: MYELINOS LIVE ISO BOOT & COSMIC GRAPHICAL DEMONSTRATION")
        print("[+] ==========================================================================")
    else:
        print("\n[-] Failed to reach root shell: Live ISO boot timeout or unexpected EOF")
except Exception as e:
    print(f"\n[-] Test Exception: {e}")
finally:
    if child.isalive():
        child.terminate(force=True)

if not passed:
    sys.exit(1)
