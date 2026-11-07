#!/usr/bin/env python3
import time
import subprocess
import pexpect
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def test_interactive_stage1():
    print("=== Testing Stage 1 Interactive Flow with Pexpect ===")
    cmd = "./run_installer.sh -d --headless --reset-disk"
    child = pexpect.spawn(cmd, encoding="utf-8", timeout=30, cwd=str(BASE_DIR))
    
    try:
        # Step 1: Hardware Audit
        child.expect(r"Continue.*Disk.*Selection", timeout=20)
        print("[+] Detected Step 1 (Hardware Audit). Pressing Enter...")
        time.sleep(1)
        child.send("\r")
        
        # Step 2: Target Storage Device
        child.expect(r"Confirm.*Drive", timeout=15)
        print("[+] Detected Step 2 (Disk Selection). Pressing Enter to confirm /dev/vda...")
        time.sleep(1)
        child.send("\r")
        
        # Step 3: Installation Profile
        child.expect(r"Confirm.*Profile", timeout=15)
        print("[+] Detected Step 3 (Profile Selection). Pressing Enter...")
        time.sleep(1)
        child.send("\r")
        
        # Step 4: Confirmation & Partition Plan
        child.expect(r"START.*INSTALLATION", timeout=15)
        print("[+] Detected Step 4 (Confirmation). Pressing Enter to start installation...")
        time.sleep(1)
        child.send("\r")
        
        # Step 5: Staging & Done
        child.expect(r"Reboot.*System", timeout=45)
        print("[+] Detected Final Screen (Complete). Pressing Enter to trigger REBOOT...")
        time.sleep(1)
        child.send("\r")
        
        # Verify it reboots and exits cleanly
        child.expect("✔ MyelinOS Stage 1 Bootstrap Installer execution finished!", timeout=15)
        print("[+] Verified: Pressing Enter successfully rebooted and finished installer!")
        child.expect(pexpect.EOF, timeout=10)
        print("[+] SUCCESS: Interactive Stage 1 test completed cleanly!")
        return True
    except Exception as e:
        print(f"[-] Interactive Stage 1 test failed: {e}")
        if child.isalive():
            print("Output before error:", child.before)
            child.terminate(force=True)
        return False

if __name__ == "__main__":
    success = test_interactive_stage1()
    exit(0 if success else 1)
