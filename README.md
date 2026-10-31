# MyelinOS — Linux Distribution (LFS + systemd + Display Server + COSMIC Desktop)

A complete, bootable Linux distribution bootstrapped following the **Linux From Scratch (LFS) systemd** standard, featuring a **modern Display Server architecture** and the **System76 COSMIC Desktop Environment**.

MyelinOS combines the reliability and transparency of an LFS system with `systemd` v259 as PID 1, the Wayland compositor `cosmic-comp`, X11 compatibility via `Xwayland`, Mesa DRM/KMS VirtIO graphics acceleration, D-Bus session and system message bus, and the full COSMIC Desktop suite.

---

## Architecture & Subsystems

```
+--------------------------------------------------------------------------+
|                        MyelinOS Desktop System                           |
+--------------------------------------------------------------------------+
|  Applications & Tools:                                                   |
|    * COSMIC Terminal (cosmic-term), COSMIC Files (cosmic-files)          |
|    * COSMIC App Library, Launcher, Settings, Applets, Workspaces        |
|    * Python 3.14 Runtime & Full Standard Library                         |
|    * Full GNU Coreutils, Procps-ng, Util-Linux, OpenSSH, Nano, Vi        |
+--------------------------------------------------------------------------+
|  Display Server & Compositor Layer:                                      |
|    * Wayland Display Server: cosmic-comp (Smithay / wgpu / Rust)         |
|    * X11 Display Server:     Xwayland (seamless X11 compatibility)       |
|    * Session Manager:        start-cosmic / cosmic-session               |
|    * Diagnostics:            wayland-info, xrandr, glxinfo, xauth, xrdb  |
+--------------------------------------------------------------------------+
|  Graphics & Acceleration Stack:                                          |
|    * Mesa 26.2 (Gallium, GBM, EGL, GL, GLESv2)                           |
|    * DRI Drivers: virtio_gpu_dri.so, kms_swrast_dri.so, swrast_dri.so    |
|    * Vulkan ICDs: virtio_icd (virtio-gpu) & lvp_icd (CPU lavapipe)       |
|    * Input & Seat: libseat, libinput, libxkbcommon, xkeyboard-config     |
+--------------------------------------------------------------------------+
|  System & Service Infrastructure:                                        |
|    * Init System: systemd v259 (PID 1, multi-user / graphical targets)  |
|    * Message Bus: D-Bus (dbus-daemon.service, dbus.socket)               |
|    * Seat / Session: systemd-logind.service, pam_systemd.so              |
|    * Networking: systemd-networkd (DHCP), systemd-resolved, OpenSSH      |
|    * Kernel: Linux 7.2.11 with virtio-gpu, virtio-net, virtio-blk        |
+--------------------------------------------------------------------------+
```

---

## Included Subsystems & Command Coverage

### 1. Display Server & Graphics
- **Wayland Compositor / Display Server**: `cosmic-comp` (v1.0.0, built on Smithay). Supports direct DRM/KMS scanout, GBM allocation, software fallbacks, and multi-output management.
- **X11 Display Server**: `Xwayland` (v24.1.14), managed transparently by `cosmic-comp` on `DISPLAY=:0`.
- **Display & Graphics Diagnostics**:
  - `wayland-info`: Inspects active Wayland protocols and compositor interfaces.
  - `xrandr`: Manages screen resolutions, refresh rates, and virtual outputs.
  - `glxinfo`: Queries OpenGL / GLX context, renderer, and visual properties.
  - `xauth`, `xhost`, `xrdb`: Manages X11 authentication, access control, and resources.
- **Mesa & DRM Stack**:
  - DRI drivers: `virtio_gpu_dri.so`, `kms_swrast_dri.so`, `swrast_dri.so`, `libdril_dri.so`.
  - Vulkan drivers: `libvulkan_virtio.so` (VirtIO GPU) and `libvulkan_lvp.so` (CPU Lavapipe).
  - Acceleration libraries: `libgallium`, `libgbm`, `libEGL`, `libGL`, `libGLESv2`, `libdrm`.
  - Seat & Input: `libseat`, `libinput`, `libxkbcommon`, `libevdev`, `libwacom`.
  - Keyboard definitions: `/usr/share/X11/xkb` (via `xkeyboard-config-2`).

### 2. COSMIC Desktop Environment Suite
- **Session Orchestration**:
  - `start-cosmic`: High-level session initialization script setting up XDG environment, D-Bus session bus, and launch flags.
  - `cosmic-session`: Desktop lifecycle manager coordinating compositor, background daemons, and client applications.
- **Core Desktop Components**:
  - `cosmic-panel`: Top/bottom panel and dock.
  - `cosmic-applets`: Status applets (workspaces, clock, audio, network, notifications, battery, power, tiling).
  - `cosmic-app-library`: Full-screen categorized application grid.
  - `cosmic-launcher`: Fast application, command, and calculation launcher.
  - `cosmic-workspaces`: Workspace overview and window switcher.
  - `cosmic-bg`: Wallpaper and background renderer.
  - `cosmic-notifications`: Desktop notification daemon.
  - `cosmic-osd`: On-screen display for volume and display brightness.
  - `cosmic-idle`: User idle state notification manager.
  - `cosmic-randr`: Display configuration utility.
  - `cosmic-screenshot`: Screen capture utility.
- **COSMIC Applications**:
  - `cosmic-term`: High-performance terminal emulator built with Alacritty and Libcosmic.
  - `cosmic-files`: Libcosmic file manager with thumbnailer daemon.
  - `cosmic-settings` & `cosmic-settings-daemon`: System and appearance configuration.
