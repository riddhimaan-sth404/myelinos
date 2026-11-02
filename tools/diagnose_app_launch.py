#!/usr/bin/env python3
import sys
import pexpect
import time

cmd = (
    "qemu-system-x86_64 -enable-kvm -m 4096M -smp 2 "
    "-kernel /home/admin/MyelinOS/build/images/vmlinuz "
    "-drive file=/home/admin/MyelinOS/build/images/myelinos-rootfs.ext4,format=raw,if=virtio "
    "-device virtio-vga -device virtio-tablet-pci -display none -serial stdio -vnc :1 "
    "-append \"root=/dev/vda rw console=ttyS0 init=/usr/lib/systemd/systemd audit=0 selinux=0 enforcing=0 quiet\""
)

child = pexpect.spawn(cmd, encoding="utf-8", timeout=40)
child.logfile_read = sys.stdout
prompt = r"\[root@myelinos.*\]#"
child.expect(prompt, timeout=30)
print("\n[+] Reached root prompt! Waiting 3s for session stabilization...")
time.sleep(3)

def run_cmd(c):
    print(f"\n>>> RUNNING: {c}")
    child.sendline(c)
    child.expect(prompt, timeout=15)
    print(child.before)

run_cmd("cat /proc/loadavg")
run_cmd("ps aux | grep -E 'gnome|mutter'")

# Check XDG_RUNTIME_DIR and wayland socket
run_cmd("ls -la /run/user/1000")

# Test launching apps as myelinos user under wayland
run_cmd("su - myelinos -c 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 timeout 5 ptyxis --version 2>&1'")
run_cmd("su - myelinos -c 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 timeout 5 nautilus --version 2>&1'")
run_cmd("su - myelinos -c 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 timeout 5 gnome-text-editor --version 2>&1'")
run_cmd("su - myelinos -c 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 timeout 5 firefox --headless --screenshot /tmp/ff_test.png https://localhost 2>&1'")
run_cmd("su - myelinos -c 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 timeout 5 gnome-calculator --version 2>&1'")

# Now test launching via gtk-launch or desktop entry execution
run_cmd("su - myelinos -c 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 timeout 5 gtk-launch org.gnome.Calculator 2>&1'")
run_cmd("su - myelinos -c 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 timeout 5 gtk-launch org.gnome.Ptyxis 2>&1'")
run_cmd("su - myelinos -c 'WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 timeout 5 gtk-launch org.gnome.Nautilus 2>&1'")

# Check user systemd journal and services
run_cmd("journalctl --user -n 40 --no-pager")

# Check gdm service journal
run_cmd("journalctl -u gdm.service -n 40 --no-pager")

child.sendline("poweroff -f")
child.expect(pexpect.EOF, timeout=10)
print("\n[+] Diagnosis finished.")
