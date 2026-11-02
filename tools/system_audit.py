#!/usr/bin/env python3
import sys
import pexpect

cmd = (
    "qemu-system-x86_64 -enable-kvm -m 4096M -smp 2 "
    "-bios /usr/share/OVMF/OVMF_CODE.fd "
    "-drive file=build/images/myelinos-uefi.img,format=raw,if=virtio "
    "-device virtio-vga -device virtio-tablet-pci -device intel-hda -device hda-duplex "
    "-display none -serial stdio -vnc :2 "
    "-netdev user,id=net0 -device virtio-net-pci,netdev=net0"
)

child = pexpect.spawn(cmd, encoding="utf-8", timeout=50)
child.logfile_read = sys.stdout
prompt = r"\[root@myelinos.*\]#"
child.expect(prompt, timeout=40)

def check(c):
    print(f"\n==========================================")
    print(f"AUDIT COMMAND: {c}")
    child.sendline(c)
    child.expect(prompt, timeout=15)
    print(child.before)

# 1. Systemd unit states & failures
check("systemctl --failed --no-pager")
check("systemctl --user --failed --no-pager")
check("systemctl status --no-pager -n 20")

# 2. Mounts & Filesystem Configuration
check("cat /etc/fstab")
check("findmnt /")
check("df -h")

# 3. Kernel warnings and errors
check("dmesg -l emerg,alert,crit,err")

# 4. Networking & DNS
check("ip a")
check("networkctl")
check("cat /etc/resolv.conf")
check("ping -c 2 -W 2 1.1.1.1 || true")

# 5. Audio and multimedia stack
check("ps aux | grep -E 'pipewire|wireplumber|pulseaudio|snd'")
check("ls -la /dev/snd 2>&1")

# 6. Locale and environment
check("locale 2>&1")
check("locale -a 2>&1")

# 7. Desktop logs and errors
check("systemctl get-default")
check("systemctl status gdm.service --no-pager")
check("journalctl -u gdm.service -n 50 --no-pager")
check("journalctl --user -n 50 --no-pager")

# 8. Clean shutdown test (systemctl poweroff vs poweroff -f)
print("\n[*] Testing clean system shutdown via systemctl poweroff...")
child.sendline("systemctl poweroff")
child.expect(pexpect.EOF, timeout=20)
print("\n[+] Audit completed.")
