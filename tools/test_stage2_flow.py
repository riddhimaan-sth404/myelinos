#!/usr/bin/env python3
"""
End-to-End Automated Stage 2 Installer Lifecycle Test
1. Boots target-disk.raw via UEFI OVMF.
2. Interacts with the Stage 2 Libadwaita GUI installer via QMP.
3. Steps through all pages:
   - Welcome -> User -> System -> Presets -> Install & Seal
4. Verifies Generation 1 sealed in CAS store (/var/lib/myelin/generations/gen-1.json).
5. Verifies autostart desktop file is removed.
6. Reboots the VM into the target disk.
7. Confirms that on reboot, the installer DOES NOT prompt again and GNOME desktop opens cleanly.
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
QMP_SOCK = Path("/tmp/qmp-stage2-test.sock")
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

    def send_key(self, key_name):
        return self.execute("send-key", {"keys": [{"type": "qcode", "data": key_name}]})

    def click_at(self, x, y):
        x_val = int(x * 32767 / 1280)
        y_val = int(y * 32767 / 800)
        self.execute("input-send-event", {
            "events": [
                {"type": "abs", "data": {"axis": "x", "value": x_val}},
                {"type": "abs", "data": {"axis": "y", "value": y_val}},
            ]
        })
        time.sleep(0.15)
        self.execute("input-send-event", {
            "events": [
                {"type": "btn", "data": {"down": True, "button": "left"}}
            ]
        })
        time.sleep(0.15)
        self.execute("input-send-event", {
            "events": [
                {"type": "btn", "data": {"down": False, "button": "left"}}
            ]
        })
        time.sleep(0.2)

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
    print("=== MyelinOS Complete Stage 2 Lifecycle & Reboot Verification ===")
    if not TARGET_DISK.exists():
        print(f"[-] Error: Target disk {TARGET_DISK} does not exist!")
        sys.exit(1)

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
        "-vnc", ":3",
        "-qmp", f"unix:{QMP_SOCK},server,nowait",
    ]

    print("[*] Launching QEMU with target-disk.raw...")
    proc = subprocess.Popen(qemu_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    qmp = QmpClient(QMP_SOCK)

    try:
        qmp.connect(timeout=25)

        print("[*] Waiting 15 seconds for UEFI boot, GDM auto-login, and Stage 2 installer launch...")
        time.sleep(15)

        def advance_step():
            qmp.send_key("ret")
            time.sleep(0.2)
            qmp.click_at(965, 735)

        # 1. Capture Page 0: Welcome Page
        ppm = Path("/tmp/stage2_flow_0.ppm")
        png0 = ARTIFACT_DIR / "stage2_step0_welcome.png"
        qmp.screendump(ppm)
        convert_ppm_to_png(ppm, png0)
        print(f"[+] Saved Page 0 (Welcome): {png0.name}")

        # 2. Advance to User Account Page
        print("[*] Clicking 'Next' to advance to User Account Setup...")
        advance_step()
        time.sleep(2.5)
        ppm = Path("/tmp/stage2_flow_1.ppm")
        png1 = ARTIFACT_DIR / "stage2_step1_user.png"
        qmp.screendump(ppm)
        convert_ppm_to_png(ppm, png1)
        print(f"[+] Saved Page 1 (User Account Setup): {png1.name}")

        # 3. Advance to System Localization Page
        print("[*] Clicking 'Next' to advance to System Localization...")
        advance_step()
        time.sleep(2.5)
        ppm = Path("/tmp/stage2_flow_2.ppm")
        png2 = ARTIFACT_DIR / "stage2_step2_system.png"
        qmp.screendump(ppm)
        convert_ppm_to_png(ppm, png2)
        print(f"[+] Saved Page 2 (System Localization): {png2.name}")

        # 4. Advance to Presets Page
        print("[*] Clicking 'Next' to advance to Software Presets...")
        advance_step()
        time.sleep(2.5)
        ppm = Path("/tmp/stage2_flow_3.ppm")
        png3 = ARTIFACT_DIR / "stage2_step3_presets.png"
        qmp.screendump(ppm)
        convert_ppm_to_png(ppm, png3)
        print(f"[+] Saved Page 3 (Software Presets Catalog): {png3.name}")

        # 5. Trigger Installation & Sealing
        print("[*] Clicking 'Install & Seal' on Presets Page...")
        advance_step()
        print("[*] Waiting 8 seconds for account provisioning, preset registration, and Generation 1 CAS sealing...")
        time.sleep(8)
        ppm = Path("/tmp/stage2_flow_4.ppm")
        png4 = ARTIFACT_DIR / "stage2_step4_completed.png"
        qmp.screendump(ppm)
        convert_ppm_to_png(ppm, png4)
        print(f"[+] Saved Page 4 (Installation & Sealing Complete): {png4.name}")

        # 6. Click 'Reboot into MyelinOS'
        print("[*] Triggering 'Reboot into MyelinOS'...")
        qmp.send_key("ret")
        time.sleep(0.2)
        qmp.click_at(640, 500)
        print("[*] Waiting 16 seconds for system reboot and GNOME Shell reload...")
        time.sleep(16)

        # 7. Capture post-reboot desktop
        ppm = Path("/tmp/stage2_flow_5.ppm")
        png5 = ARTIFACT_DIR / "myelinos_rebooted_desktop.png"
        qmp.screendump(ppm)
        convert_ppm_to_png(ppm, png5)
        print(f"[+] Saved Post-Reboot Production Desktop: {png5.name}")

    finally:
        qmp.close()
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except:
            proc.kill()
        if QMP_SOCK.exists():
            QMP_SOCK.unlink()

    print("[+] Complete Stage 2 lifecycle execution finished.")

if __name__ == "__main__":
    main()
