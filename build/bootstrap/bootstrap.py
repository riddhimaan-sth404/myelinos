#!/usr/bin/env python3
"""
MyelinOS Full Linux Distribution Bootstrap with Display Server & GNOME Desktop
Constructs a complete Linux distribution based on Linux From Scratch (LFS) systemd standard.
Includes:
 - systemd init system (PID 1)
 - Full GNU CLI toolchain and system utilities (coreutils, procps-ng, util-linux, e2fsprogs, kmod)
 - Networking (systemd-networkd, systemd-resolved, SSH server, curl, wget, iproute2)
 - Python 3 runtime and standard library
 - Display Server: GNOME Shell / Mutter (Wayland display server & compositor) & Xwayland (X11 display server)
 - Graphics stack: Mesa DRM/KMS virtio-gpu, DRI drivers, Gallium, Vulkan lavapipe/virtio, GBM, EGL
 - Desktop Environment: Mature GNOME 50 Desktop Environment suite
   (gnome-shell, mutter, gnome-session, gdm, gjs, nautilus, ptyxis, gnome-text-editor,
    gnome-calculator, gnome-system-monitor, gnome-control-center, loupe, papers, adwaita)
 - D-Bus system & session message bus and systemd-logind seat/session manager
 - XKB keyboard maps, Fontconfig, and system fonts
"""

import os
import sys
import re
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
BUILD_DIR = BASE_DIR / "build"
ROOTFS_DIR = BUILD_DIR / "bootstrap" / "rootfs"
IMAGES_DIR = BUILD_DIR / "images"
ROOTFS_IMG = IMAGES_DIR / "myelinos-rootfs.ext4"
KERNEL_SRC = BUILD_DIR / "kernel_build" / "linux-7.2.13" / "arch" / "x86" / "boot" / "bzImage"
KERNEL_DEST = IMAGES_DIR / "vmlinuz"
SUDO_PKGS_DIR = BUILD_DIR / "packages" / "sudo"
DESKTOP_PKGS_DIR = BUILD_DIR / "packages" / "desktop_apps"
POLKIT_PKGS_DIR = BUILD_DIR / "packages" / "polkit"

def resolve_deps(binary_path, found_deps=None):
    """Recursively resolve all dynamic library dependencies using ldd."""
    if found_deps is None:
        found_deps = set()
    
    if not os.path.exists(binary_path):
        return found_deps
    
    try:
        env = dict(os.environ)
        # Search extracted lib64 as well
        extra_lib = str(ROOTFS_DIR / "usr/lib64")
        env["LD_LIBRARY_PATH"] = f"{extra_lib}:{env.get('LD_LIBRARY_PATH', '')}"
        out = subprocess.check_output(["ldd", binary_path], stderr=subprocess.DEVNULL, text=True, env=env)
    except Exception:
        return found_deps
    
    for line in out.splitlines():
        line = line.strip()
        if "=>" in line:
            parts = line.split("=>")
            right = parts[1].strip().split()[0]
            if right.startswith("/") and os.path.exists(right):
                if right not in found_deps:
                    found_deps.add(right)
                    resolve_deps(right, found_deps)
        elif line.startswith("/"):
            left = line.split()[0]
            if os.path.exists(left):
                if left not in found_deps:
                    found_deps.add(left)
                    resolve_deps(left, found_deps)
    return found_deps

def create_directory_hierarchy(root: Path):
    """Create standard LFS filesystem hierarchy (FHS 3.0 / UsrMerge)."""
    if root.exists():
        subprocess.run(["podman", "unshare", "rm", "-rf", str(root)], check=True)

    dirs = [
        "usr/bin", "usr/lib", "usr/lib64", "usr/lib64/dri", "usr/lib64/security",
        "usr/lib64/gnome-shell", "usr/lib64/mutter-18", "usr/lib64/girepository-1.0",
        "usr/lib/systemd/system", "usr/lib/systemd/system-generators",
        "usr/lib/systemd/network", "usr/lib/systemd/user",
        "usr/local/bin", "usr/local/lib", "usr/local/lib/systemd/system",
        "usr/share/terminfo", "usr/share/nano", "usr/share/vim", "usr/share/empty.sshd",
        "usr/share/gnome-shell", "usr/share/gnome-session", "usr/share/gdm",
        "usr/share/wayland-sessions", "usr/share/xsessions", "usr/share/applications",
        "usr/share/icons", "usr/share/fonts", "usr/share/X11", "usr/share/vulkan/icd.d",
        "usr/share/drirc.d", "usr/share/glvnd", "usr/share/dbus-1", "usr/share/hwdata",
        "usr/libexec/openssh", "usr/libexec/sudo",
        "etc/systemd/system", "etc/systemd/system/multi-user.target.wants",
        "etc/systemd/system/graphical.target.wants",
        "etc/systemd/system/sysinit.target.wants", "etc/systemd/system/getty.target.wants",
        "etc/systemd/system/sockets.target.wants",
        "etc/systemd/network", "etc/udev/rules.d",
        "etc/pam.d", "etc/selinux", "etc/ssh", "etc/ssl/certs", "etc/pki/tls/certs",
        "etc/dbus-1", "etc/fonts", "etc/gdm", "etc/sudoers.d",
        "dev", "dev/dri", "dev/input", "proc", "sys", "sys/fs/cgroup",
        "run", "run/systemd", "run/systemd/seats", "run/lock", "run/dbus", "run/sudo", "run/user/0", "run/user/1000", "run/user/42",
        "tmp", "tmp/.X11-unix", "root", "home", "home/myelinos", "mnt", "opt",
        "var/log", "var/tmp", "var/lib/systemd", "var/empty/sshd", "var/run/dbus", "var/db/sudo",
        "var/lib/gdm", "var/lib/AccountsService"
    ]
    for d in dirs:
        (root / d).mkdir(parents=True, exist_ok=True)

    # Standard UsrMerge and LFS compatibility symlinks
    symlinks = [
        ("bin", "usr/bin"),
        ("sbin", "usr/bin"),
        ("lib", "usr/lib"),
        ("lib64", "usr/lib64"),
        ("usr/sbin", "bin"),
        ("usr/local/sbin", "bin"),
        ("var/run", "../run"),
        ("var/lock", "../run/lock"),
        ("etc/mtab", "/proc/self/mounts"),
    ]
    for link, target in symlinks:
        link_path = root / link
        if link_path.exists() or link_path.is_symlink():
            if link_path.is_dir() and not link_path.is_symlink():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
        link_path.symlink_to(target)

    # /usr/bin/init -> ../lib/systemd/systemd
    init_symlink = root / "usr/bin/init"
    if not init_symlink.exists():
        init_symlink.symlink_to("../lib/systemd/systemd")

def extract_sudo_packages(root: Path):
    """Ensure sudo RPM is downloaded, unpacked, and installed into rootfs."""
    SUDO_PKGS_DIR.mkdir(parents=True, exist_ok=True)
    rpms = list(SUDO_PKGS_DIR.glob("*.rpm"))
    if not rpms:
        print("[*] Downloading sudo package...")
        subprocess.check_call(["dnf", "download", "--destdir", str(SUDO_PKGS_DIR), "sudo"])
        rpms = list(SUDO_PKGS_DIR.glob("*.rpm"))

    print("Extracting sudo package into rootfs...")
    staging = BUILD_DIR / "bootstrap" / "sudo_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    for rpm_file in rpms:
        cmd = f"rpm2cpio '{rpm_file}' | (cd '{staging}' && cpio -idu 2>/dev/null)"
        subprocess.check_call(cmd, shell=True)

    # Ensure user has read/write permissions on extracted files
    subprocess.run(["chmod", "-R", "u+rw", str(staging)], check=True)

    # Copy binaries (/usr/bin and /usr/sbin)
    for bin_dir in ["usr/bin", "usr/sbin"]:
        if (staging / bin_dir).exists():
            for item in (staging / bin_dir).iterdir():
                dest = root / "usr/bin" / item.name
                if dest.exists() or dest.is_symlink():
                    dest.unlink()
                if item.is_symlink():
                    dest.symlink_to(os.readlink(item))
                else:
                    shutil.copy2(item, dest)

    # Copy /usr/libexec/sudo
    if (staging / "usr/libexec/sudo").exists():
        shutil.copytree(staging / "usr/libexec/sudo", root / "usr/libexec/sudo", dirs_exist_ok=True)

    # Copy /etc/sudo.conf
    if (staging / "etc/sudo.conf").exists():
        shutil.copy2(staging / "etc/sudo.conf", root / "etc/sudo.conf")

    # Cleanup staging directory
    shutil.rmtree(staging, ignore_errors=True)
    print("Sudo package extracted successfully.")

def extract_desktop_packages(root: Path):
    """Extract all desktop application RPM packages (Evince, LibreOffice Base/Draw/Math) into rootfs."""
    rpms = sorted(list(DESKTOP_PKGS_DIR.glob("*.rpm")))
    if not rpms:
        print("No RPMs found in desktop packages directory.")
        return
    print(f"Extracting {len(rpms)} desktop application RPM packages into rootfs...")
    staging = BUILD_DIR / "bootstrap" / "desktop_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    for rpm_file in rpms:
        cmd = f"rpm2cpio '{rpm_file}' | (cd '{staging}' && cpio -idu 2>/dev/null)"
        subprocess.check_call(cmd, shell=True)

    # Ensure user has read/write permissions on extracted files
    subprocess.run(["chmod", "-R", "u+rw", str(staging)], check=True)

    # Sync staging into rootfs
    for sub in ["usr/bin", "usr/sbin", "usr/lib64", "usr/libexec", "usr/share", "usr/lib/systemd", "etc"]:
        src_sub = staging / sub
        if src_sub.exists():
            dest_sub = root / sub
            dest_sub.parent.mkdir(parents=True, exist_ok=True)
            if src_sub.is_dir():
                shutil.copytree(src_sub, dest_sub, dirs_exist_ok=True)

    # Cleanup staging directory
    shutil.rmtree(staging, ignore_errors=True)
    print("Desktop application packages extracted successfully.")

def extract_polkit_packages(root: Path):
    """Ensure polkit RPM is downloaded, unpacked, and installed into rootfs."""
    POLKIT_PKGS_DIR.mkdir(parents=True, exist_ok=True)
    rpms = list(POLKIT_PKGS_DIR.glob("*.rpm"))
    if not rpms:
        print("[*] Downloading polkit packages...")
        subprocess.check_call(["dnf", "download", "--destdir", str(POLKIT_PKGS_DIR), "polkit", "polkit-libs"])
        for p in POLKIT_PKGS_DIR.glob("*i686*.rpm"):
            p.unlink()
        rpms = list(POLKIT_PKGS_DIR.glob("*.rpm"))

    print("Extracting polkit packages into rootfs...")
    staging = BUILD_DIR / "bootstrap" / "polkit_staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    for rpm_file in rpms:
        cmd = f"rpm2cpio '{rpm_file}' | (cd '{staging}' && cpio -idu 2>/dev/null)"
        subprocess.check_call(cmd, shell=True)

    # Ensure user has read/write permissions on extracted files
    subprocess.run(["chmod", "-R", "u+rw", str(staging)], check=True)

    # Copy files
    for sub in ["usr/bin", "usr/sbin", "usr/lib64", "usr/lib/polkit-1", "usr/lib/systemd/system", "usr/share", "etc"]:
        src_sub = staging / sub
        if src_sub.exists():
            dest_sub = root / sub
            dest_sub.parent.mkdir(parents=True, exist_ok=True)
            if src_sub.is_dir():
                shutil.copytree(src_sub, dest_sub, dirs_exist_ok=True)
            else:
                shutil.copy2(src_sub, dest_sub)

    # Copy host polkit action files if available
    host_actions = Path("/usr/share/polkit-1/actions")
    if host_actions.exists():
        dest_actions = root / "usr/share/polkit-1/actions"
        dest_actions.mkdir(parents=True, exist_ok=True)
        shutil.copytree(host_actions, dest_actions, dirs_exist_ok=True)

    # Universal polkit rule for root, myelinos desktop user, wheel, and gdm
    rules_dir = root / "etc/polkit-1/rules.d"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "49-wheel.rules").write_text("""polkit.addRule(function(action, subject) {
    if (subject.user === "root" || subject.user === "myelinos" || subject.isInGroup("wheel") || subject.isInGroup("gdm")) {
        return polkit.Result.YES;
    }
});
""")

    # Cleanup staging directory
    shutil.rmtree(staging, ignore_errors=True)
    print("Polkit packages extracted successfully.")

