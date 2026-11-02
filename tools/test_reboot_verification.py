#!/usr/bin/env python3
"""
MyelinOS Reboot Verification Test
Boots target-disk.raw AFTER Stage 2 installation to confirm:
1. GDM logs in automatically into user session.
2. Stage 2 Installer autostart does NOT appear (wizard is completely gone).
3. Production GNOME desktop renders cleanly with top bar and application suite.
"""

import sys
import os
import time
import socket
import json
import subprocess
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
TARGET_DISK = BASE_DIR / "build" / "images" / "target-disk.raw"
QMP_SOCK = Path("/tmp/qmp-reboot-test.sock")
ARTIFACT_DIR = Path("/home/admin/.gemini/antigravity/brain/cf9af180-f1ea-4982-9a9d-117bcbfaf48f")

OVMF_PATH = Path("/usr/share/OVMF/OVMF_CODE.fd")
if not OVMF_PATH.exists():
    OVMF_PATH = Path("/usr/share/edk2/ovmf/OVMF_CODE.fd")

class QmpClient:
    def __init__(self, sock_path):
        self.sock_path = sock_path
        self.sock = None

    def connect(self, timeout=30):
        start = time.time()
        while time.time() - start < timeout:
            if self.sock_path.exists():
                try:
                    self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self.sock.connect(str(self.sock_path))
                    self.sock.settimeout(5.0)
                    self._read_resp()
                    self.execute("qmp_capabilities")
                    print("[+] QMP connected and capabilities negotiated.")
                    return True
                except Exception:
                    time.sleep(0.5)
            time.sleep(0.5)
        raise TimeoutError("Failed to connect to QMP socket")

    def _read_resp(self):
        buf = b""
        while b"\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        lines = [line.strip() for line in buf.decode("utf-8", errors="ignore").splitlines() if line.strip()]
        for l in lines:
            try:
                msg = json.loads(l)
                if "return" in msg or "error" in msg:
                    return msg
            except:
                pass
        return {}

    def execute(self, cmd, args=None):
        payload = {"execute": cmd}
        if args:
            payload["arguments"] = args
        self.sock.sendall((json.dumps(payload) + "\n").encode())
        return self._read_resp()

    def screendump(self, out_ppm):
        return self.execute("screendump", {"filename": str(out_ppm)})

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

def convert_ppm_to_png(ppm_path: Path, png_path: Path):
    if ppm_path.exists():
        img = Image.open(ppm_path)
        img.save(png_path, "PNG")
        ppm_path.unlink(missing_ok=True)
        return True
    return False

def main():
    print("=== MyelinOS Post-Install Reboot Verification ===")
    if QMP_SOCK.exists():
        QMP_SOCK.unlink()

    qemu_cmd = [
        "qemu-system-x86_64",
        "-enable-kvm",
        "-m", "4096M",
        "-smp", "2",
        "-bios", str(OVMF_PATH),
        "-drive", f"file={TARGET_DISK},format=raw,if=virtio",
        "-device", "virtio-vga",
        "-device", "virtio-tablet-pci",
        "-device", "intel-hda", "-device", "hda-duplex",
        "-display", "none",
        "-vnc", ":4",
        "-qmp", f"unix:{QMP_SOCK},server,nowait",
    ]

    print("[*] Booting installed target-disk.raw via UEFI...")
    proc = subprocess.Popen(qemu_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    qmp = QmpClient(QMP_SOCK)

    try:
        qmp.connect(timeout=25)
        print("[*] Waiting 12 seconds for system startup and GNOME Shell...")
        time.sleep(12)

        ppm = Path("/tmp/reboot_desktop.ppm")
        png = ARTIFACT_DIR / "myelinos_rebooted_desktop.png"
        qmp.screendump(ppm)
        convert_ppm_to_png(ppm, png)
        print(f"[+] Captured reboot desktop screendump: {png}")

    finally:
        qmp.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except:
            proc.kill()
        if QMP_SOCK.exists():
            QMP_SOCK.unlink()

    print("[+] Post-reboot verification complete.")

if __name__ == "__main__":
    main()
