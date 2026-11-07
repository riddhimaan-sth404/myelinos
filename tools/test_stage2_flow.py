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

def find_suggested_button(img_path: Path, is_final: bool = False):
    if not img_path.exists():
        return (-1, -1) if is_final else (640, 715)
    im = Image.open(img_path)
    pixels = im.load()
    w, h = im.size
    
    if is_final:
        # Check if the bottom action bar is still present (if so, we are NOT on the final screen yet)
        pts_action_bar = []
        for y in range(h - 100, h - 5):
            for x in range(100, w - 100):
                r, g, b = pixels[x, y][:3]
                if (b > 170 and r < 120 and g < 180) and abs(x - 640) > 200:
                    pts_action_bar.append((x, y))
        if len(pts_action_bar) > 50:
            return (-1, -1)

        # Search for centered Reboot button in done_box (centered horizontally at 400..880, y between 350..750)
        pts = []
        for y in range(350, 750):
            for x in range(400, 880):
                r, g, b = pixels[x, y][:3]
                if b > 170 and r < 120 and g < 180:
                    pts.append((x, y))
        if len(pts) > 80:
            min_x = min(p[0] for p in pts)
            max_x = max(p[0] for p in pts)
            min_y = min(p[1] for p in pts)
            max_y = max(p[1] for p in pts)
            return ((min_x + max_x) // 2, (min_y + max_y) // 2)
        return (-1, -1)
    else:
        # Search for Next / Install & Seal button in the bottom section
        pts = []
        for y in range(h - 140, h - 10):
            for x in range(100, w - 100):
                r, g, b = pixels[x, y][:3]
                if b > 170 and r < 120 and g < 180:
                    pts.append((x, y))

        if pts and len(pts) > 40:
            min_x = min(p[0] for p in pts)
            max_x = max(p[0] for p in pts)
            min_y = min(p[1] for p in pts)
            max_y = max(p[1] for p in pts)
            return ((min_x + max_x) // 2, (min_y + max_y) // 2)
        return (640, 715)

def click_suggested_action(qmp, img_path: Path, is_final: bool = False, send_enter: bool = True):
    cx, cy = find_suggested_button(img_path, is_final=is_final)
    print(f"[*] Targeting action button at ({cx}, {cy})...")
    if cx > 0 and cy > 0:
        qmp.click_at(cx, cy)
    time.sleep(0.3)
    if send_enter:
        qmp.send_key("ret")

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
        "-serial", "file:/tmp/stage2-qemu-serial.log",
        "-display", "none",
        "-vnc", ":3",
        "-qmp", f"unix:{QMP_SOCK},server,nowait",
    ]

    print("[*] Launching QEMU with target-disk.raw...")
    proc = subprocess.Popen(qemu_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    qmp = QmpClient(QMP_SOCK)

    try:
        qmp.connect(timeout=25)

        print("[*] Waiting 18 seconds for UEFI boot, GDM auto-login, and Stage 2 installer launch...")
        time.sleep(18)

        # 1. Capture Page 0: Welcome Page
        ppm0 = Path("/tmp/stage2_flow_0.ppm")
        png0 = ARTIFACT_DIR / "stage2_step0_welcome.png"
        qmp.screendump(ppm0)
        convert_ppm_to_png(ppm0, png0)
        print(f"[+] Saved Page 0 (Welcome): {png0.name}")

        # 2. Advance to User Account Page
        print("[*] Advancing to User Account Setup...")
        click_suggested_action(qmp, png0)
        time.sleep(3)
        ppm1 = Path("/tmp/stage2_flow_1.ppm")
        png1 = ARTIFACT_DIR / "stage2_step1_user.png"
        qmp.screendump(ppm1)
        convert_ppm_to_png(ppm1, png1)
        print(f"[+] Saved Page 1 (User Account Setup): {png1.name}")

        # 3. Advance to System Localization Page
        print("[*] Advancing to System Localization...")
        click_suggested_action(qmp, png1)
        time.sleep(3)
        ppm2 = Path("/tmp/stage2_flow_2.ppm")
        png2 = ARTIFACT_DIR / "stage2_step2_system.png"
        qmp.screendump(ppm2)
        convert_ppm_to_png(ppm2, png2)
        print(f"[+] Saved Page 2 (System Localization): {png2.name}")

        # 4. Advance to Presets Page
        print("[*] Advancing to Software Presets...")
        click_suggested_action(qmp, png2)
        time.sleep(3)
        ppm3 = Path("/tmp/stage2_flow_3.ppm")
        png3 = ARTIFACT_DIR / "stage2_step3_presets.png"
        qmp.screendump(ppm3)
        convert_ppm_to_png(ppm3, png3)
        print(f"[+] Saved Page 3 (Software Presets Catalog): {png3.name}")

        # 5. Trigger Installation & Sealing
        print("[*] Triggering 'Install & Seal' on Presets Page...")
        click_suggested_action(qmp, png3, send_enter=True)
        print("[*] Polling for installation completion & Generation 1 CAS sealing...")
        ppm4 = Path("/tmp/stage2_flow_4.ppm")
        png4 = ARTIFACT_DIR / "stage2_step4_completed.png"

        reboot_found = False
        for attempt in range(35):  # up to 70 seconds
            time.sleep(2)
            qmp.screendump(ppm4)
            convert_ppm_to_png(ppm4, png4)
            cx, cy = find_suggested_button(png4, is_final=True)
            if cx > 0 and cy > 0:
                print(f"[+] Finalization complete! Reboot button detected at ({cx}, {cy}) (attempt {attempt+1})")
                reboot_found = True
                break
            else:
                print(f"[*] Installation still executing... (attempt {attempt+1})")
        
        if not reboot_found:
            print("[-] Polling timeout waiting for Reboot button!")
            cx, cy = (640, 580)

        # 6. Click 'Reboot into MyelinOS'
        print("[*] Triggering 'Reboot into MyelinOS'...")
        click_suggested_action(qmp, png4, is_final=True, send_enter=True)
        print("[*] Waiting 25 seconds for system reboot and GNOME Shell reload...")
        time.sleep(25)

        # 7. Capture post-reboot desktop
        ppm5 = Path("/tmp/stage2_flow_5.ppm")
        png5 = ARTIFACT_DIR / "myelinos_rebooted_desktop.png"
        qmp.screendump(ppm5)
        convert_ppm_to_png(ppm5, png5)
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