def install_graphics_and_desktop_assets(root: Path):
    """Install Mesa DRI drivers, Vulkan ICDs, XKB data, fonts, and D-Bus configs."""
    print("Installing graphics stack, DRI drivers, XKB, and font assets...")
    
    # 1. Mesa DRI drivers & GBM backends
    if Path("/usr/lib64/dri").exists():
        shutil.copytree("/usr/lib64/dri", root / "usr/lib64/dri", dirs_exist_ok=True)
    if Path("/usr/lib64/gbm").exists():
        shutil.copytree("/usr/lib64/gbm", root / "usr/lib64/gbm", dirs_exist_ok=True)

    # 1b. Udev rules, hardware database, and device helpers
    if Path("/usr/lib/udev").exists():
        shutil.copytree("/usr/lib/udev", root / "usr/lib/udev", dirs_exist_ok=True)

    # 2. Mesa Gallium, GBM, EGL, GL, Vulkan libraries
    for p in Path("/usr/lib64").glob("libgallium*.so*"):
        shutil.copy2(p, root / "usr/lib64" / p.name)
    for p in Path("/usr/lib64").glob("libgbm*.so*"):
        shutil.copy2(p, root / "usr/lib64" / p.name)
    for p in Path("/usr/lib64").glob("libEGL*.so*"):
        shutil.copy2(p, root / "usr/lib64" / p.name)
    for p in Path("/usr/lib64").glob("libGL*.so*"):
        shutil.copy2(p, root / "usr/lib64" / p.name)
    for p in Path("/usr/lib64").glob("libGLESv2*.so*"):
        shutil.copy2(p, root / "usr/lib64" / p.name)
    for p in Path("/usr/lib64").glob("libglapi*.so*"):
        shutil.copy2(p, root / "usr/lib64" / p.name)
    for p in Path("/usr/lib64").glob("libvulkan*.so*"):
        shutil.copy2(p, root / "usr/lib64" / p.name)
    for p in Path("/usr/lib64").glob("libdrm*.so*"):
        shutil.copy2(p, root / "usr/lib64" / p.name)
    for p in Path("/usr/lib64").glob("libwayland*.so*"):
        shutil.copy2(p, root / "usr/lib64" / p.name)
    for p in Path("/usr/lib64").glob("libxkbcommon*.so*"):
        shutil.copy2(p, root / "usr/lib64" / p.name)
    for p in Path("/usr/lib64").glob("libX11*.so*"):
        shutil.copy2(p, root / "usr/lib64" / p.name)

    # Unversioned dlopen symlinks for desktop components
    for base, target in [
        ("libwayland-client.so", "libwayland-client.so.0"),
        ("libwayland-server.so", "libwayland-server.so.0"),
        ("libwayland-cursor.so", "libwayland-cursor.so.0"),
        ("libwayland-egl.so", "libwayland-egl.so.1"),
        ("libxkbcommon.so", "libxkbcommon.so.0"),
        ("libxkbcommon-x11.so", "libxkbcommon-x11.so.0"),
        ("libX11.so", "libX11.so.6"),
        ("libX11-xcb.so", "libX11-xcb.so.1"),
    ]:
        sym = root / "usr/lib64" / base
        if sym.exists() or sym.is_symlink():
            sym.unlink()
        sym.symlink_to(target)

    # 3. Vulkan ICD configuration
    if Path("/usr/share/vulkan/icd.d").exists():
        shutil.copytree("/usr/share/vulkan/icd.d", root / "usr/share/vulkan/icd.d", dirs_exist_ok=True)

    # 4. XKB keyboard configuration
    if Path("/usr/share/xkeyboard-config-2").exists():
        shutil.copytree("/usr/share/xkeyboard-config-2", root / "usr/share/xkeyboard-config-2", dirs_exist_ok=True)
    xkb_link = root / "usr/share/X11/xkb"
    if xkb_link.exists() or xkb_link.is_symlink():
        xkb_link.unlink()
    xkb_link.symlink_to("../xkeyboard-config-2")

    # 5. Mesa / GL configs
    if Path("/usr/share/drirc.d").exists():
        shutil.copytree("/usr/share/drirc.d", root / "usr/share/drirc.d", dirs_exist_ok=True)
    if Path("/usr/share/glvnd").exists():
        shutil.copytree("/usr/share/glvnd", root / "usr/share/glvnd", dirs_exist_ok=True)

    # 6. Fonts and Fontconfig
    if Path("/etc/fonts").exists():
        shutil.copytree("/etc/fonts", root / "etc/fonts", dirs_exist_ok=True)
    if Path("/usr/share/fonts").exists():
        shutil.copytree("/usr/share/fonts", root / "usr/share/fonts", dirs_exist_ok=True)
    if Path("/usr/share/icons/hicolor").exists():
        shutil.copytree("/usr/share/icons/hicolor", root / "usr/share/icons/hicolor", dirs_exist_ok=True)

    # 7. D-Bus configs
    if Path("/etc/dbus-1").exists():
        shutil.copytree("/etc/dbus-1", root / "etc/dbus-1", dirs_exist_ok=True)
    if Path("/usr/share/dbus-1").exists():
        shutil.copytree("/usr/share/dbus-1", root / "usr/share/dbus-1", dirs_exist_ok=True)

    # 8. Hardware database for lspci / lsusb
    if Path("/usr/share/hwdata").exists():
        shutil.copytree("/usr/share/hwdata", root / "usr/share/hwdata", dirs_exist_ok=True)

    # 9. PipeWire, WirePlumber, and audio runtime assets
    for pw_dir in ["/usr/lib64/pipewire-0.3", "/usr/lib64/spa-0.2", "/usr/lib64/wireplumber-0.5"]:
        p = Path(pw_dir)
        if p.exists():
            shutil.copytree(p, root / pw_dir.lstrip("/"), dirs_exist_ok=True)
    for pw_share in ["/usr/share/pipewire", "/usr/share/wireplumber", "/etc/pipewire", "/etc/wireplumber"]:
        p = Path(pw_share)
        if p.exists():
            shutil.copytree(p, root / pw_share.lstrip("/"), dirs_exist_ok=True)

    # 10. Glibc locale archive and locale binaries
    if Path("/usr/lib/locale/locale-archive").exists():
        (root / "usr/lib/locale").mkdir(parents=True, exist_ok=True)
        shutil.copy2("/usr/lib/locale/locale-archive", root / "usr/lib/locale/locale-archive")

    # 11. DConf database
    if Path("/etc/dconf").exists():
        shutil.copytree("/etc/dconf", root / "etc/dconf", dirs_exist_ok=True)

