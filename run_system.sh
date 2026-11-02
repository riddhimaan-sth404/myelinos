#!/usr/bin/env bash
# ==============================================================================
# MyelinOS System Runner (run_system.sh)
# Launches the full installed MyelinOS operating system in QEMU.
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}"

KERNEL="${ROOT_DIR}/build/images/vmlinuz"
ROOTFS="${ROOT_DIR}/build/images/myelinos-rootfs.ext4"
UEFI_DISK="${ROOT_DIR}/build/images/myelinos-uefi.img"
LIVE_ISO="${ROOT_DIR}/build/images/myelinos-live.iso"

# Default configuration
BOOT_MODE="uefi"          # uefi | direct | iso
MEMORY="${QEMU_MEM:-4096M}"
SMP="${QEMU_SMP:-2}"
VNC_PORT="${QEMU_VNC:-:1}"
SSH_PORT="${QEMU_SSH_PORT:-2222}"
ENABLE_GUI=false
ENABLE_GL=false

find_ovmf() {
    for f in \
        "/usr/share/OVMF/OVMF_CODE.fd" \
        "/usr/share/edk2/ovmf/OVMF_CODE.fd" \
        "/usr/share/edk2/ovmf/OVMF.stateless.fd"; do
        if [[ -f "$f" ]]; then
            echo "$f"
            return 0
        fi
    done
    return 1
}

usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

MyelinOS System Runner - Boots the installed MyelinOS environment.

Options:
  -u, --uefi            Boot UEFI GPT hard disk image (Default: myelinos-uefi.img)
  -t, --target          Boot the target disk installed by the installer (target-disk.raw)
      --disk <path>     Boot custom UEFI hard disk image
  -d, --direct          Boot kernel directly into ext4 rootfs (vmlinuz + myelinos-rootfs.ext4)
  -i, --iso             Boot MyelinOS Live ISO image (myelinos-live.iso)
  -g, --gui             Open graphical window on desktop (GTK backend)
      --gl              Enable VirtIO 3D GPU acceleration (virtio-vga-gl with GTK gl=on)
      --vnc <display>   Set VNC display offset (default: :1 -> localhost:5901)
  -m, --mem <size>      Memory allocation (default: 4096M)
  -c, --smp <cores>     CPU core count (default: 2)
  -p, --ssh-port <port> Host port to forward SSH to (default: 2222)
      --rebuild         Rebuild disk image before launching
  -h, --help            Show this help message

Environment Variables:
  QEMU_MEM              Memory allocation (e.g. 4096M)
  QEMU_SMP              CPU cores (e.g. 2)
  QEMU_VNC              VNC display (e.g. :1)
  QEMU_SSH_PORT         SSH forward port (e.g. 2222)

To exit the VM:
  - In serial console: Type 'poweroff' or press 'Ctrl-a' then 'x'
  - From graphical window: Close window or select Power Off in GNOME
EOF
}

# Parse command line flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        -u|--uefi)
            BOOT_MODE="uefi"
            shift
            ;;
        -t|--target)
            BOOT_MODE="uefi"
            UEFI_DISK="${ROOT_DIR}/build/images/target-disk.raw"
            shift
            ;;
        --disk)
            BOOT_MODE="uefi"
            UEFI_DISK="$2"
            shift 2
            ;;
        -d|--direct)
            BOOT_MODE="direct"
            shift
            ;;
        -i|--iso)
            BOOT_MODE="iso"
            shift
            ;;
        -g|--gui)
            ENABLE_GUI=true
            shift
            ;;
        --no-gui|--headless)
            ENABLE_GUI=false
            shift
            ;;
        --gl)
            ENABLE_GL=true
            ENABLE_GUI=true
            shift
            ;;
        --vnc)
            VNC_PORT="$2"
            shift 2
            ;;
        -m|--mem)
            MEMORY="$2"
            shift 2
            ;;
        -c|--smp)
            SMP="$2"
            shift 2
            ;;
        -p|--ssh-port)
            SSH_PORT="$2"
            shift 2
            ;;
        --rebuild)
            echo "[*] Rebuilding UEFI disk and rootfs images..."
            python3 "${ROOT_DIR}/build/bootstrap/bootstrap.py"
            python3 "${ROOT_DIR}/tools/build_uefi_disk.py"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "[-] Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Ensure images exist
