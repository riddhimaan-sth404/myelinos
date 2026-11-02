#!/usr/bin/env bash
# ==============================================================================
# MyelinOS Bootstrap Installer Runner (run_installer.sh)
# Launches the Stage 1 TUI Bootstrap Installer in QEMU with a target virtual disk.
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}"

BOOTSTRAP_ISO="${ROOT_DIR}/build/images/myelinos-bootstrap.iso"
BOOTSTRAP_INITRD="${ROOT_DIR}/build/bootstrap_iso_staging/boot/initrd.img"
KERNEL="${ROOT_DIR}/build/images/vmlinuz"
TARGET_DISK="${ROOT_DIR}/build/images/target-disk.raw"
TARGET_DISK_SIZE_GB="20"

# Default configuration (4 GB RAM allocated per user mandate)
BOOT_MODE="uefi"          # uefi | direct
MEMORY="${QEMU_MEM:-4096M}"
SMP="${QEMU_SMP:-2}"
VNC_PORT="${QEMU_VNC:-:1}"

# Auto-enable graphical window by default if host display is available
if [[ -n "${DISPLAY:-${WAYLAND_DISPLAY}}" ]]; then
    ENABLE_GUI=true
else
    ENABLE_GUI=false
fi

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

MyelinOS Bootstrap Installer Runner - Tests the Stage 1 TUI installation workflow.

Options:
  -u, --uefi                Boot installer via UEFI firmware (Default)
  -d, --direct              Boot installer directly via kernel + initrd
  -t, --target-disk <path>  Path to target hard disk image (Default: build/images/target-disk.raw)
  -s, --disk-size <gb>      Size of target disk in GB if auto-created (Default: 20)
      --reset-disk          Wipe and re-create blank target disk before launch
  -g, --gui                 Open graphical window on desktop (Default when desktop session active)
      --no-gui, --headless  Disable graphical window (serial console only)
      --vnc <display>       Set VNC display offset (default: :1 -> localhost:5901)
  -m, --mem <size>          Memory allocation (default: 4096M / 4 GB)
  -c, --smp <cores>         CPU core count (default: 2)
      --rebuild             Recompile axon-bootstrap and rebuild bootstrap ISO
  -h, --help                Show this help message

Interactive Controls in TUI Installer:
  - [Enter]:       Advance to next step / Confirm drive / Start staging
  - [Up / Down]:   Navigate drive list and profile selection
  - [Esc] or [b]:  Go back to previous step
  - [q]:           Quit installer and drop to shell

Dual-Display:
  - Terminal:      Interactive Rust Ratatui TUI attached to stdio
  - Graphical:     QEMU GTK display window with VirtIO GPU & VGA console
  - VNC Server:    Available on localhost:5901

To exit QEMU:
  - Press 'Ctrl-a' then 'x' or type 'poweroff' in shell
EOF
}

AUTO_MODE=false
RESET_DISK=false

# Parse command line flags
while [[ $# -gt 0 ]]; do
    case "$1" in
        -u|--uefi)
            BOOT_MODE="uefi"
            shift
            ;;
        -a|--auto)
            AUTO_MODE=true
            BOOT_MODE="direct"
            shift
            ;;
        -d|--direct)
            BOOT_MODE="direct"
            shift
            ;;
        -t|--target-disk)
            TARGET_DISK="$2"
            shift 2
            ;;
        -s|--disk-size)
            TARGET_DISK_SIZE_GB="$2"
            shift 2
            ;;
        --reset-disk)
            RESET_DISK=true
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
        --rebuild)
            echo "[*] Rebuilding axon-bootstrap binary and bootstrap ISO..."
            python3 "${ROOT_DIR}/tools/build_bootstrap_iso.py"
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

# Ensure bootstrap installer media exists
ensure_bootstrap_media() {
    if [[ ! -f "${BOOTSTRAP_ISO}" || ! -f "${BOOTSTRAP_INITRD}" ]]; then
        echo "[*] Bootstrap installer media missing. Building now..."
        python3 "${ROOT_DIR}/tools/build_bootstrap_iso.py"
    fi
}

ensure_bootstrap_media