def install_gnome_desktop(root: Path, all_libs: set):
    """Install GNOME 50 desktop environment: Shell, Mutter, GDM, GJS, extensions, schemas, and assets."""
    print("Installing GNOME 50 desktop environment (GNOME Shell, Mutter, GDM, GJS, Schemas)...")

    # 1. Mutter private libraries and typelibs
    if Path("/usr/lib64/mutter-18").exists():
        print("  Installing Mutter 18 runtime and typelibs...")
        shutil.copytree("/usr/lib64/mutter-18", root / "usr/lib64/mutter-18", dirs_exist_ok=True)
        for f in (root / "usr/lib64/mutter-18").glob("*.so*"):
            if not f.is_symlink():
                resolve_deps(str(f), all_libs)

    # 2. GNOME Shell private libraries and typelibs
    if Path("/usr/lib64/gnome-shell").exists():
        print("  Installing GNOME Shell runtime and typelibs...")
        shutil.copytree("/usr/lib64/gnome-shell", root / "usr/lib64/gnome-shell", dirs_exist_ok=True)
        for f in (root / "usr/lib64/gnome-shell").glob("*.so*"):
            if not f.is_symlink():
                resolve_deps(str(f), all_libs)

    # 2b. TinySPARQL & LocalSearch private libraries and modules (required by Nautilus and GNOME search)
    for tracker_lib in ["/usr/lib64/tinysparql-3.0", "/usr/lib64/localsearch-3.0"]:
        if Path(tracker_lib).exists():
            print(f"  Installing {tracker_lib} modules...")
            shutil.copytree(tracker_lib, root / tracker_lib.lstrip("/"), dirs_exist_ok=True)
            for f in (root / tracker_lib.lstrip("/")).rglob("*.so*"):
                if not f.is_symlink():
                    resolve_deps(str(f), all_libs)

    # 2c. GJS private libraries and typelibs (/usr/lib64/gjs)
    if Path("/usr/lib64/gjs").exists():
        print("  Installing GJS private typelibs (GjsPrivate)...")
        shutil.copytree("/usr/lib64/gjs", root / "usr/lib64/gjs", dirs_exist_ok=True)
        gjs_typelib = Path("/usr/lib64/gjs/girepository-1.0/GjsPrivate-1.0.typelib")
        if gjs_typelib.exists():
            (root / "usr/lib64/girepository-1.0").mkdir(parents=True, exist_ok=True)
            shutil.copy2(gjs_typelib, root / "usr/lib64/girepository-1.0/GjsPrivate-1.0.typelib")

    # 3. GObject Introspection typelibs (/usr/lib64/girepository-1.0)
    if Path("/usr/lib64/girepository-1.0").exists():
        print("  Installing GObject Introspection typelibs...")
        shutil.copytree("/usr/lib64/girepository-1.0", root / "usr/lib64/girepository-1.0", dirs_exist_ok=True)

    # 3b. Resolve all shared libraries referenced inside GObject typelibs
    print("  Resolving runtime libraries referenced by GObject typelibs...")
    typelib_files = list(root.glob("usr/lib64/**/*.typelib"))
    for tf in typelib_files:
        try:
            with open(tf, "rb") as f:
                content = f.read()
            for m in re.findall(rb'lib[a-zA-Z0-9_.-]+\.so(?:\.[0-9]+)*', content):
                lib_name = m.decode('latin1')
                for search_dir in ["/usr/lib64", "/lib64"]:
                    cand = Path(search_dir) / lib_name
                    if cand.exists():
                        all_libs.add(str(cand))
                        if cand.is_symlink():
                            all_libs.add(str(cand.resolve()))
                        break
        except Exception:
            pass

    # 4. GNOME Shell share data (theme, extensions, modes, osk, etc.)
    if Path("/usr/share/gnome-shell").exists():
        print("  Installing GNOME Shell shared data...")
        shutil.copytree("/usr/share/gnome-shell", root / "usr/share/gnome-shell", dirs_exist_ok=True)

        # Built-in extension to guarantee GNOME Shell animations remain active unconditionally
        ext_dir = root / "usr/share/gnome-shell/extensions/force-animations@myelinos.org"
        ext_dir.mkdir(parents=True, exist_ok=True)
        (ext_dir / "metadata.json").write_text("""{
  "name": "Force Animations",
  "description": "Unconditionally enable animations in GNOME Shell",
  "uuid": "force-animations@myelinos.org",
  "shell-version": [
    "50"
  ],
  "version-name": "1.0"
}
""")
        (ext_dir / "extension.js").write_text("""import St from 'gi://St';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

export default class ForceAnimationsExtension extends Extension {
    enable() {
        try {
            global.force_animations = true;
            const settings = St.Settings.get();
            let safety = 10;
            while (!settings.enable_animations && safety-- > 0) {
                settings.uninhibit_animations();
            }
        } catch (e) {
            console.error('Failed to force animations in extension:', e);
        }
    }

    disable() {
    }
}
""")

    # 5. GNOME Session share data
    if Path("/usr/share/gnome-session").exists():
        shutil.copytree("/usr/share/gnome-session", root / "usr/share/gnome-session", dirs_exist_ok=True)

    # 6. GNOME Settings Daemon share data
    if Path("/usr/share/gnome-settings-daemon").exists():
        shutil.copytree("/usr/share/gnome-settings-daemon", root / "usr/share/gnome-settings-daemon", dirs_exist_ok=True)

    # 7. GNOME Control Center share data
    if Path("/usr/share/gnome-control-center").exists():
        shutil.copytree("/usr/share/gnome-control-center", root / "usr/share/gnome-control-center", dirs_exist_ok=True)

    # 8. Nautilus share data
    if Path("/usr/share/nautilus").exists():
        shutil.copytree("/usr/share/nautilus", root / "usr/share/nautilus", dirs_exist_ok=True)
    if Path("/usr/share/localsearch3").exists():
        shutil.copytree("/usr/share/localsearch3", root / "usr/share/localsearch3", dirs_exist_ok=True)

    # 9. GDM data and configuration
    if Path("/usr/share/gdm").exists():
        shutil.copytree("/usr/share/gdm", root / "usr/share/gdm", dirs_exist_ok=True)
    if Path("/etc/gdm").exists():
        shutil.copytree("/etc/gdm", root / "etc/gdm", dirs_exist_ok=True)

    # Configure GDM for automatic login
    (root / "etc/gdm").mkdir(parents=True, exist_ok=True)
    (root / "etc/gdm/custom.conf").write_text("""# GDM configuration for MyelinOS
[daemon]
AutomaticLoginEnable=True
AutomaticLogin=myelinos
WaylandEnable=true
InitialSetupEnable=false

[security]

[debug]
# Uncomment to enable debugging
#Enable=true
""")

    if Path("/usr/share/dconf/profile/gdm").exists():
        (root / "usr/share/dconf/profile").mkdir(parents=True, exist_ok=True)
        shutil.copy2("/usr/share/dconf/profile/gdm", root / "usr/share/dconf/profile/gdm")

    (root / "usr/lib/tmpfiles.d").mkdir(parents=True, exist_ok=True)
    (root / "usr/lib/tmpfiles.d/gdm.conf").write_text("""d /run/gdm 0711 gdm gdm -
d /var/lib/gdm 0750 gdm gdm -
d /var/log/gdm 0750 gdm gdm -
""")

    gdm_dropin = root / "usr/lib/systemd/system/gdm.service.d"
    gdm_dropin.mkdir(parents=True, exist_ok=True)
    (gdm_dropin / "10-dependencies.conf").write_text("""[Unit]
After=systemd-user-sessions.service dbus.service systemd-logind.service accounts-daemon.service
Wants=systemd-user-sessions.service dbus.service systemd-logind.service accounts-daemon.service
""")

    if Path("/usr/lib64/gnome-software").exists():
        shutil.copytree("/usr/lib64/gnome-software", root / "usr/lib64/gnome-software", dirs_exist_ok=True)

    # 10. Backgrounds
    if Path("/usr/share/backgrounds/gnome").exists():
        shutil.copytree("/usr/share/backgrounds/gnome", root / "usr/share/backgrounds/gnome", dirs_exist_ok=True)
        bg_dir = root / "usr/share/backgrounds/gnome"
        for name in ["adwaita-d", "adwaita-l"]:
            src_jxl = bg_dir / f"{name}.jxl"
            dest_jpg = bg_dir / f"{name}.jpg"
            if src_jxl.exists() and not dest_jpg.exists():
                try:
                    subprocess.run(["magick", str(src_jxl), "-quality", "92", str(dest_jpg)], check=True)
                except Exception as e:
                    print(f"Warning: Failed to convert {src_jxl} to JPG: {e}")

    # 10b. Glycin image loaders and bubblewrap assets
    if Path("/usr/share/glycin-loaders").exists():
        shutil.copytree("/usr/share/glycin-loaders", root / "usr/share/glycin-loaders", dirs_exist_ok=True)
    if Path("/usr/libexec/glycin-loaders").exists():
        shutil.copytree("/usr/libexec/glycin-loaders", root / "usr/libexec/glycin-loaders", dirs_exist_ok=True)

    # 10c. ALSA configuration, card profiles, and sound themes
    if Path("/usr/share/alsa").exists():
        shutil.copytree("/usr/share/alsa", root / "usr/share/alsa", dirs_exist_ok=True)
    if Path("/usr/share/alsa-card-profile").exists():
        shutil.copytree("/usr/share/alsa-card-profile", root / "usr/share/alsa-card-profile", dirs_exist_ok=True)
    if Path("/usr/share/sounds").exists():
        shutil.copytree("/usr/share/sounds", root / "usr/share/sounds", dirs_exist_ok=True)

    # 10d. NetworkManager configuration and systemd service
    nm_etc = root / "etc/NetworkManager"
    nm_etc.mkdir(parents=True, exist_ok=True)
    (nm_etc / "system-connections").mkdir(mode=0o700, parents=True, exist_ok=True)
    if Path("/etc/NetworkManager/NetworkManager.conf").exists():
        shutil.copy2("/etc/NetworkManager/NetworkManager.conf", nm_etc / "NetworkManager.conf")
    else:
        (nm_etc / "NetworkManager.conf").write_text("""[main]
plugins=keyfile

[logging]
""")
    # Add auto-connecting wired ethernet connection
    wired_conn = nm_etc / "system-connections/Wired.nmconnection"
    wired_conn.write_text("""[connection]
id=Wired Connection
uuid=1d8d9e20-7e10-4bf2-a3c3-63b78cf23a84
type=ethernet
autoconnect=true

[ethernet]

[ipv4]
method=auto

[ipv6]
method=auto
""")
    wired_conn.chmod(0o600)
    if Path("/usr/share/NetworkManager").exists():
        shutil.copytree("/usr/share/NetworkManager", root / "usr/share/NetworkManager", dirs_exist_ok=True)
    if Path("/usr/share/dbus-1/system.d/org.freedesktop.NetworkManager.conf").exists():
        shutil.copy2("/usr/share/dbus-1/system.d/org.freedesktop.NetworkManager.conf",
                     root / "usr/share/dbus-1/system.d/org.freedesktop.NetworkManager.conf")
    if Path("/usr/lib/systemd/system/NetworkManager.service").exists():
        shutil.copy2("/usr/lib/systemd/system/NetworkManager.service",
                     root / "usr/lib/systemd/system/NetworkManager.service")
        nm_link = root / "etc/systemd/system/multi-user.target.wants/NetworkManager.service"
        nm_link.parent.mkdir(parents=True, exist_ok=True)
        if nm_link.exists() or nm_link.is_symlink():
            nm_link.unlink()
        nm_link.symlink_to("/usr/lib/systemd/system/NetworkManager.service")

    # 11. Wayland sessions (gnome.desktop)
    (root / "usr/share/wayland-sessions").mkdir(parents=True, exist_ok=True)
    if Path("/usr/share/wayland-sessions/gnome.desktop").exists():
        shutil.copy2("/usr/share/wayland-sessions/gnome.desktop", root / "usr/share/wayland-sessions/gnome.desktop")
    if Path("/usr/share/wayland-sessions/gnome-wayland.desktop").exists():
        shutil.copy2("/usr/share/wayland-sessions/gnome-wayland.desktop", root / "usr/share/wayland-sessions/gnome-wayland.desktop")

    # 12. GNOME libexec binaries
    print("  Installing GNOME libexec helpers...")
    gnome_libexec = [
        "gio-launch-desktop",
        "gdm-wayland-session", "gdm-session-worker", "gdm-runtime-config", "gdm-new-session",
        "gnome-session-ctl", "gnome-session-init-worker", "gnome-session-service",
        "gnome-shell-calendar-server", "gnome-shell-hotplug-sniffer", "gnome-shell-portal-helper",
        "ptyxis-agent", "accounts-daemon", "xdg-desktop-portal", "xdg-desktop-portal-gnome", "xdg-desktop-portal-gtk",
        "xdg-desktop-portal-validate-sound", "xdg-desktop-portal-validate-icon", "xdg-desktop-portal-rewrite-launchers",
        "gnome-calculator-search-provider", "gnome-contacts-search-provider", "gnome-boxes-search-provider",
        "gnome-control-center-search-provider", "gnome-control-center-global-shortcuts-provider",
        "gsd-a11y-settings", "gsd-color", "gsd-datetime", "gsd-housekeeping", "gsd-keyboard",
        "gsd-media-keys", "gsd-power", "gsd-print-notifications", "gsd-rfkill",
        "gsd-screensaver-proxy", "gsd-sharing", "gsd-smartcard", "gsd-sound",
        "gsd-usb-protection", "gsd-wwan", "gsd-xsettings",
        "localsearch-3", "localsearch-control-3", "localsearch-endpoint-3",
        "localsearch-extractor-3", "localsearch-writeback-3",
        "tinysparql-sql", "tinysparql-xdg-portal-3",
        "mutter-x11-frames", "mutter-backlight-helper",
        "geoclue", "malcontent-timerd",
        "ibus-dconf", "ibus-extension-gtk3", "ibus-portal", "ibus-ui-emojier", "ibus-x11", "ibus-engine-simple",
        "gcr-prompter", "gcr-ssh-agent", "gcr-ssh-askpass", "gcr4-ssh-askpass",
        "org.gnome.NautilusPreviewer", "vte-urlencode-cwd",
        "glib-pacrunner", "switcheroo-control", "upowerd",
        "colord", "colord-session", "at-spi-bus-launcher", "at-spi2-registryd", "dconf-service",
        "goa-daemon", "goa-identity-service", "goa-oauth2-handler",
        "evolution-alarm-notify", "evolution-source-registry", "evolution-addressbook-factory",
        "evolution-calendar-factory", "evolution-user-prompter"
    ]
    for libexec_bin in gnome_libexec:
        src = Path("/usr/libexec") / libexec_bin
        if src.exists():
            dest = root / "usr/libexec" / libexec_bin
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            resolve_deps(str(src), all_libs)

    for libexec_dir in ["gnome-system-monitor", "gnome-contacts", "evolution-data-server"]:
        src_d = Path("/usr/libexec") / libexec_dir
        if src_d.exists():
            shutil.copytree(src_d, root / "usr/libexec" / libexec_dir, dirs_exist_ok=True)
            for f in (root / "usr/libexec" / libexec_dir).rglob("*"):
                if f.is_file() and os.access(f, os.X_OK):
                    resolve_deps(str(f), all_libs)

    # Symlink /usr/bin/gio-launch-desktop to /usr/libexec/gio-launch-desktop
    if (root / "usr/libexec/gio-launch-desktop").exists():
        gio_sym = root / "usr/bin/gio-launch-desktop"
        gio_sym.parent.mkdir(parents=True, exist_ok=True)
        if gio_sym.exists() or gio_sym.is_symlink():
            gio_sym.unlink()
        gio_sym.symlink_to("/usr/libexec/gio-launch-desktop")

    # 13. Systemd user services for GNOME
    print("  Installing GNOME systemd user units...")
    for u in Path("/usr/lib/systemd/user").glob("org.gnome.*"):
        if u.is_dir():
            shutil.copytree(u, root / "usr/lib/systemd/user" / u.name, dirs_exist_ok=True)
        else:
            shutil.copy2(u, root / "usr/lib/systemd/user" / u.name)
    for u in Path("/usr/lib/systemd/user").glob("gnome-*"):
        if u.is_dir():
            shutil.copytree(u, root / "usr/lib/systemd/user" / u.name, dirs_exist_ok=True)
        else:
            shutil.copy2(u, root / "usr/lib/systemd/user" / u.name)

    # 14. D-Bus session and system services for GNOME
    for s in Path("/usr/share/dbus-1/services").glob("org.gnome.*"):
        shutil.copy2(s, root / "usr/share/dbus-1/services" / s.name)
    if Path("/usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.gnome.service").exists():
        shutil.copy2("/usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.gnome.service",
                     root / "usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.gnome.service")
    for s in Path("/usr/share/dbus-1/system-services").glob("org.gnome.*"):
        shutil.copy2(s, root / "usr/share/dbus-1/system-services" / s.name)
    if Path("/usr/share/dbus-1/system-services/org.freedesktop.Accounts.service").exists():
        shutil.copy2("/usr/share/dbus-1/system-services/org.freedesktop.Accounts.service",
                     root / "usr/share/dbus-1/system-services/org.freedesktop.Accounts.service")
    for c in Path("/usr/share/dbus-1/system.d").glob("*gnome*"):
        shutil.copy2(c, root / "usr/share/dbus-1/system.d" / c.name)
    if Path("/usr/share/dbus-1/system.d/org.freedesktop.Accounts.conf").exists():
        shutil.copy2("/usr/share/dbus-1/system.d/org.freedesktop.Accounts.conf",
                     root / "usr/share/dbus-1/system.d/org.freedesktop.Accounts.conf")

    # 15. GNOME PAM configuration
    for pam_f in Path("/etc/pam.d").glob("gdm*"):
        shutil.copy2(pam_f, root / "etc/pam.d" / pam_f.name)

    # 16. Install robust start-gnome launcher script
    start_gnome_path = root / "usr/bin/start-gnome"
    start_gnome_path.write_text("""#!/usr/bin/bash

export XDG_CURRENT_DESKTOP=GNOME
export XDG_SESSION_DESKTOP=GNOME
export XDG_SESSION_TYPE=wayland
export XDG_RUNTIME_DIR=/run/user/1000
export HOME=/home/myelinos
export USER=myelinos
export SHELL=/bin/bash
export PATH=/usr/local/bin:/usr/bin:/usr/libexec
export XDG_DATA_DIRS=/usr/local/share:/usr/share
export XDG_CONFIG_DIRS=/etc/xdg
export _JAVA_AWT_WM_NONREPARENTING=1
export GDK_BACKEND=wayland,x11
export MOZ_ENABLE_WAYLAND=1
export SAL_USE_VCLPLUGIN=gtk3
export QT_QPA_PLATFORM="wayland;xcb"
export QT_AUTO_SCREEN_SCALE_FACTOR=1
export QT_ENABLE_HIGHDPI_SCALING=1
if [ -n "$FORCE_SOFTWARE_GL" ]; then
    export LIBGL_ALWAYS_SOFTWARE=1
fi
export GI_TYPELIB_PATH=/usr/lib64/girepository-1.0:/usr/lib64/gnome-shell:/usr/lib64/mutter-18:/usr/lib64/gjs/girepository-1.0
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# Symlink wayland socket if wayland-1 exists so default wayland-0 also resolves
(
    while true; do
        if [ -S /run/user/1000/wayland-1 ] && [ ! -e /run/user/1000/wayland-0 ]; then
            ln -snf wayland-1 /run/user/1000/wayland-0 2>/dev/null || true
        elif [ -S /run/user/1000/wayland-0 ] && [ ! -e /run/user/1000/wayland-1 ]; then
            ln -snf wayland-0 /run/user/1000/wayland-1 2>/dev/null || true
        fi
        if [ -S /run/user/1000/wayland-0 ] || [ -S /run/user/1000/wayland-1 ]; then
            export WAYLAND_DISPLAY=wayland-0
            export DISPLAY=:0
            if command -v systemctl >/dev/null; then
                systemctl --user import-environment WAYLAND_DISPLAY DISPLAY 2>/dev/null || true
                systemctl --user start graphical-session.target 2>/dev/null || true
            fi
            if command -v dbus-update-activation-environment >/dev/null; then
                dbus-update-activation-environment --systemd WAYLAND_DISPLAY DISPLAY 2>/dev/null || true
            fi
            break
        fi
        sleep 0.2
    done
) &

if [ -z "$DBUS_SESSION_BUS_ADDRESS" ] && [ -S /run/user/1000/bus ]; then
    export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus"
fi

if command -v systemctl >/dev/null; then
    systemctl --user import-environment PATH XDG_DATA_DIRS XDG_CONFIG_DIRS XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP XDG_SESSION_TYPE GDK_BACKEND MOZ_ENABLE_WAYLAND SAL_USE_VCLPLUGIN GI_TYPELIB_PATH LANG LC_ALL 2>/dev/null || true
fi
if command -v dbus-update-activation-environment >/dev/null; then
    dbus-update-activation-environment --systemd PATH XDG_DATA_DIRS XDG_CONFIG_DIRS XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP XDG_SESSION_TYPE GDK_BACKEND MOZ_ENABLE_WAYLAND SAL_USE_VCLPLUGIN GI_TYPELIB_PATH LANG LC_ALL 2>/dev/null || true
fi

# Cleanup graphical session target when GNOME Shell exits
cleanup_session() {
    if command -v systemctl >/dev/null; then
        systemctl --user stop graphical-session.target 2>/dev/null || true
    fi
}
trap cleanup_session EXIT INT TERM

# Launch GNOME Shell directly as Wayland display server & compositor
/usr/bin/gnome-shell --wayland --display-server --force-animations
""")
    start_gnome_path.chmod(0o755)

    # 17. Custom GSettings schema overrides for MyelinOS GNOME
    schema_override = root / "usr/share/glib-2.0/schemas/99_myelinos.gschema.override"
    schema_override.write_text("""[org.gnome.shell]
favorite-apps=['org.gnome.Ptyxis.desktop', 'org.gnome.Nautilus.desktop', 'org.mozilla.firefox.desktop', 'org.gnome.TextEditor.desktop', 'org.gnome.Calculator.desktop', 'org.gnome.SystemMonitor.desktop', 'libreoffice-writer.desktop']
welcome-dialog-last-shown-version='99'
disable-user-extensions=false
enabled-extensions=['force-animations@myelinos.org', 'apps-menu@gnome-shell-extensions.gcampax.github.com', 'places-menu@gnome-shell-extensions.gcampax.github.com', 'window-list@gnome-shell-extensions.gcampax.github.com']

[org.gnome.desktop.interface]
color-scheme='prefer-dark'
font-name='Cantarell 11'
document-font-name='Cantarell 11'
monospace-font-name='Adwaita Mono 10'
enable-animations=true
enable-hot-corners=true

[org.gnome.mutter]
attach-modal-dialogs=true
edge-tiling=true
dynamic-workspaces=true

[org.gnome.desktop.wm.preferences]
button-layout='appmenu:minimize,maximize,close'

[org.gnome.desktop.session]
idle-delay=uint32 0

[org.gnome.desktop.background]
picture-uri='file:///usr/share/backgrounds/gnome/adwaita-l.jpg'
picture-uri-dark='file:///usr/share/backgrounds/gnome/adwaita-d.jpg'
picture-options='zoom'
primary-color='#2e3436'
secondary-color='#1e2229'

[org.gnome.desktop.screensaver]
picture-uri='file:///usr/share/backgrounds/gnome/adwaita-d.jpg'
picture-options='zoom'

[org.gnome.settings-daemon.plugins.power]
sleep-inactive-ac-type='nothing'
sleep-inactive-battery-type='nothing'
""")
    if shutil.which("glib-compile-schemas"):
        try:
            subprocess.run(["glib-compile-schemas", str(root / "usr/share/glib-2.0/schemas")], check=True)
        except Exception as e:
            print(f"Warning: glib-compile-schemas failed: {e}")

    print("GNOME 50 desktop environment installed successfully.")

    # 18. Accountsservice, DBus interfaces, and GVFS daemons
    if Path("/usr/share/accountsservice").exists():
        shutil.copytree("/usr/share/accountsservice", root / "usr/share/accountsservice", dirs_exist_ok=True)
    if Path("/usr/share/dbus-1/interfaces").exists():
        shutil.copytree("/usr/share/dbus-1/interfaces", root / "usr/share/dbus-1/interfaces", dirs_exist_ok=True)
    (root / "var/lib/AccountsService/users").mkdir(parents=True, exist_ok=True)
    (root / "var/lib/AccountsService/icons").mkdir(parents=True, exist_ok=True)

    # Accounts service systemd override to ensure non-blocking mount namespace paths
    act_override_dir = root / "etc/systemd/system/accounts-daemon.service.d"
    act_override_dir.mkdir(parents=True, exist_ok=True)
    (act_override_dir / "override.conf").write_text("""[Service]
ReadOnlyPaths=-/usr/share/accountsservice/interfaces/ -/usr/share/dbus-1/interfaces/ -/var/log/wtmp -/run/systemd/seats/
""")

    # GVFS helpers and at-spi accessibility bus helpers
    for gvfs_bin in Path("/usr/libexec").glob("gvfs*"):
        dest = root / "usr/libexec" / gvfs_bin.name
        shutil.copy2(gvfs_bin, dest)
        resolve_deps(str(gvfs_bin), all_libs)
    for atspi_bin in Path("/usr/libexec").glob("at-spi*"):
        dest = root / "usr/libexec" / atspi_bin.name
        shutil.copy2(atspi_bin, dest)
        resolve_deps(str(atspi_bin), all_libs)
    if Path("/usr/share/gvfs").exists():
        shutil.copytree("/usr/share/gvfs", root / "usr/share/gvfs", dirs_exist_ok=True)
    if Path("/usr/share/libinput").exists():
        shutil.copytree("/usr/share/libinput", root / "usr/share/libinput", dirs_exist_ok=True)
    if Path("/usr/share/defaults").exists():
        shutil.copytree("/usr/share/defaults", root / "usr/share/defaults", dirs_exist_ok=True)

    # RealtimeKit daemon for Mutter/KMS real-time priority
    if Path("/usr/libexec/rtkit-daemon").exists():
        shutil.copy2("/usr/libexec/rtkit-daemon", root / "usr/libexec/rtkit-daemon")
        resolve_deps("/usr/libexec/rtkit-daemon", all_libs)
    if Path("/usr/lib/systemd/system/rtkit-daemon.service").exists():
        shutil.copy2("/usr/lib/systemd/system/rtkit-daemon.service", root / "usr/lib/systemd/system/rtkit-daemon.service")
    if Path("/usr/share/dbus-1/system-services/org.freedesktop.RealtimeKit1.service").exists():
        shutil.copy2("/usr/share/dbus-1/system-services/org.freedesktop.RealtimeKit1.service",
                     root / "usr/share/dbus-1/system-services/org.freedesktop.RealtimeKit1.service")
    if Path("/usr/share/dbus-1/system.d/org.freedesktop.RealtimeKit1.conf").exists():
        shutil.copy2("/usr/share/dbus-1/system.d/org.freedesktop.RealtimeKit1.conf",
                     root / "usr/share/dbus-1/system.d/org.freedesktop.RealtimeKit1.conf")

    # GWeather locations database (required by GNOME Shell date/weather menu)
    if Path("/usr/lib64/gweather-locations").exists():
        shutil.copytree("/usr/lib64/gweather-locations", root / "usr/lib64/gweather-locations", dirs_exist_ok=True)
    if Path("/usr/share/gweather-locations").exists():
        shutil.copytree("/usr/share/gweather-locations", root / "usr/share/gweather-locations", dirs_exist_ok=True)
    if Path("/usr/share/xml/iso-codes").exists():
        shutil.copytree("/usr/share/xml/iso-codes", root / "usr/share/xml/iso-codes", dirs_exist_ok=True)

    # Color management daemon (colord)
    for colord_bin in ["colord", "colord-session"]:
        src = Path(f"/usr/libexec/{colord_bin}")
        if src.exists():
            dest = root / "usr/libexec" / colord_bin
            shutil.copy2(src, dest)
            resolve_deps(str(src), all_libs)
    if Path("/usr/lib/systemd/system/colord.service").exists():
        shutil.copy2("/usr/lib/systemd/system/colord.service", root / "usr/lib/systemd/system/colord.service")
    if Path("/usr/share/dbus-1/system-services/org.freedesktop.ColorManager.service").exists():
        shutil.copy2("/usr/share/dbus-1/system-services/org.freedesktop.ColorManager.service", root / "usr/share/dbus-1/system-services/org.freedesktop.ColorManager.service")
    if Path("/usr/share/dbus-1/system.d/org.freedesktop.ColorManager.conf").exists():
        shutil.copy2("/usr/share/dbus-1/system.d/org.freedesktop.ColorManager.conf", root / "usr/share/dbus-1/system.d/org.freedesktop.ColorManager.conf")
    if Path("/usr/share/colord").exists():
        shutil.copytree("/usr/share/colord", root / "usr/share/colord", dirs_exist_ok=True)
    (root / "var/lib/colord").mkdir(parents=True, exist_ok=True)

    # GeoClue location daemon
    if Path("/usr/lib/systemd/system/geoclue.service").exists():
        shutil.copy2("/usr/lib/systemd/system/geoclue.service", root / "usr/lib/systemd/system/geoclue.service")
    if Path("/etc/geoclue").exists():
        shutil.copytree("/etc/geoclue", root / "etc/geoclue", dirs_exist_ok=True)
    if Path("/usr/share/dbus-1/system-services/org.freedesktop.GeoClue2.service").exists():
        shutil.copy2("/usr/share/dbus-1/system-services/org.freedesktop.GeoClue2.service", root / "usr/share/dbus-1/system-services/org.freedesktop.GeoClue2.service")
    if Path("/usr/share/dbus-1/system.d/org.freedesktop.GeoClue2.conf").exists():
        shutil.copy2("/usr/share/dbus-1/system.d/org.freedesktop.GeoClue2.conf", root / "usr/share/dbus-1/system.d/org.freedesktop.GeoClue2.conf")
    (root / "var/lib/geoclue").mkdir(parents=True, exist_ok=True)

    # Parental Controls / Timer Daemon (malcontent)
    if Path("/usr/lib/systemd/system/malcontent-timerd.service").exists():
        shutil.copy2("/usr/lib/systemd/system/malcontent-timerd.service", root / "usr/lib/systemd/system/malcontent-timerd.service")
    (root / "var/lib/malcontent-timerd").mkdir(parents=True, exist_ok=True)

    # IBus Input Method configuration and services
    if Path("/usr/share/ibus").exists():
        shutil.copytree("/usr/share/ibus", root / "usr/share/ibus", dirs_exist_ok=True)
    for ibus_unit in Path("/usr/lib/systemd/user").glob("org.freedesktop.IBus*"):
        shutil.copy2(ibus_unit, root / "usr/lib/systemd/user" / ibus_unit.name)

    # Prune dangling D-Bus system-services whose systemd units do not exist to eliminate activation warnings
    dbus_sys_services = root / "usr/share/dbus-1/system-services"
    if dbus_sys_services.exists():
        for ss in list(dbus_sys_services.glob("*.service")):
            try:
                txt = ss.read_text()
                for line in txt.splitlines():
                    if line.startswith("SystemdService="):
                        unit = line.split("=")[1].strip()
                        if not (root / "usr/lib/systemd/system" / unit).exists() and not (root / "etc/systemd/system" / unit).exists():
                            ss.unlink()
                        break
            except Exception:
                pass