- **Desktop Assets & Theming**:
  - Default shortcut and window tiling configs in `/usr/share/cosmic/`.
  - Official COSMIC icon theme in `/usr/share/icons/cosmic/`.
  - COSMIC official wallpapers in `/usr/share/backgrounds/cosmic/`.
  - Wayland desktop session definition in `/usr/share/wayland-sessions/cosmic.desktop`.
  - Application desktop entries in `/usr/share/applications/`.

### 3. Init System & Process Management (systemd)
- **PID 1**: `systemd` v259 running in system mode, achieving targets in ~1.5s cold boot.
- **Active System Services**:
  - `systemd-journald` (logging & journal management)
  - `systemd-udevd` (kernel device events, DRM nodes, input devices)
  - `dbus.service` & `dbus.socket` (D-Bus system message bus)
  - `systemd-logind` (user session, seat, and VT manager)
  - `systemd-networkd` (DHCP network interface configuration)
  - `systemd-resolved` (DNS resolution & caching)
  - `systemd-timesyncd` (NTP clock synchronization)
  - `sshd.service` (OpenSSH server daemon)
  - `serial-getty@ttyS0.service` (instant auto-login console on `/dev/ttyS0`)
  - `cosmic.service` (COSMIC Desktop service on VT1)
- **Control Tools**:
  `systemctl`, `journalctl`, `udevadm`, `loginctl`, `timedatectl`, `localectl`, `hostnamectl`, `bootctl`, `busctl`, `resolvectl`, `networkctl`, `poweroff`, `reboot`.

### 4. D-Bus & Seat Management
- **D-Bus System Bus**: `dbus-daemon --system` listening on `/run/dbus/system_bus_socket`.
- **D-Bus Session Bus**: `dbus-run-session` automatically provisioned per graphical session.
- **CLI Tools**: `dbus-send`, `dbus-monitor`, `busctl`.
- **Logind Integration**: `systemd-logind` managing graphical seats (`seat0`), VT switching, and DRM master delegation.
- **Users**: System user `dbus` (UID 81) and standard desktop user `cosmic` (UID 1000).

### 5. Standard CLI & Development Environment
- **Shells**: `bash` (with custom `/etc/profile` and `/root/.bashrc`), `sh`.
- **Full GNU Coreutils**: Complete suite of 100+ utilities (`cat`, `cp`, `mv`, `rm`, `mkdir`, `touch`, `chmod`, `chown`, `dd`, `stat`, `truncate`, `grep`, `sed`, `awk`, `find`, `xargs`, `sort`, `uniq`, `wc`, `diff`, `patch`, `sha256sum`, etc.).
- **Process Monitoring**: `ps`, `top`, `free`, `vmstat`, `pkill`, `pgrep`, `pidof`, `kill`, `watch`.
- **Storage & Disk Administration**: `mount`, `umount`, `findmnt`, `lsblk`, `blkid`, `fdisk`, `cfdisk`, `mke2fs`, `mkfs.ext4`, `e2fsck`, `tune2fs`, `resize2fs`.
- **Archiving & Compression**: `tar`, `gzip`, `bzip2`, `xz`, `zstd`.
- **Editors & Pagers**: `nano` (syntax highlighting in `/usr/share/nano`), `vi` (with `/usr/share/vim`), `less`, `more`.
- **Fonts & Fontconfig**: Complete `/etc/fonts/fonts.conf` database, `fc-cache`, `fc-list`, and system fonts (Noto, Liberation, DejaVu).
- **Networking**: `ip` (`iproute2`), `ss`, `ping`, `curl`, `wget`, OpenSSH suite (`ssh`, `sshd`, `scp`, `sftp`).
- **Python 3 Runtime**: Python 3.14 with complete standard library in `/usr/lib64/python3.14`.

---

## Quick Start & Verification

### Prerequisites
- Linux host with QEMU (`qemu-system-x86_64`) and `podman` installed.
- KVM acceleration enabled (`/dev/kvm`).

### Build the Image
```bash
make build
# or: python3 build/bootstrap/bootstrap.py
```
This downloads packages (if not cached), extracts the rootfs, resolves all shared libraries, configures systemd, and formats the bootable 3.5 GB ext4 image (`build/images/myelinos-rootfs.ext4`).

### Run the Automated Test Suite
```bash
make test
# or: python3 tools/test_boot.py
```
Validates cold boot, PID 1 systemd, D-Bus, logind, DRM virtio-gpu detection, `cosmic-comp`, `Xwayland`, COSMIC binaries, Python 3 runtime, network ping, SSH server, and ACPI shutdown.

### Run Interactive Session
```bash
make run
# or: ./tools/run_qemu.sh --interactive
```
- **Serial Console**: Automatic root shell on terminal stdio.
- **COSMIC Desktop Display**: Rendered via VirtIO GPU on VNC display `localhost:5901` (`:1`). Connect using any VNC viewer (e.g. `vncviewer localhost:5901`).
- **SSH Access**: Forwarded to host port 2222 (`ssh -p 2222 root@localhost`).

---

## Project Structure

```
MyelinOS/
├── build/
│   ├── bootstrap/
│   │   ├── bootstrap.py            # Complete rootfs generator and image builder
│   │   └── rootfs/                 # Staged rootfs directory
│   ├── images/
│   │   ├── myelinos-rootfs.ext4    # 3.5GB sparse bootable ext4 disk image
│   │   └── vmlinuz                 # Linux 7.2 x86_64 kernel binary
│   └── packages/
│       └── cosmic/                 # Cached COSMIC RPM packages
├── tools/
│   ├── run_qemu.sh                 # QEMU launcher (serial console + VNC GPU)
│   └── test_boot.py                # Automated end-to-end verification suite
├── Makefile                        # Top-level build, run, test targets
└── README.md                       # Distribution documentation
```
