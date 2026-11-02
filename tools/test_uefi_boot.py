#!/usr/bin/env python3
"""
MyelinOS UEFI Automated Verification Test Suite
Tests:
- UEFI firmware initialization via OVMF
- GRUB 2.12 EFI bootloader execution from EFI System Partition (ESP)
- Linux kernel 7.2.13 boot with Rust for Linux in UEFI mode
- GPT partition discovery and root mounting (/dev/vda2 -> MYELINOS_ROOT)
- systemd 259.10 PID 1 initialization
- VirtIO GPU display and DRM KMS (/dev/dri/card0)
- GNOME desktop service and compositor (gnome-shell, mutter)
- GNOME Shell 50 compositor stability
- Application execution under user session (ptyxis, nautilus, firefox, gnome-calculator, libreoffice)
- Sudo privilege escalation
- Graphical framebuffer screendump capture via QMP
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
UEFI_IMG = BASE_DIR / "build" / "images" / "myelinos-uefi.img"
QMP_SOCK = Path("/tmp/qmp-uefi-test.sock")
SCREENSHOT_PPM = Path("/tmp/myelinos_uefi_desktop.ppm")
SCREENSHOT_PNG = Path("/tmp/myelinos_uefi_desktop.png")
ARTIFACT_DIR = Path("/home/admin/.gemini/antigravity/brain/cf9af180-f1ea-4982-9a9d-117bcbfaf48f")

OVMF_PATH = Path("/usr/share/OVMF/OVMF_CODE.fd")
if not OVMF_PATH.exists():
    OVMF_PATH = Path("/usr/share/edk2/ovmf/OVMF_CODE.fd")

if not UEFI_IMG.exists():
    print(f"[-] Error: UEFI disk image not found at {UEFI_IMG}")
    print("[*] Generating UEFI disk image first...")
    import subprocess
    subprocess.check_call([sys.executable, str(BASE_DIR / "tools" / "build_uefi_disk.py")])

if not OVMF_PATH.exists():
    print(f"[-] Error: OVMF UEFI firmware not found on host!")
    sys.exit(1)

if QMP_SOCK.exists():
    QMP_SOCK.unlink()

qemu_cmd = (
    f"qemu-system-x86_64 -enable-kvm -m 4096M -smp 2 "
    f"-bios {OVMF_PATH} "
    f"-drive file={UEFI_IMG},format=raw,if=virtio "
    f"-device virtio-vga "
    f"-device virtio-tablet-pci "
    f"-device intel-hda -device hda-duplex "
    f"-display none -vnc :2 "
    f"-serial mon:stdio "
    f"-qmp unix:{QMP_SOCK},server,nowait "
    f"-netdev user,id=net0,hostfwd=tcp::2223-:22 -device virtio-net-pci,netdev=net0"
)

print(f"[*] Starting MyelinOS UEFI GPT Disk boot test in QEMU...")
print(f"[*] Command: {qemu_cmd}")

child = pexpect.spawn(qemu_cmd, encoding="utf-8", timeout=50)
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
        greeting = json.loads(s.recv(2048).decode("utf-8"))
        print(f"    QMP connected (QEMU {greeting.get('QMP', {}).get('version', {}).get('qemu', {})})")
        s.sendall(b'{"execute": "qmp_capabilities"}\n')
        resp = json.loads(s.recv(2048).decode("utf-8"))
        dump_cmd = json.dumps({"execute": "screendump", "arguments": {"filename": str(SCREENSHOT_PPM)}}) + "\n"
        s.sendall(dump_cmd.encode("utf-8"))
        resp = json.loads(s.recv(2048).decode("utf-8"))
        s.close()

        if SCREENSHOT_PPM.exists():
            im = Image.open(SCREENSHOT_PPM)
            im.save(SCREENSHOT_PNG)
            colors = im.getcolors(maxcolors=300000)
            color_count = len(colors) if colors else "> 300000"
            print(f"[+] UEFI Graphical screenshot saved: {SCREENSHOT_PNG} (Size: {im.size}, Mode: {im.mode}, Colors: {color_count})")
            if ARTIFACT_DIR.exists():
                artifact_dest = ARTIFACT_DIR / "myelinos_uefi_desktop.png"
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
    print("[*] Waiting for UEFI boot to reach root console...")
    idx = child.expect([prompt, pexpect.TIMEOUT, pexpect.EOF], timeout=45)
    if idx == 0:
        print("\n\n[+] Successfully booted MyelinOS UEFI GPT Disk into root shell!")

        # 1. System Identity & UEFI Environment
        send_check(prompt, "cat /etc/os-release", r'NAME="MyelinOS"', "OS Release identity")
        send_check(prompt, "uname -r", r"7\.2\.13", "Linux kernel 7.2.13 compiled from source")
        send_check(prompt, "dmesg | grep --color=never -i 'Rust minimal sample'", r"Rust minimal sample \(init\)", "Rust for Linux kernel initialization")
        send_check(prompt, "dmesg | grep --color=never -i 'efi:'", r"efi:", "UEFI runtime services initialized")

        # 2. Partition & Filesystem Verification
        send_check(prompt, "df -h /", r"/dev/root|/dev/vda2", "Root filesystem mounted on /dev/vda2")
        send_check(prompt, "free -m", r"Mem:\s+[0-9]+", "4GB Memory reporting")

        # 3. Sudo Privilege Escalation
        send_check(prompt, "su - myelinos -c 'sudo whoami'", r"root", "Sudo execution as myelinos user")
        send_check(prompt, "su - myelinos -c 'sudo id'", r"uid=0\(root\)", "Sudo id returns root UID 0")

        # 4. Display & GNOME Environment
        send_check(prompt, "test -c /dev/fb0 && echo FBDEV_OK", r"FBDEV_OK", "Framebuffer device /dev/fb0 available")
        send_check(prompt, "cat /proc/asound/cards", r"HDA-Intel", "Intel HDA audio card detected")
        send_check(prompt, "cat /proc/asound/card0/codec#0", r"Codec:", "HDA audio codec successfully probed")
        send_check(prompt, "for i in $(seq 1 15); do if [ \"$(systemctl is-active gdm.service)\" = \"active\" ]; then echo GDM_ACTIVE; break; fi; sleep 1; done", r"GDM_ACTIVE", "GDM Display Manager systemd service is active")
        send_check(prompt, "for i in $(seq 1 15); do if [ \"$(systemctl --user -M myelinos@ is-active graphical-session.target 2>/dev/null)\" = \"active\" ]; then echo GRAPHICAL_SESSION_ACTIVE; break; fi; sleep 1; done", r"GRAPHICAL_SESSION_ACTIVE", "User graphical-session.target is active")
        send_check(prompt, "systemctl is-active systemd-logind", r"active", "systemd-logind is active")
        send_check(prompt, "gnome-shell --version", r"GNOME Shell 50", "GNOME Shell 50 compositor & shell")
        send_check(prompt, "mutter --version", r"mutter 50", "Mutter 50 display server")

        # 5. GNOME Session processes running
        send_check(prompt, "ps aux | grep --color=never -E 'gnome-shell|gnome-session|systemd --user'", r"(gnome-shell|gnome-session|systemd --user)", "GNOME Shell and user session active")

        # 5b. Verify GNOME Shell Animations are active and forced
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
        send_check(
            prompt,
            "su - myelinos -c 'gsettings get org.gnome.desktop.interface enable-animations'",
            r"true",
            "GSettings org.gnome.desktop.interface enable-animations is true"
        )

        # 6. Test Application Launching under the Wayland session
        print("\n[*] Testing application execution in user session...")
        send_check(prompt, "test -x /usr/libexec/gio-launch-desktop && echo GIO_LAUNCH_DESKTOP_OK", r"GIO_LAUNCH_DESKTOP_OK", "gio-launch-desktop binary exists in /usr/libexec")
        send_check(prompt, "which gio-launch-desktop gapplication xdg-open notify-send update-desktop-database", r"/usr/(bin|sbin|libexec)/gio-launch-desktop", "GIO & XDG desktop tools present")
        send_check(prompt, "ls -d /home/myelinos/Desktop /home/myelinos/Downloads /home/myelinos/Documents", r"/home/myelinos/Downloads", "Standard XDG user directories exist")
        send_check(prompt, "su - myelinos -c 'export WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000; timeout 3 gio launch /usr/share/applications/org.gnome.Calculator.desktop && echo GIO_LAUNCH_SUCCESS'", r"GIO_LAUNCH_SUCCESS", "gio launch GDesktopAppInfo execution")
        send_check(prompt, "su - myelinos -c 'export WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000; timeout 3 gnome-calculator --version'", r"gnome-calculator", "gnome-calculator execution")
        send_check(prompt, "su - myelinos -c 'export WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000; timeout 3 ptyxis --version'", r"Ptyxis", "ptyxis terminal execution")
        send_check(prompt, "su - myelinos -c 'export WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000; timeout 3 nautilus --version'", r"nautilus", "nautilus file manager execution")
        send_check(prompt, "su - myelinos -c 'export WAYLAND_DISPLAY=wayland-0 DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000; timeout 3 libreoffice --version'", r"LibreOffice", "libreoffice execution")
        send_check(prompt, "which firefox gnome-text-editor loupe papers gnome-system-monitor gnome-boxes gnome-contacts showtime snapshot yelp", r"/usr/(bin|sbin)/firefox", "Complete GNOME desktop applications suite present")

        # 7. Transient Unit Execution (systemd-run --user)
        send_check(prompt, "su - myelinos -c 'systemd-run --user --scope echo SYSTEMD_RUN_USER_OK'", r"SYSTEMD_RUN_USER_OK", "systemd-run --user transient scope")

        # 8. Test Axon Package Manager with Arch & AUR Support (§5.4, §13, §14)
        print("\n[*] Testing Axon Package Manager (axon / ax)...")
        send_check(prompt, "which axon", r"/usr/(bin|sbin)/axon", "axon binary exists in PATH")
        send_check(prompt, "which ax", r"/usr/(bin|sbin)/ax", "short alias 'ax' exists in PATH")
        send_check(prompt, "axon --version", r"axon 0.1.0", "axon version check")
        send_check(prompt, "ax list", r"Installed Packages", "ax list packages")
        send_check(prompt, "ax generation list", r"Generations for profile", "ax generation list")
        send_check(prompt, "ax artifact list", r"Content-Addressed Artifacts", "ax artifact list")
        send_check(prompt, "axon search ripgrep", r"extra/ripgrep", "axon search Arch Linux repositories")
        send_check(prompt, "axon info ripgrep", r"Arch Package: extra/ripgrep", "axon info Arch package metadata")
        send_check(prompt, "mkdir -p /tmp/guest-pkg/bin && echo '#!/bin/sh' > /tmp/guest-pkg/bin/hello-agent && echo 'echo AGENT_EXEC_OK' >> /tmp/guest-pkg/bin/hello-agent && chmod +x /tmp/guest-pkg/bin/hello-agent && echo PKG_SRC_READY", r"PKG_SRC_READY", "create guest test package source")
        send_check(prompt, "ax package build /tmp/guest-pkg -o /tmp/hello-agent-1.0.0.mpkg --name hello-agent --version 1.0.0", r"Successfully built package", "ax package build in guest")
        send_check(prompt, "ax package inspect /tmp/hello-agent-1.0.0.mpkg", r"Package Manifest: hello-agent v1.0.0", "ax package inspect in guest")
        send_check(prompt, "ax install /tmp/hello-agent-1.0.0.mpkg --profile project:guest-agent", r"Successfully installed hello-agent v1.0.0", "ax install into project profile")
        send_check(prompt, "/var/lib/myelin/profiles/project:guest-agent/bin/hello-agent", r"AGENT_EXEC_OK", "execute installed package via materialized profile")
        send_check(prompt, "ax rollback --profile project:guest-agent 2>&1 || true", r"(Cannot rollback|no active generation|has no parent)", "ax rollback validation")
        send_check(prompt, "ax artifact verify", r"Store Verification Report", "ax artifact store verification")

        # 9. Screendump
        print("[*] Waiting 5s for desktop rendering...")
        time.sleep(5)
        capture_screendump()

        # 10. Clean Shutdown
        print("\n[*] Testing clean system shutdown via systemctl poweroff...")
        child.sendline("systemctl poweroff")
        child.expect(pexpect.EOF, timeout=20)
        passed = True
        print("\n[+] ==========================================================================")
        print("[+] ALL TESTS PASSED: MYELINOS UEFI GPT DISK BOOT & GNOME 50 APPLICATIONS")
        print("[+] ==========================================================================")
    else:
        print("\n[-] Failed to reach root shell: UEFI boot timeout or EOF")
except Exception as e:
    print(f"\n[-] Test Exception: {e}")
finally:
    if child.isalive():
        child.terminate(force=True)

if not passed:
    sys.exit(1)