def install_desktop_applications(root: Path, all_libs: set):
    """Install Firefox, LibreOffice suite, GNOME utilities, desktop entries, schemas, and icons."""
    print("Installing standard desktop applications (Firefox, LibreOffice, GNOME utilities)...")

    # 1. Mozilla Firefox
    firefox_src = Path("/usr/lib64/firefox")
    if firefox_src.exists():
        print("  Installing Mozilla Firefox runtime...")
        firefox_dest = root / "usr/lib64/firefox"
        shutil.copytree(firefox_src, firefox_dest, dirs_exist_ok=True)
        if Path("/usr/bin/firefox").exists():
            shutil.copy2("/usr/bin/firefox", root / "usr/bin/firefox")
        if Path("/etc/firefox").exists():
            shutil.copytree("/etc/firefox", root / "etc/firefox", dirs_exist_ok=True)
        if Path("/usr/lib64/mozilla").exists():
            shutil.copytree("/usr/lib64/mozilla", root / "usr/lib64/mozilla", dirs_exist_ok=True)
        if Path("/usr/share/applications/org.mozilla.firefox.desktop").exists():
            shutil.copy2("/usr/share/applications/org.mozilla.firefox.desktop", root / "usr/share/applications/org.mozilla.firefox.desktop")

        # Resolve libraries for Firefox
        for f in firefox_dest.glob("*.so*"):
            resolve_deps(str(f), all_libs)
        if (firefox_dest / "firefox").exists():
            resolve_deps(str(firefox_dest / "firefox"), all_libs)

    # 2. LibreOffice Suite
    lo_src = Path("/usr/lib64/libreoffice")
    if lo_src.exists():
        print("  Installing LibreOffice suite runtime...")
        lo_dest = root / "usr/lib64/libreoffice"
        shutil.copytree(lo_src, lo_dest, dirs_exist_ok=True)
        if Path("/usr/share/libreoffice").exists():
            shutil.copytree("/usr/share/libreoffice", root / "usr/share/libreoffice", dirs_exist_ok=True)
        if Path("/usr/share/autocorr").exists():
            shutil.copytree("/usr/share/autocorr", root / "usr/share/autocorr", dirs_exist_ok=True)

        # Copy LibreOffice executables & symlinks
        for lo_bin in ["libreoffice", "soffice", "oocalc", "oowriter", "ooimpress", "oodraw", "oomath", "oobase", "unopkg"]:
            src_bin = Path(f"/usr/bin/{lo_bin}")
            if src_bin.exists():
                dest_bin = root / "usr/bin" / lo_bin
                if dest_bin.exists() or dest_bin.is_symlink():
                    dest_bin.unlink()
                if src_bin.is_symlink():
                    dest_bin.symlink_to(os.readlink(src_bin))
                else:
                    shutil.copy2(src_bin, dest_bin)

        # Copy LibreOffice desktop entries
        for dt in Path("/usr/share/applications").glob("libreoffice-*.desktop"):
            shutil.copy2(dt, root / "usr/share/applications" / dt.name)

        # Resolve libraries for LibreOffice
        for f in (lo_dest / "program").glob("*.so*"):
            resolve_deps(str(f), all_libs)
        for f in ["soffice.bin", "oosplash"]:
            bp = lo_dest / "program" / f
            if bp.exists():
                resolve_deps(str(bp), all_libs)

    # 2b. XDG System Configurations (/etc/xdg)
    if Path("/etc/xdg").exists():
        print("  Installing XDG system configurations (/etc/xdg)...")
        shutil.copytree("/etc/xdg", root / "etc/xdg", dirs_exist_ok=True)

    # 3. GNOME Desktop Applications: Desktop entries
    for dtf in Path("/usr/share/applications").glob("org.gnome.*.desktop"):
        shutil.copy2(dtf, root / "usr/share/applications" / dtf.name)

    # 3b. GNOME Desktop Applications Data Directories & Assets
    print("  Installing GNOME desktop application assets & data directories...")
    desktop_shares = [
        "gnome-boxes", "gnome-tour", "gnome-maps", "org.gnome.Characters",
        "org.gnome.Weather", "org.gnome.Decibels", "showtime", "snapshot",
        "yelp", "yelp-xsl", "gnome-color-manager", "gnome-user-share",
        "gnome-bluetooth-3.0", "gnome-vpn-properties", "gnome-remote-desktop",
        "gweather-locations", "icons/default"
    ]
    for d in desktop_shares:
        src = Path(f"/usr/share/{d}")
        if src.exists():
            dest = root / f"usr/share/{d}"
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

    for svg in Path("/usr/share/icons").glob("gnome-logo-text*"):
        shutil.copy2(svg, root / "usr/share/icons" / svg.name)

    # 3c. Python pure-lib site-packages for desktop applications
    if Path("/usr/lib/python3.14/site-packages").exists():
        print("  Installing Python pure-lib site-packages...")
        shutil.copytree("/usr/lib/python3.14/site-packages", root / "usr/lib/python3.14/site-packages",
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # 4. GIO modules & GDK pixbuf modules
    if Path("/usr/lib64/gio/modules").exists():
        shutil.copytree("/usr/lib64/gio/modules", root / "usr/lib64/gio/modules", dirs_exist_ok=True)
        for m in (root / "usr/lib64/gio/modules").glob("*.so*"):
            resolve_deps(str(m), all_libs)

    if Path("/usr/lib64/gdk-pixbuf-2.0").exists():
        shutil.copytree("/usr/lib64/gdk-pixbuf-2.0", root / "usr/lib64/gdk-pixbuf-2.0", dirs_exist_ok=True)
        for m in (root / "usr/lib64/gdk-pixbuf-2.0").rglob("*.so*"):
            resolve_deps(str(m), all_libs)

    # 5. GSettings Schemas & compilation
    if Path("/usr/share/glib-2.0/schemas").exists():
        print("  Compiling GSettings schemas...")
        shutil.copytree("/usr/share/glib-2.0/schemas", root / "usr/share/glib-2.0/schemas", dirs_exist_ok=True)
        try:
            subprocess.run(["glib-compile-schemas", str(root / "usr/share/glib-2.0/schemas")], check=True)
        except Exception as e:
            print(f"Warning: glib-compile-schemas failed: {e}")

    # 6. Shared MIME Info database
    if Path("/usr/share/mime").exists():
        print("  Updating MIME database...")
        shutil.copytree("/usr/share/mime", root / "usr/share/mime", dirs_exist_ok=True)
        if shutil.which("update-mime-database"):
            try:
                subprocess.run(["update-mime-database", str(root / "usr/share/mime")], check=True)
            except Exception as e:
                print(f"Warning: update-mime-database failed: {e}")

    # 7. Adwaita Icon Themes
    for theme in ["Adwaita", "AdwaitaLegacy"]:
        src_th = Path(f"/usr/share/icons/{theme}")
        if src_th.exists():
            shutil.copytree(src_th, root / "usr/share/icons" / theme, dirs_exist_ok=True)

    # 8. Update desktop database & icon caches
    if shutil.which("update-desktop-database"):
        try:
            subprocess.run(["update-desktop-database", "-q", str(root / "usr/share/applications")], check=True)
        except Exception:
            pass

    if shutil.which("gtk-update-icon-cache"):
        for icondir in [(root / "usr/share/icons/hicolor"), (root / "usr/share/icons/Adwaita")]:
            if icondir.exists():
                try:
                    subprocess.run(["gtk-update-icon-cache", "-q", "-t", "-f", str(icondir)], check=False)
                except Exception:
                    pass

    # 9. XDG Desktop Portals & D-Bus Interfaces
    print("  Installing XDG Desktop Portal services & helpers...")
    portal_bins = [
        "xdg-desktop-portal", "xdg-document-portal", "xdg-permission-store",
        "xdg-desktop-portal-rewrite-launchers", "xdg-desktop-portal-validate-icon",
        "xdg-desktop-portal-validate-sound",
        "xdg-desktop-portal-gtk", "xdg-desktop-portal-gnome"
    ]
    for pb in portal_bins:
        p_src = Path(f"/usr/libexec/{pb}")
        if p_src.exists():
            p_dest = root / "usr/libexec" / pb
            p_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p_src, p_dest)
            resolve_deps(str(p_src), all_libs)

    # Portal systemd user services
    for us in Path("/usr/lib/systemd/user").glob("xdg-*.service"):
        shutil.copy2(us, root / "usr/lib/systemd/user" / us.name)

    # Portal D-Bus service files & interfaces
    for srv in Path("/usr/share/dbus-1/services").glob("org.freedesktop.portal.*"):
        shutil.copy2(srv, root / "usr/share/dbus-1/services" / srv.name)
    if Path("/usr/share/dbus-1/services/org.freedesktop.impl.portal.PermissionStore.service").exists():
        shutil.copy2("/usr/share/dbus-1/services/org.freedesktop.impl.portal.PermissionStore.service", root / "usr/share/dbus-1/services/org.freedesktop.impl.portal.PermissionStore.service")
    if Path("/usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.gtk.service").exists():
        shutil.copy2("/usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.gtk.service", root / "usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.gtk.service")
    if Path("/usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.gnome.service").exists():
        shutil.copy2("/usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.gnome.service", root / "usr/share/dbus-1/services/org.freedesktop.impl.portal.desktop.gnome.service")

    if Path("/usr/share/xdg-desktop-portal").exists():
        shutil.copytree("/usr/share/xdg-desktop-portal", root / "usr/share/xdg-desktop-portal", dirs_exist_ok=True)

    # 10. dconf service & D-Bus activation
    if Path("/usr/libexec/dconf-service").exists():
        dest = root / "usr/libexec/dconf-service"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2("/usr/libexec/dconf-service", dest)
        resolve_deps("/usr/libexec/dconf-service", all_libs)
    if Path("/usr/lib/systemd/user/dconf.service").exists():
        shutil.copy2("/usr/lib/systemd/user/dconf.service", root / "usr/lib/systemd/user/dconf.service")
    if Path("/usr/share/dbus-1/services/ca.desrt.dconf.service").exists():
        shutil.copy2("/usr/share/dbus-1/services/ca.desrt.dconf.service", root / "usr/share/dbus-1/services/ca.desrt.dconf.service")

    # 11. PolicyKit (polkit) library resolution
    for pb in [(root / "usr/lib/polkit-1/polkitd"), (root / "usr/lib/polkit-1/polkit-agent-helper-1")]:
        if pb.exists():
            resolve_deps(str(pb), all_libs)

    # 12. UPower daemon
    if Path("/usr/libexec/upowerd").exists():
        dest = root / "usr/libexec/upowerd"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2("/usr/libexec/upowerd", dest)
        resolve_deps("/usr/libexec/upowerd", all_libs)
    if Path("/usr/lib/systemd/system/upower.service").exists():
        shutil.copy2("/usr/lib/systemd/system/upower.service", root / "usr/lib/systemd/system/upower.service")
    if Path("/usr/share/dbus-1/system-services/org.freedesktop.UPower.service").exists():
        shutil.copy2("/usr/share/dbus-1/system-services/org.freedesktop.UPower.service", root / "usr/share/dbus-1/system-services/org.freedesktop.UPower.service")
    if Path("/usr/share/dbus-1/system.d/org.freedesktop.UPower.conf").exists():
        shutil.copy2("/usr/share/dbus-1/system.d/org.freedesktop.UPower.conf", root / "usr/share/dbus-1/system.d/org.freedesktop.UPower.conf")
    if Path("/etc/UPower").exists():
        shutil.copytree("/etc/UPower", root / "etc/UPower", dirs_exist_ok=True)

    # 13. Systemd D-Bus services: timedated, localed, hostnamed
    for s_name in ["timedated", "localed", "hostnamed"]:
        s_bin = Path(f"/usr/lib/systemd/systemd-{s_name}")
        if s_bin.exists():
            dest = root / "usr/lib/systemd" / f"systemd-{s_name}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s_bin, dest)
            resolve_deps(str(s_bin), all_libs)
        for s_file in Path("/usr/lib/systemd/system").glob(f"*{s_name}*"):
            shutil.copy2(s_file, root / "usr/lib/systemd/system" / s_file.name)
        for d_file in Path("/usr/share/dbus-1/system.d").glob(f"*{s_name}*"):
            shutil.copy2(d_file, root / "usr/share/dbus-1/system.d" / d_file.name)
        for ds_file in Path("/usr/share/dbus-1/system-services").glob(f"*{s_name}*"):
            shutil.copy2(ds_file, root / "usr/share/dbus-1/system-services" / ds_file.name)

    # 14. X11 / XKB Locales and Compose tables
    if Path("/usr/share/X11/locale").exists():
        print("  Installing X11 / XKB Compose tables and locales...")
        shutil.copytree("/usr/share/X11/locale", root / "usr/share/X11/locale", dirs_exist_ok=True)

    print("Desktop applications installed successfully.")

