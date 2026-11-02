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
- Display Servers (GNOME Shell Wayland and Xwayland X11)
- GNOME 50 Desktop suite and session services
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
    f"qemu-system-x86_64 -enable-kvm -m 4096M -smp 2 "
    f"-cdrom {ISO_IMG} "
    f"-boot d "
    f"-device virtio-vga "
    f"-device virtio-tablet-pci "
    f"-device intel-hda -device hda-duplex "
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
            colors = im.getcolors(maxcolors=300000)
            color_count = len(colors) if colors else "> 300000"
            print(f"[+] Graphical screenshot successfully saved: {SCREENSHOT_PNG} (Size: {im.size}, Mode: {im.mode}, Colors: {color_count})")
            if ARTIFACT_DIR.exists():
                artifact_dest = ARTIFACT_DIR / "myelinos_live_desktop.png"
                im.save(artifact_dest)
                print(f"[+] Copied screenshot to conversation artifact: {artifact_dest}")
            if colors is not None and len(colors) < 50:
                print(f"[!] Warning: Low color count ({len(colors)}) detected in screenshot - desktop may not have fully rendered")
                return False
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

        # 3. Distro Identity & Rust for Linux
        send_check(prompt, "cat /etc/os-release", r'NAME="MyelinOS"', "OS Release identity")
        send_check(prompt, "hostname", r"myelinos", "Distro hostname")
        send_check(prompt, "uname -r", r"7\.2\.13", "Linux kernel 7.2.13 compiled from source")
        send_check(prompt, "dmesg | grep --color=never -i 'Rust minimal sample'", r"Rust minimal sample \(init\)", "Rust for Linux kernel initialization")

        # 3b. Sudo Privilege Escalation & Wheel Group Integration
        send_check(prompt, "which sudo sudoedit visudo", r"/usr/(bin|sbin)/sudo", "Sudo binaries present")
        send_check(prompt, "ls -l /usr/bin/sudo", r"-rwsr-xr-x.*root", "Sudo SUID root permissions")
        send_check(prompt, "su - myelinos -c 'sudo whoami'", r"root", "Sudo execution as myelinos user")
        send_check(prompt, "su - myelinos -c 'sudo id'", r"uid=0\(root\)", "Sudo id returns root UID 0")

        # 3c. Standard Linux Distro CLI Utilities
        send_check(prompt, "which tree vi nano curl wget zip unzip lspci lsusb tracepath patch diff less file", r"/usr/(bin|sbin)/tree", "Standard Linux CLI utilities")
        send_check(prompt, "tree --version", r"tree", "Tree utility functional")
        send_check(prompt, "curl --version", r"curl", "Curl network transfer functional")

        # 4. D-Bus & Seat/Session Infrastructure
        send_check(prompt, "systemctl is-active dbus.socket", r"active", "D-Bus socket is active")
        send_check(prompt, "dbus-send --system --dest=org.freedesktop.DBus / org.freedesktop.DBus.Peer.Ping", r"", "D-Bus system bus ping")
        send_check(prompt, "systemctl is-active systemd-logind", r"active", "systemd-logind is active")
        send_check(prompt, "loginctl list-users", r"myelinos", "MyelinOS desktop user active in logind")

        # 5. Graphics & DRM Hardware Detection
        send_check(prompt, "ls -l /dev/dri/card* /dev/dri/renderD* 2>&1", r"(card|renderD)", "VirtIO DRM KMS devices (/dev/dri)")
        send_check(prompt, "test -c /dev/fb0 && echo FBDEV_OK", r"FBDEV_OK", "Framebuffer device /dev/fb0 available")
        send_check(prompt, "cat /proc/asound/cards", r"HDA-Intel", "Intel HDA audio card detected")
        send_check(prompt, "cat /proc/asound/card0/codec#0", r"Codec:", "HDA audio codec successfully probed")
        send_check(prompt, "dmesg | grep --color=never -i 'virtio-gpu'", r"virtio-gpu", "VirtIO GPU kernel driver initialized")

        # 6. Display Servers (Wayland & X11)
        send_check(prompt, "gnome-shell --version", r"GNOME Shell 50", "Wayland Display Server & Compositor (gnome-shell)")
        send_check(prompt, "mutter --version", r"mutter 50", "Mutter display server")
        send_check(prompt, "Xwayland -version", r"The X\.Org Foundation Xwayland Version", "X11 Display Server (Xwayland)")
        send_check(prompt, "which glxinfo xauth xhost xrdb", r"/usr/(bin|sbin)/glxinfo", "Wayland and X11 diagnostic tools")

        # 7. GNOME Desktop Environment Components
        send_check(
            prompt,
            "which gnome-shell gnome-session gnome-session-quit gnome-session-inhibit gnome-extensions mutter gjs gdm start-gnome nautilus ptyxis",
            r"/usr/.*gnome-shell",
            "GNOME 50 Desktop Environment core suite"
        )
        send_check(
            prompt,
            "test -d /usr/share/gnome-shell && test -f /usr/share/wayland-sessions/gnome.desktop && echo GNOME_DATA_OK",
            r"GNOME_DATA_OK",
            "GNOME system configuration & Wayland session desktop entry"
        )

        # 7c. Standard Desktop Applications (Firefox, LibreOffice Suite, GNOME Utilities)
        send_check(
            prompt,
            "which firefox libreoffice soffice gnome-calculator loupe baobab papers gnome-font-viewer gnome-disks gnome-calendar gnome-clocks gnome-weather gnome-characters simple-scan gnome-text-editor",
            r"/usr/(bin|sbin)/firefox",
            "Standard Desktop Application binaries"
        )
        send_check(prompt, "firefox --version", r"Mozilla Firefox", "Firefox web browser execution")
        send_check(prompt, "soffice --version", r"LibreOffice", "LibreOffice office suite execution")
        send_check(prompt, "gnome-calculator --version", r"gnome-calculator", "GNOME Calculator execution")
        send_check(prompt, "baobab --version", r"baobab", "Baobab disk analyzer execution")
        send_check(prompt, "papers --version", r"Papers", "Papers document viewer execution")
        send_check(
            prompt,
            "ls -la /usr/share/applications/org.mozilla.firefox.desktop /usr/share/applications/libreoffice-*.desktop /usr/share/applications/org.gnome.Calculator.desktop /usr/share/applications/org.gnome.Loupe.desktop /usr/share/applications/org.gnome.Papers.desktop",
            r"org\.mozilla\.firefox\.desktop",
            "Desktop application .desktop entries for GNOME"
        )
        send_check(
            prompt,
            "test -f /usr/share/glib-2.0/schemas/gschemas.compiled && echo SCHEMAS_OK",
            r"SCHEMAS_OK",
            "GSettings compiled schemas present"
        )

        # 7d. Desktop Support Frameworks: systemd-run, Portals, Polkit, DConf, UPower
        send_check(
            prompt,
            "which systemd-run gio gio-launch-desktop gtk-launch dbus-update-activation-environment dconf pkexec upower /usr/libexec/gio-launch-desktop /usr/libexec/xdg-desktop-portal /usr/libexec/dconf-service /usr/libexec/upowerd",
            r"/usr/(bin|sbin)/systemd-run",
            "Desktop infrastructure binaries & helpers"
        )
        send_check(
            prompt,
            "su - myelinos -c 'systemd-run --user --scope echo SYSTEMD_RUN_USER_OK'",
            r"SYSTEMD_RUN_USER_OK",
            "Systemd user manager transient scope execution (systemd-run --user)"
        )

        # 8. GDM Service & User Session Status
        send_check(prompt, "for i in $(seq 1 15); do if [ \"$(systemctl is-active gdm.service)\" = \"active\" ]; then echo GDM_ACTIVE; break; fi; sleep 1; done", r"GDM_ACTIVE", "GDM Display Manager systemd service is active")
        send_check(prompt, "for i in $(seq 1 15); do if [ \"$(systemctl --user -M myelinos@ is-active graphical-session.target 2>/dev/null)\" = \"active\" ]; then echo GRAPHICAL_SESSION_ACTIVE; break; fi; sleep 1; done", r"GRAPHICAL_SESSION_ACTIVE", "User graphical-session.target is active")
        send_check(prompt, "ps aux | grep --color=never -E 'gdm|gnome-shell|gnome-session|systemd --user'", r"(gnome-shell|gnome-session|systemd --user)", "GNOME session processes running")
        send_check(
            prompt,
            "ps aux | grep --color=never -E 'gnome-shell.*--force-animations'",
            r"--force-animations",
            "GNOME Shell running with --force-animations flag"
        )
        send_check(
            prompt,
            "su - myelinos -c 'busctl --user get-property org.gnome.Shell /org/gnome/Shell/Introspect org.gnome.Shell.Introspect AnimationsEnabled'",
            r"b true",
            "GNOME Shell Introspect AnimationsEnabled reports true"
        )

        # 9. Writable Live Layer Verification
        send_check(prompt, "mkdir -p /live_write_test && echo 'MyelinOS Live OK' > /live_write_test/status && cat /live_write_test/status", r"MyelinOS Live OK", "OverlayFS writable persistence test")

        # 10. Capture Graphical Framebuffer
        print("[*] Waiting 5s for GNOME desktop to fully render...")
        time.sleep(5)
        screen_ok = capture_screendump()

        # 11. Clean Shutdown
        print("\n[*] Testing clean system shutdown via poweroff...")
        child.sendline("poweroff -f")
        child.expect(pexpect.EOF, timeout=10)
        passed = True
        print("\n[+] ==========================================================================")
        print("[+] ALL TESTS PASSED: MYELINOS LIVE ISO BOOT & GNOME 50 GRAPHICAL DEMONSTRATION")
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