# Ensure target virtual disk exists
ensure_target_disk() {
    mkdir -p "$(dirname "${TARGET_DISK}")"
    if [[ "${RESET_DISK}" == "true" && -f "${TARGET_DISK}" ]]; then
        echo "[*] Resetting target installation disk: ${TARGET_DISK}"
        rm -f "${TARGET_DISK}"
    fi

    if [[ ! -f "${TARGET_DISK}" ]]; then
        echo "[*] Creating sparse target virtual disk (${TARGET_DISK_SIZE_GB} GB): ${TARGET_DISK}..."
        truncate -s "${TARGET_DISK_SIZE_GB}G" "${TARGET_DISK}"
        echo "[+] Target drive ready for fresh GPT partitioning."
    fi
}

ensure_target_disk

# Hardware acceleration
KVM_ARG=""
if [[ -r /dev/kvm && -w /dev/kvm ]]; then
    KVM_ARG="-enable-kvm"
fi

# Configure display & GPU
if [[ "${ENABLE_GUI}" == "true" ]]; then
    DISPLAY_OPTS=("-display" "gtk,zoom-to-fit=on,show-cursor=on" "-vnc" "${VNC_PORT}")
else
    DISPLAY_OPTS=("-display" "none" "-vnc" "${VNC_PORT}")
fi

echo "=========================================================="
echo " ◈ Starting MyelinOS Bootstrap Installer (Stage 1 TUI) in QEMU"
echo " - Boot Medium:    ${BOOTSTRAP_ISO} (~50 MB ISO)"
echo " - Target Drive:   ${TARGET_DISK} (${TARGET_DISK_SIZE_GB} GB raw virtual disk -> /dev/vda)"
echo " - Mode / Memory:  ${BOOT_MODE^^} / ${MEMORY} (4 GB RAM allocated)"
echo " - KVM Engine:     $([ -n "$KVM_ARG" ] && echo 'Enabled (Hardware Acceleration)' || echo 'Disabled')"
echo " - Graphical GUI:  $([ "$ENABLE_GUI" = "true" ] && echo 'Enabled (QEMU GTK Window + VNC :1)' || echo 'Disabled (Headless)')"
echo " - Terminal TUI:   Rust Ratatui TUI attached directly to stdio"
echo " To exit: press 'Ctrl-a' then 'x' or type 'poweroff'"
echo "=========================================================="

PAYLOAD_IMG="${ROOT_DIR}/build/images/myelinos-rootfs.ext4"
PAYLOAD_ARG=()
if [[ -f "${PAYLOAD_IMG}" ]]; then
    PAYLOAD_ARG=("-drive" "file=${PAYLOAD_IMG},format=raw,if=virtio,readonly=on")
fi

COMMON_ARGS=(
    ${KVM_ARG}
    -m "${MEMORY}"
    -smp "${SMP}"
    -drive "file=${TARGET_DISK},format=raw,if=virtio"
    "${PAYLOAD_ARG[@]}"
    -device virtio-net-pci
    -device virtio-vga
    -device virtio-tablet-pci
    -device intel-hda -device hda-duplex
    -serial mon:stdio
    -qmp "unix:/tmp/qmp-installer.sock,server,nowait"
    "${DISPLAY_OPTS[@]}"
)

if [[ "${BOOT_MODE}" == "uefi" ]]; then
    OVMF=$(find_ovmf) || { echo "[-] Warning: OVMF not found, falling back to direct boot"; BOOT_MODE="direct"; }
fi

if [[ "${BOOT_MODE}" == "uefi" ]]; then
    if [[ "${AUTO_MODE}" == "true" ]]; then
        CONSOLE_APPEND="${CONSOLE_APPEND} myelin.auto=1"
    fi
    exec qemu-system-x86_64 \
        "${COMMON_ARGS[@]}" \
        -bios "${OVMF}" \
        -cdrom "${BOOTSTRAP_ISO}" \
        -boot d
else
    if [[ "${ENABLE_GUI}" == "true" ]]; then
        CONSOLE_APPEND="console=ttyS0 console=tty0 quiet"
    else
        CONSOLE_APPEND="console=tty0 console=ttyS0 quiet"
    fi
    if [[ "${AUTO_MODE}" == "true" ]]; then
        CONSOLE_APPEND="${CONSOLE_APPEND} myelin.auto=1"
    fi
    exec qemu-system-x86_64 \
        "${COMMON_ARGS[@]}" \
        -kernel "${KERNEL}" \
        -initrd "${BOOTSTRAP_INITRD}" \
        -append "${CONSOLE_APPEND}"
fi