def install_binaries_and_libs(root: Path):
    """Collect and install the full CLI binary set, display server, and shared libraries."""
    all_bins = [
        # Systemd core & helpers
        "systemd", "systemd-executor", "systemd-journald", "systemd-udevd",
        "systemd-sysctl", "systemd-modules-load", "systemd-remount-fs",
        "systemd-tmpfiles", "systemd-random-seed", "systemd-logind",
        "systemd-networkd", "systemd-resolved", "systemd-timesyncd",
        "systemd-user-runtime-dir", "systemd-shutdown", "systemd-sulogin-shell",
        "systemd-vconsole-setup",
        
        # System control & inspection
        "systemctl", "journalctl", "udevadm", "loginctl", "timedatectl",
        "localectl", "hostnamectl", "hostname", "bootctl", "busctl", "resolvectl", "networkctl",
        
        # Shells
        "bash", "sh",
        
        # GNU Core Utilities (Full Set)
        "cat", "chgrp", "chmod", "chown", "cp", "date", "dd", "df", "dmesg",
        "echo", "false", "ln", "ls", "mkdir", "mknod", "mktemp", "mv", "pwd",
        "rm", "rmdir", "sleep", "stty", "sync", "touch", "true", "uname",
        "readlink", "realpath", "truncate", "stat", "shred", "basename",
        "dirname", "cut", "head", "tail", "wc", "sort", "uniq", "tr", "tee",
        "fold", "split", "join", "comm", "paste", "csplit", "expand", "unexpand",
        "fmt", "pr", "nl", "od", "base64", "base32", "basenc", "md5sum",
        "sha1sum", "sha256sum", "sha512sum", "b2sum", "cksum", "env", "printenv",
        "expr", "factor", "seq", "shuf", "yes", "id", "whoami", "groups", "users",
        "who", "w", "uptime", "logname", "tty", "nproc", "du", "test", "[",
        
        # Find & text stream processing
        "find", "xargs", "grep", "egrep", "fgrep", "sed", "gawk", "awk",
        "which", "whereis", "file", "diff", "cmp", "patch", "diff3", "sdiff",
        "tree", "cal", "column", "col", "rev", "tac", "strings",
        
        # Text editors & pagers
        "less", "more", "nano", "vi",
        
        # Terminal management
        "clear", "reset", "tput",
        
        # Process monitoring & control (procps-ng)
        "ps", "top", "free", "kill", "killall", "pkill", "pgrep", "pidof",
        "watch", "timeout", "nice", "renice", "nohup",
        
        # Archiving & compression
        "tar", "cpio", "gzip", "gunzip", "zcat", "bzip2", "bunzip2", "bzcat",
        "xz", "unxz", "xzcat", "zstd", "unzstd", "zstdcat", "zip", "unzip",
        "zgrep", "zdiff",
        
        # Disk & filesystem administration
        "mount", "umount", "findmnt", "lsblk", "blkid", "fdisk", "cfdisk",
        "sfdisk", "partx", "wipefs", "losetup", "fallocate", "fstrim", "fsfreeze",
        "mke2fs", "mkfs", "mkfs.ext2", "mkfs.ext3", "mkfs.ext4", "e2fsck", "fsck",
        "fsck.ext4", "tune2fs", "resize2fs", "dumpe2fs", "chattr", "lsattr",
        "mkswap", "swapon", "swapoff",
        
        # Kernel modules & hardware
        "kmod", "modprobe", "insmod", "rmmod", "lsmod", "modinfo", "depmod",
        "lscpu", "lspci", "lsusb", "setarch", "taskset", "chcpu", "ionice",
        
        # Networking & remote access
        "ip", "ss", "bridge", "rtmon", "ping", "curl", "wget", "tracepath",
        "ssh", "sshd", "scp", "sftp", "ssh-keygen", "ssh-agent", "ssh-add",
        
        # Privilege escalation & account management
        "sudo", "sudoedit", "visudo", "unix_chkpwd",
        "useradd", "userdel", "usermod", "groupadd", "groupdel", "groupmod",
        "passwd", "chage", "su", "sulogin", "agetty", "login",
        
        # Power & runlevel control
        "poweroff", "reboot", "halt", "shutdown",
        
        # Scripting & system inspection
        "python3", "ldconfig", "lsof", "man", "groff",

        # D-Bus message bus
        "dbus-daemon", "dbus-run-session", "dbus-send", "dbus-monitor",

        # Font configuration
        "fc-cache", "fc-list",

        # Display server, X11 & Wayland diagnostics
        "Xwayland", "xkbcomp", "wayland-info", "xrandr", "glxinfo",
        "xauth", "xhost", "xrdb",

        # Input method (IBus)
        "ibus", "ibus-daemon", "ibus-setup",

        # GNOME 50 Desktop Environment suite & utilities
        "gnome-shell", "gnome-session", "gnome-session-quit", "gnome-session-inhibit",
        "gnome-extensions", "mutter", "gjs", "gjs-console", "gdm", "gdm-config",
        "gnome-keyring", "gnome-keyring-daemon", "gnome-software",
        "start-gnome", "nautilus", "ptyxis",
        "gnome-text-editor", "gnome-calculator", "gcalccmd",
        "gnome-system-monitor", "gnome-control-center",
        "papers", "papers-previewer",
        "loupe", "baobab", "gnome-font-viewer", "gnome-disks",
        "gnome-calendar", "gnome-clocks", "gnome-weather", "gnome-characters",
        "simple-scan", "zenity", "evince", "evince-previewer",

        # Systemd & D-Bus Launchers & Desktop Helpers
        "systemd-run", "systemd-cat", "systemd-cgls", "systemd-cgtop",
        "systemd-escape", "systemd-id128", "systemd-inhibit", "systemd-notify",
        "systemd-path", "systemd-sysusers",
        "systemd-timedated", "systemd-hostnamed", "systemd-localed",
        "dbus-update-activation-environment", "gio", "gio-launch-desktop", "gtk-launch", "gapplication",
        "dconf", "pkexec", "pkcheck", "upower", "gsettings", "gdbus", "bwrap", "xdg-user-dirs-update",

        # XDG Desktop Integration Utilities
        "xdg-open", "xdg-mime", "xdg-settings", "xdg-email",
        "xdg-screensaver", "xdg-user-dir", "xdg-dbus-proxy", "xdg-user-dirs-gtk-update",

        # Notifications & Desktop/MIME Cache Tools
        "notify-send", "update-desktop-database", "gtk-update-icon-cache", "update-mime-database",

        # Complete GNOME Desktop Application Suite
        "gnome-boxes", "gnome-contacts", "gnome-connections", "gnome-logs",
        "gnome-tour", "showtime", "snapshot", "tecla", "yelp",
        "gcm-viewer", "org.gnome.Decibels", "gnome-browser-connector",

        # System Inspection & CLI Tools
        "busctl", "hostnamectl", "localectl", "timedatectl", "loginctl", "file", "which",

        # Localization & Network Management
        "locale", "localedef", "nmcli", "nmtui", "NetworkManager",

        # Audio & Multimedia Stack (PipeWire, WirePlumber, ALSA)
        "pipewire", "pipewire-pulse", "wireplumber", "pw-cat", "pw-cli", "pw-top", "pw-mon", "wpctl", "pactl",
        "alsamixer", "amixer", "aplay", "speaker-test"
    ]

    all_libs = set()
    copied_bins = 0

    # Locate and copy all binaries
    for name in all_bins:
        existing = root / "usr/bin" / name
        if existing.exists():
            resolve_deps(str(existing), all_libs)
            copied_bins += 1
            continue
        existing_libexec = root / "usr/libexec" / name
        if existing_libexec.exists():
            resolve_deps(str(existing_libexec), all_libs)
            copied_bins += 1
            continue

        path = shutil.which(name)
        if not path:
            candidate = Path("/usr/lib/systemd") / name
            if candidate.exists():
                path = str(candidate)
            else:
                candidate = Path("/usr/sbin") / name
                if candidate.exists():
                    path = str(candidate)
        
        if path and os.path.exists(path):
            if os.path.islink(path):
                target = os.readlink(path)
                dest = root / path.lstrip("/")
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.is_symlink() or dest.exists():
                    dest.unlink()
                if target.startswith(".."):
                    target = os.path.realpath(path)
                dest.symlink_to(target)
                real_p = os.path.realpath(path)
                if os.path.exists(real_p):
                    real_dest = root / real_p.lstrip("/")
                    real_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(real_p, real_dest)
                    resolve_deps(real_p, all_libs)
            else:
                dest = root / path.lstrip("/")
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    shutil.copy2(path, dest)
                resolve_deps(path, all_libs)
            copied_bins += 1

    # Explicit clean symlinks for GNOME Weather and Characters
    weather_target = root / "usr/share/org.gnome.Weather/org.gnome.Weather"
    if weather_target.exists():
        wb = root / "usr/bin/gnome-weather"
        if wb.exists() or wb.is_symlink():
            wb.unlink()
        wb.symlink_to("/usr/share/org.gnome.Weather/org.gnome.Weather")

    char_target = root / "usr/share/org.gnome.Characters/org.gnome.Characters"
    if char_target.exists():
        cb = root / "usr/bin/gnome-characters"
        if cb.exists() or cb.is_symlink():
            cb.unlink()
        cb.symlink_to("/usr/share/org.gnome.Characters/org.gnome.Characters")

    # Python link /usr/bin/python -> python3
    py_link = root / "usr/bin/python"
    if py_link.exists() or py_link.is_symlink():
        py_link.unlink()
    py_link.symlink_to("python3")

    # Copy all binaries in /usr/lib/systemd
    for item in Path("/usr/lib/systemd").iterdir():
        if item.is_file() and os.access(item, os.X_OK):
            dest = root / item.as_posix().lstrip("/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(item, dest)
                resolve_deps(str(item), all_libs)

    # Copy systemd system-generators
    if Path("/usr/lib/systemd/system-generators").exists():
        shutil.copytree("/usr/lib/systemd/system-generators", root / "usr/lib/systemd/system-generators", dirs_exist_ok=True)
        for gen in (root / "usr/lib/systemd/system-generators").iterdir():
            if gen.is_file() and os.access(gen, os.X_OK):
                resolve_deps(str(gen), all_libs)

    # Copy Python 3.14 standard library
    py_lib_src = Path("/usr/lib64/python3.14")
    py_lib_dest = root / "usr/lib64/python3.14"
    if py_lib_src.exists():
        print("Copying Python 3.14 standard library...")
        shutil.copytree(py_lib_src, py_lib_dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        dynload = py_lib_src / "lib-dynload"
        if dynload.exists():
            for so in dynload.glob("*.so"):
                resolve_deps(str(so), all_libs)

    # Include NSS, PAM, BPF, kmod, seccomp, cryptsetup, seat, dri, graphics libs explicitly
    for p in Path("/usr/lib64").glob("libnss*"):
        all_libs.add(str(p))
    for p in Path("/usr/lib64").glob("libbpf*"):
        all_libs.add(str(p))
    for p in Path("/usr/lib64").glob("libkmod*"):
        all_libs.add(str(p))
    for p in Path("/usr/lib64").glob("libseccomp*"):
        all_libs.add(str(p))
    for p in Path("/usr/lib64").glob("libcryptsetup*"):
        all_libs.add(str(p))
    for p in Path("/usr/lib64/security").glob("*.so*"):
        all_libs.add(str(p))
    for p in Path("/usr/lib64/systemd").glob("*.so*"):
        all_libs.add(str(p))
    for p in (root / "usr/lib64/dri").glob("*.so*"):
        all_libs.add(str(p))
    for p in (root / "usr/lib64").glob("*.so*"):
        all_libs.add(str(p))

    # Install GNOME desktop stack (Shell, Mutter, GDM, GJS, schemas, assets)
    install_gnome_desktop(root, all_libs)

    # Install standard desktop applications (Firefox, LibreOffice, GNOME apps, schemas, icons)
    install_desktop_applications(root, all_libs)

    # Resolve dependencies transitively
    for lib in list(all_libs):
        resolve_deps(lib, all_libs)

    # Copy all libraries
    print(f"Installing {len(all_libs)} shared libraries...")
    for lib in all_libs:
        if os.path.exists(lib):
            dest = root / lib.lstrip("/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(lib, dest)

    # Copy terminfo database
    if Path("/usr/share/terminfo").exists():
        print("Copying terminfo database...")
        shutil.copytree("/usr/share/terminfo", root / "usr/share/terminfo", dirs_exist_ok=True)

    # Copy C.utf8 locale
    loc_src = Path("/usr/lib/locale/C.utf8")
    if loc_src.exists():
        print("Copying C.utf8 locale...")
        loc_dest = root / "usr/lib/locale/C.utf8"
        loc_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(loc_src, loc_dest, dirs_exist_ok=True)
        for l_sym in ["C.UTF-8", "en_US.utf8", "en_US.UTF-8"]:
            target_sym = root / "usr/lib/locale" / l_sym
            if not target_sym.exists():
                target_sym.symlink_to("C.utf8")

    # Copy nano syntax definitions
    if Path("/usr/share/nano").exists():
        shutil.copytree("/usr/share/nano", root / "usr/share/nano", dirs_exist_ok=True)
    if Path("/etc/nanorc").exists():
        shutil.copy2("/etc/nanorc", root / "etc/nanorc")

    # Copy vim runtime
    if Path("/usr/share/vim").exists():
        shutil.copytree("/usr/share/vim", root / "usr/share/vim", dirs_exist_ok=True)

    # Copy CA certificates
    ca_file = Path("/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem")
    if ca_file.exists():
        print("Copying SSL CA certificates...")
        (root / "etc/ssl/certs").mkdir(parents=True, exist_ok=True)
        (root / "etc/pki/tls/certs").mkdir(parents=True, exist_ok=True)
        shutil.copy2(ca_file, root / "etc/ssl/certs/ca-certificates.crt")
        shutil.copy2(ca_file, root / "etc/pki/tls/certs/ca-bundle.crt")

    # Install kernel modules from freshly built Linux 7.2.13 with Rust for Linux
    kernel_build_dir = BUILD_DIR / "kernel_build" / "linux-7.2.13"
    if kernel_build_dir.exists():
        print("Installing kernel modules from compiled Linux 7.2.13 tree...")
        subprocess.run(
            ["make", "-C", str(kernel_build_dir), f"INSTALL_MOD_PATH={root}", "modules_install"],
            check=True
        )
        # Clean build and source symlinks
        for mod_dir in (root / "lib/modules").glob("*"):
            for link in ["build", "source"]:
                lpath = mod_dir / link
                if lpath.exists() or lpath.is_symlink():
                    lpath.unlink(missing_ok=True)
    elif Path("/lib/modules/7.2.11-200.fc44.x86_64").exists():
        print("Fallback copying kernel modules...")
        shutil.copytree("/lib/modules/7.2.11-200.fc44.x86_64", root / "lib/modules/7.2.11-200.fc44.x86_64",
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns("build", "source"))

    # Copy all helpers in /usr/libexec/openssh
    ssh_libexec = Path("/usr/libexec/openssh")
    if ssh_libexec.exists():
        print("Copying OpenSSH server helpers...")
        shutil.copytree(ssh_libexec, root / "usr/libexec/openssh", dirs_exist_ok=True)
        for h in (root / "usr/libexec/openssh").iterdir():
            if h.is_file() and os.access(h, os.X_OK):
                resolve_deps(str(h), all_libs)

    # Resolve dependencies for sudo plugins and helpers
    root_sudo_libexec = root / "usr/libexec/sudo"
    if root_sudo_libexec.exists():
        for h in root_sudo_libexec.iterdir():
            if h.is_file():
                all_libs.add(str(h))
                resolve_deps(str(h), all_libs)

def install_systemd_units(root: Path):
    """Install and enable systemd units for system initialization, networking, D-Bus, and GNOME desktop."""
    sysd_src = Path("/usr/lib/systemd/system")
    sysd_dest = root / "usr/lib/systemd/system"

    essential_units = [
        "basic.target", "sysinit.target", "multi-user.target", "graphical.target",
        "sockets.target", "timers.target", "paths.target", "slices.target",
        "local-fs.target", "local-fs-pre.target", "network.target",
        "systemd-journald.service", "systemd-journald.socket",
        "systemd-journald-dev-log.socket", "systemd-udevd.service",
        "systemd-udevd-control.socket", "systemd-udevd-kernel.socket",
        "systemd-udev-trigger.service",
        "systemd-modules-load.service", "systemd-sysctl.service",
        "systemd-remount-fs.service", "systemd-tmpfiles-setup.service",
        "systemd-tmpfiles-setup-dev.service",
        "systemd-random-seed.service", "systemd-networkd.service",
        "systemd-networkd.socket", "systemd-resolved.service",
        "systemd-timesyncd.service", "systemd-logind.service",
        "systemd-timedated.service", "systemd-hostnamed.service", "systemd-localed.service",
        "systemd-user-sessions.service", "user@.service", "user-runtime-dir@.service",
        "user.slice", "system.slice",
        "poweroff.target", "reboot.target", "halt.target", "shutdown.target",
        "umount.target", "final.target", "kexec.target", "sigpwr.target",
        "systemd-poweroff.service", "systemd-reboot.service", "systemd-halt.service",
        "tmp.mount", "sshd.service", "dbus.socket", "dbus-daemon.service",
        "gdm.service", "accounts-daemon.service", "rtkit-daemon.service"
    ]

    for u in essential_units:
        src_path = sysd_src / u
        if src_path.exists():
            if src_path.is_symlink():
                t = os.readlink(src_path)
                d = sysd_dest / u
                if d.exists() or d.is_symlink(): d.unlink()
                d.symlink_to(t)
            elif src_path.is_file():
                shutil.copy2(src_path, sysd_dest / u)
            elif src_path.is_dir():
                shutil.copytree(src_path, sysd_dest / u, dirs_exist_ok=True)

    # Copy drop-in directories if present
    for d_name in ["user@.service.d", "user-.slice.d"]:
        src_d = sysd_src / d_name
        if src_d.exists():
            shutil.copytree(src_d, sysd_dest / d_name, dirs_exist_ok=True)

    # Copy base systemd user units
    user_src = Path("/usr/lib/systemd/user")
    user_dest = root / "usr/lib/systemd/user"
    user_dest.mkdir(parents=True, exist_ok=True)
    if user_src.exists():
        shutil.copytree(user_src, user_dest, dirs_exist_ok=True)

    # Enable dbus.socket and audio services for user sessions
    (root / "etc/systemd/user/sockets.target.wants").mkdir(parents=True, exist_ok=True)
    (root / "etc/systemd/user/default.target.wants").mkdir(parents=True, exist_ok=True)
    (root / "usr/lib/systemd/user/sockets.target.wants").mkdir(parents=True, exist_ok=True)
    user_dbus_sock = root / "usr/lib/systemd/user/sockets.target.wants/dbus.socket"
    if user_dbus_sock.exists() or user_dbus_sock.is_symlink(): user_dbus_sock.unlink()
    user_dbus_sock.symlink_to("../dbus.socket")
    user_dbus_svc = root / "usr/lib/systemd/user/dbus.service"
    if user_dbus_svc.exists() or user_dbus_svc.is_symlink(): user_dbus_svc.unlink()
    user_dbus_svc.symlink_to("dbus-daemon.service")

    # Wire up PipeWire and WirePlumber user services
    for u_sock in ["pipewire.socket", "pipewire-pulse.socket"]:
        s_src = root / "usr/lib/systemd/user" / u_sock
        if s_src.exists():
            s_dst = root / "etc/systemd/user/sockets.target.wants" / u_sock
            if s_dst.exists() or s_dst.is_symlink(): s_dst.unlink()
            s_dst.symlink_to(f"/usr/lib/systemd/user/{u_sock}")
    for u_svc in ["pipewire.service", "wireplumber.service"]:
        s_src = root / "usr/lib/systemd/user" / u_svc
        if s_src.exists():
            s_dst = root / "etc/systemd/user/default.target.wants" / u_svc
            if s_dst.exists() or s_dst.is_symlink(): s_dst.unlink()
            s_dst.symlink_to(f"/usr/lib/systemd/user/{u_svc}")

    # Unconditionally force animations in GNOME Shell systemd user units
    shell_unit = root / "usr/lib/systemd/user/org.gnome.Shell@.service"
    if shell_unit.exists():
        unit_text = shell_unit.read_text()
        unit_text = unit_text.replace(
            "ExecStart=/usr/bin/gnome-shell --mode=%i",
            "ExecStart=/usr/bin/gnome-shell --mode=%i --force-animations"
        )
        shell_unit.write_text(unit_text)

    # Install drop-in units across all potential shell service paths
    dropin_conf = """[Service]
ExecStart=
ExecStart=/usr/bin/gnome-shell --mode=%i --force-animations
"""
    for dropin_dir in [
        root / "usr/lib/systemd/user/org.gnome.Shell@.service.d",
        root / "usr/lib/systemd/user/org.gnome.Shell@user.service.d",
        root / "usr/lib/systemd/user/org.gnome.Shell@gdm.service.d",
        root / "usr/lib/systemd/user/org.gnome.Shell@classic.service.d",
        root / "etc/systemd/user/org.gnome.Shell@.service.d",
        root / "etc/systemd/user/org.gnome.Shell@user.service.d",
        root / "etc/systemd/user/org.gnome.Shell@gdm.service.d",
    ]:
        dropin_dir.mkdir(parents=True, exist_ok=True)
        (dropin_dir / "10-force-animations.conf").write_text(dropin_conf)

    # Install wrapper in /usr/local/bin so manual CLI invocations also force animations
    local_gs = root / "usr/local/bin/gnome-shell"
    local_gs.parent.mkdir(parents=True, exist_ok=True)
    local_gs.write_text("""#!/usr/bin/bash
# Wrapper to ensure --force-animations is supplied to GNOME Shell
for arg in "$@"; do
    if [ "$arg" = "--force-animations" ]; then
        exec /usr/bin/gnome-shell "$@"
    fi
done
exec /usr/bin/gnome-shell --force-animations "$@"
""")
    local_gs.chmod(0o755)

    # Set up systemd D-Bus aliases for timedate1, hostname1, and locale1
    for alias, target in [
        ("dbus-org.freedesktop.timedate1.service", "systemd-timedated.service"),
        ("dbus-org.freedesktop.hostname1.service", "systemd-hostnamed.service"),
        ("dbus-org.freedesktop.locale1.service", "systemd-localed.service"),
        ("dbus-org.freedesktop.Accounts.service", "accounts-daemon.service"),
    ]:
        a_dst = root / "usr/lib/systemd/system" / alias
        if a_dst.exists() or a_dst.is_symlink(): a_dst.unlink()
        a_dst.symlink_to(target)

    # PAM configuration for systemd-user
    (root / "etc/pam.d/systemd-user").write_text("""#%PAM-1.0
account  sufficient pam_unix.so
account  required   pam_permit.so
session  required   pam_loginuid.so
session  optional   pam_keyinit.so force revoke
session  required   pam_permit.so
session  optional   pam_systemd.so
""")

    # Enable user lingering for myelinos user so user manager starts on boot
    linger_dir = root / "var/lib/systemd/linger"
    linger_dir.mkdir(parents=True, exist_ok=True)
    (linger_dir / "myelinos").touch()

    # Set up dbus.service symlinks in /usr/lib and /etc/systemd/system
    dbus_svc = root / "usr/lib/systemd/system/dbus.service"
    if dbus_svc.exists() or dbus_svc.is_symlink():
        dbus_svc.unlink()
    dbus_svc.symlink_to("dbus-daemon.service")

    etc_dbus = root / "etc/systemd/system/dbus.service"
    if etc_dbus.exists() or etc_dbus.is_symlink():
        etc_dbus.unlink()
    etc_dbus.symlink_to("/usr/lib/systemd/system/dbus-daemon.service")

    # Set up dbus machine-id
    (root / "var/lib/dbus").mkdir(parents=True, exist_ok=True)
    m_id_link = root / "var/lib/dbus/machine-id"
    if m_id_link.exists() or m_id_link.is_symlink():
        m_id_link.unlink()
    m_id_link.symlink_to("/etc/machine-id")

    # Systemd tmpfiles configuration for runtime dirs
    tmpfiles_dir = root / "usr/lib/tmpfiles.d"
    tmpfiles_dir.mkdir(parents=True, exist_ok=True)
    (tmpfiles_dir / "myelinos.conf").write_text("""# Storage and runtime directories for MyelinOS GNOME, D-Bus, X11, and sudo
d /run/user 0755 root root -
d /run/user/0 0700 root root -
d /run/user/1000 0700 myelinos myelinos -
d /run/user/42 0700 gdm gdm -
d /run/systemd/seats 0755 root root -
d /run/dbus 0755 dbus dbus -
d /run/sudo 0711 root root -
d /var/db/sudo 0700 root root -
d /var/lib/dbus 0755 root root -
d /var/lib/gdm 0770 gdm gdm -
d /var/lib/AccountsService 0775 root root -
L /var/lib/dbus/machine-id - - - - /etc/machine-id
d /tmp/.X11-unix 1777 root root -
z /dev/input/* 0666 root input -
z /dev/dri/* 0666 root video -
""")

    # Enable essential services in sysinit / multi-user targets
    for s in ["systemd-journald.service", "systemd-udevd.service",
              "systemd-udev-trigger.service",
              "systemd-tmpfiles-setup.service", "systemd-tmpfiles-setup-dev.service",
              "systemd-modules-load.service", "systemd-sysctl.service"]:
        link = root / "etc/systemd/system/sysinit.target.wants" / s
        if not link.exists():
            link.symlink_to(f"/usr/lib/systemd/system/{s}")

    for s in ["systemd-networkd.service", "systemd-resolved.service", "sshd.service",
              "systemd-logind.service", "systemd-user-sessions.service", "dbus.service",
              "accounts-daemon.service"]:
        target_name = "dbus-daemon.service" if s == "dbus.service" else s
        link = root / "etc/systemd/system/multi-user.target.wants" / s
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(f"/usr/lib/systemd/system/{target_name}")

    # Enable dbus.socket in sockets.target.wants
    dbus_sock_link = root / "etc/systemd/system/sockets.target.wants/dbus.socket"
    if dbus_sock_link.exists() or dbus_sock_link.is_symlink():
        dbus_sock_link.unlink()
    dbus_sock_link.symlink_to("/usr/lib/systemd/system/dbus.socket")

    # Set default target to graphical.target
    default_target = root / "etc/systemd/system/default.target"
    if default_target.exists() or default_target.is_symlink():
        default_target.unlink()
    default_target.symlink_to("/usr/lib/systemd/system/graphical.target")

    # DHCP Network configuration for all ethernet interfaces
    (root / "etc/systemd/network/80-dhcp.network").write_text("""[Match]
Name=en* eth*

[Network]
DHCP=yes
""")

    # Clean serial getty unit without dev-ttyS0 device binding for direct serial boot
    serial_unit = root / "etc/systemd/system/serial-getty@.service"
    serial_unit.write_text("""[Unit]
Description=Serial Getty on %I
Documentation=man:agetty(8) man:systemd-getty-generator(8)
After=systemd-user-sessions.service plymouth-quit-wait.service
Before=getty.target
IgnoreOnIsolate=yes

[Service]
ExecStart=-/usr/bin/agetty -o '-p -- \\\\u' --noclear --autologin root %I 115200,38400,9600 linux
Type=idle
Restart=always
UtmpIdentifier=%I
TTYPath=/dev/%I
TTYReset=yes
TTYVHangup=yes
KillMode=process
IgnoreSIGPIPE=no
SendSIGHUP=yes

[Install]
WantedBy=getty.target
""")

    # Symlink serial-getty@ttyS0.service to both getty.target and multi-user.target
    ttyS0_link = root / "etc/systemd/system/getty.target.wants/serial-getty@ttyS0.service"
    if ttyS0_link.exists() or ttyS0_link.is_symlink():
        ttyS0_link.unlink()
    ttyS0_link.symlink_to("/etc/systemd/system/serial-getty@.service")

    ttyS0_multi = root / "etc/systemd/system/multi-user.target.wants/serial-getty@ttyS0.service"
    if ttyS0_multi.exists() or ttyS0_multi.is_symlink():
        ttyS0_multi.unlink()
    ttyS0_multi.symlink_to("/etc/systemd/system/serial-getty@.service")

    # Remove any obsolete gnome.service file and links
    legacy_gnome = root / "usr/lib/systemd/system/gnome.service"
    if legacy_gnome.exists():
        legacy_gnome.unlink()
    for legacy_link in [
        root / "etc/systemd/system/graphical.target.wants/gnome.service",
        root / "etc/systemd/system/multi-user.target.wants/gnome.service"
    ]:
        if legacy_link.exists() or legacy_link.is_symlink():
            legacy_link.unlink()

    # Enable gdm.service in graphical.target.wants and as display-manager.service
    dm_link = root / "etc/systemd/system/display-manager.service"
    if dm_link.exists() or dm_link.is_symlink():
        dm_link.unlink()
    dm_link.symlink_to("/usr/lib/systemd/system/gdm.service")

    gdm_link = root / "etc/systemd/system/graphical.target.wants/gdm.service"
    if gdm_link.exists() or gdm_link.is_symlink():
        gdm_link.unlink()
    gdm_link.symlink_to("/usr/lib/systemd/system/gdm.service")

def install_configuration_files(root: Path):
    """Install core LFS, user account, PAM, DRM/udev, and environment configurations."""
    print("Writing system configuration files...")
    
    # /etc/os-release
    (root / "etc/os-release").write_text("""NAME="MyelinOS"
PRETTY_NAME="MyelinOS 0.1 (LFS systemd + GNOME 50 Desktop)"
ID=myelinos
ID_LIKE=lfs
VERSION="0.1"
VERSION_ID="0.1"
HOME_URL="https://github.com/myelinos"
""")

    # /etc/hostname & /etc/hosts
    (root / "etc/hostname").write_text("myelinos\n")
    (root / "etc/hosts").write_text("""127.0.0.1   localhost myelinos
::1         localhost ip6-localhost ip6-loopback
""")

    # /etc/resolv.conf & /etc/nsswitch.conf
    (root / "etc/resolv.conf").write_text("""nameserver 8.8.8.8
nameserver 1.1.1.1
""")
    (root / "etc/nsswitch.conf").write_text("""passwd:      files
group:       files
shadow:      files
hosts:       files resolve [!UNAVAIL=return] dns
networks:    files
protocols:   files
services:    files
ethers:      files
rpc:         files
""")

    # /etc/passwd (with root, dbus, gdm, and myelinos desktop user)
    (root / "etc/passwd").write_text("""root:x:0:0:root:/root:/bin/bash
bin:x:1:1:bin:/bin:/bin/false
daemon:x:2:2:daemon:/sbin:/bin/false
adm:x:3:4:adm:/var/adm:/bin/false
lp:x:4:7:lp:/var/spool/lpd:/bin/false
sync:x:5:0:sync:/sbin:/bin/sync
shutdown:x:6:0:shutdown:/sbin:/sbin/shutdown
halt:x:7:0:halt:/sbin:/sbin/halt
mail:x:8:12:mail:/var/spool/mail:/bin/false
operator:x:11:0:operator:/root:/bin/false
dbus:x:81:81:System Message Bus:/:/usr/sbin/nologin
polkitd:x:114:114:User for polkitd:/:/usr/sbin/nologin
rtkit:x:980:980:RealtimeKit:/:/usr/sbin/nologin
colord:x:974:974:colord colour management daemon:/var/lib/colord:/usr/sbin/nologin
geoclue:x:976:976:User for geoclue:/var/lib/geoclue:/usr/sbin/nologin
malcontent-timerd:x:975:975:User for malcontent-timerd:/var/lib/malcontent-timerd:/usr/sbin/nologin
gdm:x:42:42:GNOME Display Manager:/var/lib/gdm:/usr/sbin/nologin
sshd:x:74:74:Privilege-separated SSH:/usr/share/empty.sshd:/bin/false
myelinos:x:1000:1000:MyelinOS User:/home/myelinos:/bin/bash
systemd-journal:x:999:999:systemd-journal:/:/bin/false
systemd-network:x:998:998:systemd-network:/:/bin/false
systemd-resolve:x:997:997:systemd-resolve:/:/bin/false
systemd-timesync:x:996:996:systemd-timesync:/:/bin/false
systemd-coredump:x:995:995:systemd-coredump:/:/bin/false
nobody:x:65534:65534:Kernel Overflow User:/:/bin/false
""")

    # /etc/shadow
    (root / "etc/shadow").write_text("""root::19000:0:99999:7:::
bin:*:19000:0:99999:7:::
daemon:*:19000:0:99999:7:::
adm:*:19000:0:99999:7:::
lp:*:19000:0:99999:7:::
sync:*:19000:0:99999:7:::
shutdown:*:19000:0:99999:7:::
halt:*:19000:0:99999:7:::
mail:*:19000:0:99999:7:::
operator:*:19000:0:99999:7:::
dbus:*:19000:0:99999:7:::
polkitd:*:19000:0:99999:7:::
rtkit:*:19000:0:99999:7:::
colord:*:19000:0:99999:7:::
geoclue:*:19000:0:99999:7:::
malcontent-timerd:*:19000:0:99999:7:::
gdm:*:19000:0:99999:7:::
sshd:*:19000:0:99999:7:::
myelinos::19000:0:99999:7:::
systemd-journal:*:19000:0:99999:7:::
systemd-network:*:19000:0:99999:7:::
systemd-resolve:*:19000:0:99999:7:::
systemd-timesync:*:19000:0:99999:7:::
systemd-coredump:*:19000:0:99999:7:::
nobody:*:19000:0:99999:7:::
""")

    # /etc/group
    (root / "etc/group").write_text("""root:x:0:
bin:x:1:
daemon:x:2:
sys:x:3:
adm:x:4:
tty:x:5:
disk:x:6:
lp:x:7:
mem:x:8:
kmem:x:9:
wheel:x:10:root,myelinos
cdrom:x:11:
mail:x:12:
video:x:39:myelinos,root,gdm
utmp:x:43:
audio:x:63:myelinos,root
gdm:x:42:
rtkit:x:980:
colord:x:974:
geoclue:x:976:
malcontent-timerd:x:975:
sshd:x:74:
dbus:x:81:
polkitd:x:114:
input:x:107:myelinos,root,gdm
render:x:108:myelinos,root,gdm
seat:x:109:myelinos,root,gdm
myelinos:x:1000:
systemd-journal:x:999:myelinos,root
systemd-network:x:998:
systemd-resolve:x:997:
systemd-timesync:x:996:
systemd-coredump:x:995:
nogroup:x:65534:
""")

    # /etc/udev/rules.d/99-dri.rules (Ensure DRM and input accessibility)
    (root / "etc/udev/rules.d/99-dri.rules").write_text("""KERNEL=="card[0-9]*", SUBSYSTEM=="drm", MODE="0666", GROUP="video"
KERNEL=="renderD[0-9]*", SUBSYSTEM=="drm", MODE="0666", GROUP="render"
KERNEL=="event[0-9]*", SUBSYSTEM=="input", MODE="0666", GROUP="input"
KERNEL=="uinput", SUBSYSTEM=="misc", MODE="0666"
""")

    # /etc/modules-load.d/virtio-gpu.conf (Auto-load virtio-gpu driver on boot)
    (root / "etc/modules-load.d").mkdir(parents=True, exist_ok=True)
    (root / "etc/modules-load.d/virtio-gpu.conf").write_text("virtio_gpu\n")

    # /etc/fstab
    (root / "etc/fstab").write_text("""LABEL=MYELINOS_ROOT    /          ext4   defaults,noatime             0 1
LABEL=ESP              /boot/efi  vfat   umask=0077,noatime,nofail   0 2
tmpfs                  /tmp       tmpfs  defaults,nosuid,nodev        0 0
""")

    # /etc/profile
    (root / "etc/profile").write_text(r"""export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/usr/libexec:/sbin:/bin
export TERM=linux
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export XDG_CURRENT_DESKTOP=GNOME
export XDG_SESSION_DESKTOP=GNOME
export XDG_SESSION_TYPE=wayland
export SAL_USE_VCLPLUGIN=gtk3
export MOZ_ENABLE_WAYLAND=1
export GDK_BACKEND=wayland,x11
export XDG_DATA_DIRS=/usr/local/share:/usr/share
export XDG_CONFIG_DIRS=/etc/xdg

if [ -z "$XDG_RUNTIME_DIR" ]; then
    export XDG_RUNTIME_DIR="/run/user/$(id -u)"
    mkdir -p "$XDG_RUNTIME_DIR" 2>/dev/null || true
    chmod 700 "$XDG_RUNTIME_DIR" 2>/dev/null || true
fi

if [ -z "$HOME" ]; then
    export HOME="$(getent passwd $(id -u) | cut -d: -f6)"
fi
if [ -z "$USER" ]; then
    export USER="$(id -un)"
fi

export PS1='[\u@\h \W]\$ '
umask 022

alias ls='ls --color=auto'
alias ll='ls -la --color=auto'
alias la='ls -A --color=auto'
alias l='ls -CF --color=auto'
alias grep='grep --color=auto'
alias egrep='egrep --color=auto'
alias fgrep='fgrep --color=auto'
""")

    # /etc/environment
    (root / "etc/environment").write_text("""XDG_CURRENT_DESKTOP=GNOME
XDG_SESSION_DESKTOP=GNOME
XDG_SESSION_TYPE=wayland
SAL_USE_VCLPLUGIN=gtk3
MOZ_ENABLE_WAYLAND=1
GDK_BACKEND=wayland,x11
LANG=en_US.UTF-8
LC_ALL=en_US.UTF-8
PATH=/usr/local/bin:/usr/bin:/usr/libexec:/usr/sbin:/bin:/sbin
XDG_DATA_DIRS=/usr/local/share:/usr/share
XDG_CONFIG_DIRS=/etc/xdg
""")

    # /etc/locale.conf
    (root / "etc/locale.conf").write_text("""LANG=en_US.UTF-8
LC_ALL=en_US.UTF-8
""")

    # /etc/profile.d/gnome.sh
    (root / "etc/profile.d").mkdir(parents=True, exist_ok=True)
    (root / "etc/profile.d/gnome.sh").write_text("""export XDG_CURRENT_DESKTOP=GNOME
export XDG_SESSION_DESKTOP=GNOME
export XDG_SESSION_TYPE=wayland
export SAL_USE_VCLPLUGIN=gtk3
export MOZ_ENABLE_WAYLAND=1
export GDK_BACKEND=wayland,x11
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export PATH=/usr/local/bin:/usr/bin:/usr/libexec:/usr/sbin:/bin:/sbin
export XDG_DATA_DIRS=/usr/local/share:/usr/share
export XDG_CONFIG_DIRS=/etc/xdg
""")

    # Mask failing user units that have no backends installed
    user_systemd = root / "etc/systemd/user"
    user_systemd.mkdir(parents=True, exist_ok=True)
    for s in ["evolution-alarm-notify.service", "evolution-source-registry.service", "evolution-calendar-factory.service", "evolution-addressbook-factory.service"]:
        link = user_systemd / s
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to("/dev/null")

    # Clean up host-specific proprietary graphics driver artifacts that break Mesa/Vulkan in VMs
    for nv_pat in [
        "usr/share/vulkan/icd.d/*nvidia*",
        "usr/share/glvnd/egl_vendor.d/*nvidia*",
        "usr/lib64/*nvidia*",
        "usr/lib/udev/rules.d/*nvidia*"
    ]:
        for nv_file in root.glob(nv_pat):
            try:
                nv_file.unlink()
            except Exception:
                pass

    # /root/.bashrc & /home/myelinos/.bashrc
    (root / "root/.bashrc").write_text(r"""export PS1='[\u@\h \W]\$ '
alias ll='ls -la --color=auto'
alias la='ls -A --color=auto'
""")
    (root / "home/myelinos/.bashrc").write_text(r"""export PS1='[\u@\h \W]\$ '
alias ll='ls -la --color=auto'
alias la='ls -A --color=auto'
""")

    # Standard XDG user directories & config
    user_dirs = ["Desktop", "Downloads", "Documents", "Pictures", "Music", "Videos", "Templates", "Public"]
    for d in user_dirs:
        (root / f"home/myelinos/{d}").mkdir(parents=True, exist_ok=True)
        (root / f"etc/skel/{d}").mkdir(parents=True, exist_ok=True)

    config_user_dirs = """# This file is written by xdg-user-dirs-update
# Format is XDG_xxx_DIR="$HOME/yyy"
XDG_DESKTOP_DIR="$HOME/Desktop"
XDG_DOWNLOAD_DIR="$HOME/Downloads"
XDG_TEMPLATES_DIR="$HOME/Templates"
XDG_PUBLICSHARE_DIR="$HOME/Public"
XDG_DOCUMENTS_DIR="$HOME/Documents"
XDG_MUSIC_DIR="$HOME/Music"
XDG_PICTURES_DIR="$HOME/Pictures"
XDG_VIDEOS_DIR="$HOME/Videos"
"""
    (root / "home/myelinos/.config").mkdir(parents=True, exist_ok=True)
    (root / "home/myelinos/.config/user-dirs.dirs").write_text(config_user_dirs)
    (root / "etc/skel/.config").mkdir(parents=True, exist_ok=True)
    (root / "etc/skel/.config/user-dirs.dirs").write_text(config_user_dirs)

    # /etc/issue
    (root / "etc/issue").write_text(r"""\S - MyelinOS LFS (systemd + GNOME 50) 0.1 (\l)
Kernel \r on an \m

""")

    # /etc/systemd/system.conf
    (root / "etc/systemd/system.conf").write_text("""[Manager]
LogLevel=info
LogTarget=console
ShowStatus=yes
StatusUnitFormat=combined
""")

    # Empty machine-id so systemd commits its generated machine-id
    (root / "etc/machine-id").touch()

    # Log files
    for lf in ["var/run/utmp", "var/log/wtmp", "var/log/lastlog"]:
        (root / lf).touch()

    # PAM configuration with pam_systemd.so session support
    (root / "etc/pam.d/other").write_text("""#%PAM-1.0
auth        required    pam_permit.so
account     required    pam_permit.so
password    required    pam_permit.so
session     required    pam_permit.so
session     optional    pam_systemd.so
""")
    (root / "etc/pam.d/system-auth").write_text("""#%PAM-1.0
auth        sufficient  pam_permit.so
auth        required    pam_unix.so nullok
account     required    pam_permit.so
password    required    pam_permit.so
session     required    pam_permit.so
session     optional    pam_systemd.so
""")
    (root / "etc/pam.d/login").write_text("""#%PAM-1.0
auth        sufficient  pam_permit.so
auth        required    pam_unix.so nullok
account     required    pam_permit.so
password    required    pam_permit.so
session     required    pam_permit.so
session     optional    pam_systemd.so
""")
    (root / "etc/pam.d/sudo").write_text("""#%PAM-1.0
auth        sufficient  pam_permit.so
auth        required    pam_unix.so nullok
account     required    pam_permit.so
password    required    pam_permit.so
session     required    pam_permit.so
session     optional    pam_systemd.so
""")
    (root / "etc/pam.d/sudo-i").write_text("""#%PAM-1.0
auth        sufficient  pam_permit.so
auth        required    pam_unix.so nullok
account     required    pam_permit.so
password    required    pam_permit.so
session     required    pam_permit.so
session     optional    pam_systemd.so
""")

    (root / "etc/pam.d/postlogin").write_text("""#%PAM-1.0
session     required    pam_permit.so
session     optional    pam_systemd.so
""")
    if Path("/etc/security").exists():
        (root / "etc/security").mkdir(parents=True, exist_ok=True)
        for item in Path("/etc/security").iterdir():
            try:
                dest = root / "etc/security" / item.name
                if item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)
            except Exception:
                pass

    # Sudoers configuration
    sudoers_file = root / "etc/sudoers"
    sudoers_file.write_text("""Defaults   !visiblepw
Defaults   always_set_home
Defaults   match_group_by_gid
Defaults   always_query_group_plugin
Defaults   env_reset
Defaults   env_keep =  "COLORS DISPLAY HOSTNAME HISTSIZE KDEDIR LS_COLORS"
Defaults   env_keep += "MAIL PS1 PS2 QTDIR USERNAME LANG LC_ADDRESS LC_CTYPE"
Defaults   env_keep += "LC_COLLATE LC_IDENTIFICATION LC_MEASUREMENT LC_MESSAGES"
Defaults   env_keep += "LC_MONETARY LC_NAME LC_NUMERIC LC_PAPER LC_TELEPHONE"
Defaults   env_keep += "LC_TIME LC_ALL LANGUAGE LINGUAS _XKB_CHARSET XAUTHORITY"
Defaults   secure_path = /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

root ALL=(ALL:ALL) ALL
%wheel ALL=(ALL:ALL) NOPASSWD: ALL
""")
    sudoers_file.chmod(0o440)
    (root / "etc/sudoers.d").mkdir(parents=True, exist_ok=True)
    (root / "etc/sudoers.d").chmod(0o750)

    # SSH Configuration
    ssh_dir = root / "etc/ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    (ssh_dir / "sshd_config").write_text("""Port 22
ListenAddress 0.0.0.0
PermitRootLogin yes
PermitEmptyPasswords yes
PasswordAuthentication yes
ChallengeResponseAuthentication no
UsePAM yes
PrintMotd no
Subsystem sftp /usr/libexec/openssh/sftp-server
""")

    # Pre-generate SSH Host Keys
    for ktype in ["ed25519", "rsa", "ecdsa"]:
        key_file = ssh_dir / f"ssh_host_{ktype}_key"
        if not key_file.exists():
            subprocess.run(
                ["ssh-keygen", "-t", ktype, "-f", str(key_file), "-N", "", "-q"],
                check=False
            )

def build_disk_image():
    """Create a 5.5GB ext4 filesystem disk image using podman unshare for proper root permissions."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Copy kernel to images directory and rootfs /boot
    (ROOTFS_DIR / "boot").mkdir(parents=True, exist_ok=True)
    if KERNEL_SRC.exists():
        print(f"Installing kernel {KERNEL_SRC} -> {KERNEL_DEST}...")
        shutil.copy2(KERNEL_SRC, KERNEL_DEST)
        shutil.copy2(KERNEL_SRC, ROOTFS_DIR / "boot" / "vmlinuz")
    elif not KERNEL_DEST.exists():
        raise FileNotFoundError(f"Kernel source not found at {KERNEL_SRC}")
    else:
        shutil.copy2(KERNEL_DEST, ROOTFS_DIR / "boot" / "vmlinuz")

    print("Setting permissions and formatting ext4 image via podman unshare...")
    cmd = f"""
    chown -R 0:0 {ROOTFS_DIR}
    chown -R 1000:1000 {ROOTFS_DIR}/home/myelinos
    chown -R 1000:1000 {ROOTFS_DIR}/run/user/1000 2>/dev/null || true
    chown -R 42:42 {ROOTFS_DIR}/var/lib/gdm 2>/dev/null || true
    chown -R 42:42 {ROOTFS_DIR}/run/user/42 2>/dev/null || true
    chown -R 81:81 {ROOTFS_DIR}/run/dbus 2>/dev/null || true
    chown -R 974:974 {ROOTFS_DIR}/var/lib/colord 2>/dev/null || true
    chown -R 976:976 {ROOTFS_DIR}/var/lib/geoclue 2>/dev/null || true
    chown -R 975:975 {ROOTFS_DIR}/var/lib/malcontent-timerd 2>/dev/null || true
    rm -rf {ROOTFS_DIR}/tmp/* {ROOTFS_DIR}/tmp/.* 2>/dev/null || true
    rm -rf {ROOTFS_DIR}/var/tmp/* {ROOTFS_DIR}/var/tmp/.* 2>/dev/null || true
    mkdir -p {ROOTFS_DIR}/tmp/.X11-unix {ROOTFS_DIR}/var/tmp
    chmod 1777 {ROOTFS_DIR}/tmp {ROOTFS_DIR}/tmp/.X11-unix {ROOTFS_DIR}/var/tmp
    chmod 700 {ROOTFS_DIR}/run/user/0 2>/dev/null || true
    chmod 700 {ROOTFS_DIR}/run/user/1000 2>/dev/null || true
    chmod 700 {ROOTFS_DIR}/run/user/42 2>/dev/null || true
    chmod 755 {ROOTFS_DIR}/home/myelinos
    chmod 4755 {ROOTFS_DIR}/usr/bin/mount
    chmod 4755 {ROOTFS_DIR}/usr/bin/umount
    chmod 4755 {ROOTFS_DIR}/usr/bin/su
    chmod 4755 {ROOTFS_DIR}/usr/bin/sudo
    chmod 4755 {ROOTFS_DIR}/usr/bin/passwd
    chmod 4755 {ROOTFS_DIR}/usr/bin/unix_chkpwd 2>/dev/null || true
    chmod 4755 {ROOTFS_DIR}/usr/sbin/unix_chkpwd 2>/dev/null || true
    chmod 4755 {ROOTFS_DIR}/usr/bin/ping
    chmod 4755 {ROOTFS_DIR}/usr/bin/pkexec 2>/dev/null || true
    chmod 4755 {ROOTFS_DIR}/usr/lib/polkit-1/polkit-agent-helper-1 2>/dev/null || true
    chmod 4755 {ROOTFS_DIR}/usr/bin/Xwayland 2>/dev/null || true
    chmod 0440 {ROOTFS_DIR}/etc/sudoers
    chmod 0750 {ROOTFS_DIR}/etc/sudoers.d
    chmod 0700 {ROOTFS_DIR}/var/db/sudo 2>/dev/null || true
    chmod 0711 {ROOTFS_DIR}/run/sudo 2>/dev/null || true
    chmod 0700 {ROOTFS_DIR}/etc/polkit-1/rules.d 2>/dev/null || true
    chmod 0700 {ROOTFS_DIR}/usr/share/polkit-1/rules.d 2>/dev/null || true
    chmod 0644 {ROOTFS_DIR}/etc/polkit-1/rules.d/* 2>/dev/null || true
    chmod -R 0755 {ROOTFS_DIR}/usr/share/polkit-1/actions 2>/dev/null || true
    chown -R 114:114 {ROOTFS_DIR}/etc/polkit-1/rules.d 2>/dev/null || true
    chown -R 114:114 {ROOTFS_DIR}/usr/share/polkit-1/rules.d 2>/dev/null || true
    chmod 600 {ROOTFS_DIR}/etc/shadow
    chmod 600 {ROOTFS_DIR}/etc/ssh/*_key 2>/dev/null || true
    chmod 644 {ROOTFS_DIR}/etc/passwd {ROOTFS_DIR}/etc/group
    chmod 664 {ROOTFS_DIR}/var/run/utmp {ROOTFS_DIR}/var/log/wtmp {ROOTFS_DIR}/var/log/lastlog
    mke2fs -t ext4 -d {ROOTFS_DIR} -L MYELINOS_ROOT -m 0 -F {ROOTFS_IMG} 5500M
    """
    subprocess.check_call(["podman", "unshare", "sh", "-c", cmd])
    print(f"Successfully generated bootable rootfs image: {ROOTFS_IMG}")

def install_myelin_subsystem(root: Path):
    """Build and install Axon package manager (axon / ax) and directories (§5.4, §13, §14)."""
    print("Building and installing Axon package manager (axon)...")
    axon_bin = BASE_DIR / "target" / "release" / "axon"
    if not axon_bin.exists():
        subprocess.check_call(["cargo", "build", "--release", "--bin", "axon"], cwd=str(BASE_DIR))
    dest = root / "usr" / "bin" / "axon"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(axon_bin, dest)
    os.chmod(dest, 0o755)

    # Short alias `ax` and backward compatibility alias `myelin-pkg`
    for alias in ["ax", "myelin-pkg"]:
        alias_path = root / "usr" / "bin" / alias
        if alias_path.exists() or alias_path.is_symlink():
            alias_path.unlink()
        alias_path.symlink_to("axon")

    # Canonical Myelin storage directories
    for d in ["store", "profiles", "generations"]:
        (root / "var" / "lib" / "myelin" / d).mkdir(parents=True, exist_ok=True)
    print("Axon package manager and subsystem installed successfully.")

def main():
    print("=== MyelinOS LFS Bootstrap: Display Server & GNOME 50 Desktop ===")
    print(f"Target Rootfs Directory: {ROOTFS_DIR}")
    print(f"Target Image:            {ROOTFS_IMG}")
    print(f"Target Kernel:           {KERNEL_DEST}")
    
    create_directory_hierarchy(ROOTFS_DIR)
    extract_sudo_packages(ROOTFS_DIR)
    extract_desktop_packages(ROOTFS_DIR)
    extract_polkit_packages(ROOTFS_DIR)
    install_graphics_and_desktop_assets(ROOTFS_DIR)
    install_binaries_and_libs(ROOTFS_DIR)
    install_myelin_subsystem(ROOTFS_DIR)
    install_systemd_units(ROOTFS_DIR)
    install_configuration_files(ROOTFS_DIR)
    build_disk_image()
    print("=== MyelinOS LFS Bootstrap Complete ===")

if __name__ == "__main__":
    main()