ensure_images() {
    if [[ "${BOOT_MODE}" == "uefi" ]]; then
        if [[ ! -f "${UEFI_DISK}" ]]; then
            echo "[*] UEFI disk image missing (${UEFI_DISK}). Building now..."
            python3 "${ROOT_DIR}/tools/build_uefi_disk.py"
        fi
    elif [[ "${BOOT_MODE}" == "direct" ]]; then
        if [[ ! -f "${KERNEL}" || ! -f "${ROOTFS}" ]]; then
            echo "[*] Rootfs image missing. Running bootstrap now..."
            python3 "${ROOT_DIR}/build/bootstrap/bootstrap.py"
        fi
    elif [[ "${BOOT_MODE}" == "iso" ]]; then
        if [[ ! -f "${LIVE_ISO}" ]]; then
            echo "[*] Live ISO missing. Building now..."
            python3 "${ROOT_DIR}/tools/build_iso.py"
        fi
    fi
}

ensure_images

# Hardware acceleration
KVM_ARG=""
if [[ -r /dev/kvm && -w /dev/kvm ]]; then
    KVM_ARG="-enable-kvm"
fi

# Configure display & GPU
if [[ "${ENABLE_GUI}" == "true" ]]; then
    if [[ "${ENABLE_GL}" == "true" ]]; then
        GPU_DEVICE="virtio-vga-gl"
        DISPLAY_OPTS=("-display" "gtk,gl=on,zoom-to-fit=on,show-cursor=on")
    else
        GPU_DEVICE="virtio-vga"
        DISPLAY_OPTS=("-display" "gtk,zoom-to-fit=on,show-cursor=on" "-vnc" "${VNC_PORT}")
    fi
else
    GPU_DEVICE="virtio-vga"
    DISPLAY_OPTS=("-display" "none" "-vnc" "${VNC_PORT}")
fi

# Auto-spawn vncviewer if desktop display is available and not in GUI window mode
auto_vnc() {
    if [[ "${ENABLE_GUI}" != "true" && -n "${DISPLAY:-${WAYLAND_DISPLAY}}" ]] && command -v vncviewer >/dev/null 2>&1; then
        local target_port="5901"
        if [[ "${VNC_PORT}" =~ ^:([0-9]+)$ ]]; then
            target_port=$((5900 + BASH_REMATCH[1]))
        fi
        (
            for _ in {1..60}; do
                if ss -tln 2>/dev/null | grep -q ":${target_port}\b"; then
                    vncviewer "localhost:${target_port}" >/dev/null 2>&1 &
                    break
                fi
                sleep 0.2
            done
        ) &
    fi
}

echo "=========================================================="
echo " ◈ Starting MyelinOS Full Operating System in QEMU"
echo " - Boot Target:    ${BOOT_MODE^^}"
echo " - Memory / SMP:   ${MEMORY} / ${SMP} Cores (KVM: $([ -n "$KVM_ARG" ] && echo 'Enabled' || echo 'Disabled'))"
echo " - Serial Console: Auto-login interactive root shell on stdio"
echo " - GNOME 50 GUI:   VirtIO GPU (VNC display localhost:5901)"
echo " - SSH Service:    Forwarded to host localhost:${SSH_PORT} ('ssh -p ${SSH_PORT} root@localhost')"
echo " To exit: type 'poweroff' or press 'Ctrl-a' then 'x'"
echo "=========================================================="

auto_vnc

COMMON_ARGS=(
    ${KVM_ARG}
    -m "${MEMORY}"
    -smp "${SMP}"
    -netdev "user,id=net0,hostfwd=tcp::${SSH_PORT}-:22"
    -device virtio-net-pci,netdev=net0
    -device "${GPU_DEVICE}"
    -device virtio-tablet-pci
    -device intel-hda -device hda-duplex
    -serial mon:stdio
    -qmp "unix:/tmp/qmp-system.sock,server,nowait"
    "${DISPLAY_OPTS[@]}"
)

if [[ "${BOOT_MODE}" == "uefi" ]]; then
    OVMF=$(find_ovmf) || { echo "[-] Error: OVMF UEFI firmware not found on host!"; exit 1; }
    exec qemu-system-x86_64 \
        "${COMMON_ARGS[@]}" \
        -bios "${OVMF}" \
        -drive "file=${UEFI_DISK},format=raw,if=virtio"

elif [[ "${BOOT_MODE}" == "direct" ]]; then
    exec qemu-system-x86_64 \
        "${COMMON_ARGS[@]}" \
        -kernel "${KERNEL}" \
        -drive "file=${ROOTFS},format=raw,if=virtio" \
        -append "root=/dev/vda rw console=ttyS0 init=/usr/lib/systemd/systemd audit=0 selinux=0 enforcing=0 quiet"

elif [[ "${BOOT_MODE}" == "iso" ]]; then
    OVMF=$(find_ovmf) || true
    EFI_ARG=()
    if [[ -n "${OVMF}" ]]; then
        EFI_ARG=("-bios" "${OVMF}")
    fi
    exec qemu-system-x86_64 \
        "${COMMON_ARGS[@]}" \
        "${EFI_ARG[@]}" \
        -cdrom "${LIVE_ISO}" \
        -boot d
fi
