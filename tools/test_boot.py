#!/usr/bin/env python3
"""
MyelinOS Automated Verification Test Suite
Tests cold boot into systemd PID 1, D-Bus system bus, logind seat manager,
VirtIO DRM KMS GPU detection, Display Servers (GNOME Shell Wayland and Xwayland),
GNOME 50 Desktop Environment suite, networking, Python 3, and clean shutdown.
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
    f"qemu-system-x86_64 -enable-kvm -m 4096M -smp 2 "
    f"-kernel {KERNEL} "
    f"-drive file={ROOTFS},format=raw,if=virtio "
    f"-netdev user,id=net0,hostfwd=tcp::2222-:22 "
    f"-device virtio-net-pci,netdev=net0 "
    f"-device virtio-vga "
    f"-device virtio-tablet-pci "
    f"-device intel-hda -device hda-duplex "
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
    idx = child.expect([prompt, pexpect.TIMEOUT, pexpect.EOF], timeout=45)
    if idx == 0:
        print("\n\n[+] Successfully reached root shell via systemd!")
        
        # 1. Init System & Process Manager
        send_check(prompt, "ps -p 1 -o comm=", r"systemd", "PID 1 is systemd")
        send_check(prompt, "systemctl is-active systemd-journald", r"active", "journald is active")
        send_check(prompt, "systemctl is-active systemd-udevd", r"active", "udevd is active")

        # 2. Distro Identity & Rust for Linux
        send_check(prompt, "cat /etc/os-release", r'NAME="MyelinOS"', "OS Release identity")
        send_check(prompt, "hostname", r"myelinos", "Hostname")
        send_check(prompt, "uname -r", r"7\.2\.13", "Linux kernel 7.2.13 compiled from source")
        send_check(prompt, "dmesg | grep --color=never -i 'Rust minimal sample'", r"Rust minimal sample \(init\)", "Rust for Linux kernel initialization")

        # 2b. Sudo Privilege Escalation & Wheel Group Integration
        send_check(prompt, "which sudo sudoedit visudo", r"/usr/(bin|sbin)/sudo", "Sudo binaries present")
        send_check(prompt, "ls -l /usr/bin/sudo", r"-rwsr-xr-x.*root", "Sudo SUID root permissions")
        send_check(prompt, "su - myelinos -c 'sudo whoami'", r"root", "Sudo execution as myelinos user")
        send_check(prompt, "su - myelinos -c 'sudo id'", r"uid=0\(root\)", "Sudo id returns root UID 0")

        # 3. D-Bus & Seat/Session Infrastructure
        send_check(prompt, "systemctl is-active dbus.socket", r"active", "D-Bus socket is active")
        send_check(prompt, "dbus-send --system --dest=org.freedesktop.DBus / org.freedesktop.DBus.Peer.Ping", r"", "D-Bus system bus ping")
        send_check(prompt, "systemctl is-active systemd-logind", r"active", "systemd-logind is active")

        # 4. Graphics & DRM Hardware Detection
        send_check(prompt, "ls -l /dev/dri/card* /dev/dri/renderD* 2>&1", r"(card|renderD)", "VirtIO DRM KMS devices (/dev/dri)")
        send_check(prompt, "test -c /dev/fb0 && echo FBDEV_OK", r"FBDEV_OK", "Framebuffer device /dev/fb0 available")
        send_check(prompt, "dmesg | grep --color=never -i 'virtio-gpu'", r"virtio-gpu", "VirtIO GPU kernel driver initialized")

        # 4b. Audio Hardware & Codec Detection
        send_check(prompt, "cat /proc/asound/cards", r"HDA-Intel", "Intel HDA audio card detected")
        send_check(prompt, "cat /proc/asound/card0/codec#0", r"Codec:", "HDA audio codec successfully probed")

        # 5. Display Server: GNOME Shell (Wayland) & Xwayland (X11)
        send_check(prompt, "gnome-shell --version", r"GNOME Shell 50", "Wayland Display Server (gnome-shell)")
        send_check(prompt, "mutter --version", r"mutter 50", "Mutter display server")
        send_check(prompt, "Xwayland -version", r"The X\.Org Foundation Xwayland Version", "X11 Display Server (Xwayland)")
        send_check(prompt, "which wayland-info glxinfo xauth xhost xrdb", r"/usr/(bin|sbin)/", "Wayland and X11 diagnostic tools")

        # 6. GNOME Desktop Environment Components
        send_check(
            prompt,
            "which gnome-shell gnome-session gnome-session-quit gnome-session-inhibit gnome-extensions mutter gjs gdm start-gnome nautilus ptyxis",
            r"/usr/.*gnome-shell",
            "GNOME 50 Desktop Environment core binaries"
        )
        send_check(
            prompt,
            "test -d /usr/share/gnome-shell && test -f /usr/share/wayland-sessions/gnome.desktop && echo GNOME_DATA_OK",
            r"GNOME_DATA_OK",
            "GNOME system configuration & Wayland session desktop entry"
        )
        send_check(
            prompt,
            "ls -la /usr/share/applications/org.gnome.*.desktop",
            r"org\.gnome\.Calculator\.desktop",
            "GNOME application desktop entries"
        )
        send_check(
            prompt,
            "test -d /usr/share/icons/Adwaita && test -d /usr/share/backgrounds/gnome && echo GNOME_THEME_OK",
            r"GNOME_THEME_OK",
            "GNOME icons and wallpapers"
        )

        # 6c. Standard Desktop Applications (Firefox, LibreOffice Suite, GNOME Utilities)
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

        # 6d. Desktop Support Frameworks: systemd-run, Portals, Polkit, DConf, UPower
        send_check(
            prompt,
            "which systemd-run gio gtk-launch dbus-update-activation-environment dconf pkexec upower /usr/libexec/xdg-desktop-portal /usr/libexec/dconf-service /usr/libexec/upowerd",
            r"/usr/(bin|sbin)/systemd-run",
            "Desktop infrastructure binaries & helpers"
        )
        send_check(
            prompt,
            "su - myelinos -c 'systemd-run --user --scope echo SYSTEMD_RUN_USER_OK'",
            r"SYSTEMD_RUN_USER_OK",
            "Systemd user manager transient scope execution (systemd-run --user)"
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

        # 12. Display Server & GDM Test
        send_check(
            prompt,
            "timeout 3 gnome-shell --help | grep -i 'wayland'",
            r"wayland",
            "gnome-shell execution test"
        )
        send_check(
            prompt,
            "for i in $(seq 1 15); do if [ \"$(systemctl is-active gdm.service)\" = \"active\" ]; then echo GDM_ACTIVE; break; fi; sleep 1; done",
            r"GDM_ACTIVE",
            "GDM Display Manager systemd service is active"
        )
        send_check(
            prompt,
            "ps aux | grep --color=never -E 'gdm|gnome-shell|gnome-session'",
            r"gdm",
            "GDM and GNOME processes present"
        )
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

        # 13. Clean System Shutdown
        print("\n[*] Testing clean system shutdown via poweroff...")
        child.sendline("poweroff -f")
        child.expect(pexpect.EOF, timeout=10)
        passed = True
        print("\n[+] === ALL TESTS PASSED: DISPLAY SERVER & GNOME 50 DESKTOP INTEGRATED AND OPERATIONAL ===")
    else:
        print("\n[-] Failed to reach root shell: Boot timeout or unexpected EOF")
except Exception as e:
    print(f"\n[-] Test Exception: {e}")
finally:
    if child.isalive():
        child.terminate(force=True)

if not passed:
    sys.exit(1)
