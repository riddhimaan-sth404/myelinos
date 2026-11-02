#!/usr/bin/env bash
# MyelinOS QEMU Runner Script
# Launches MyelinOS with systemd, VirtIO GPU, OpenSSH, and GNOME 50 Desktop Environment
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

KERNEL="${ROOT_DIR}/build/images/vmlinuz"
ROOTFS="${ROOT_DIR}/build/images/myelinos-rootfs.ext4"
ISO_IMAGE="${ROOT_DIR}/build/images/myelinos-live.iso"
UEFI_DISK="${ROOT_DIR}/build/images/myelinos-uefi.img"
MEMORY="${QEMU_MEM:-4096M}"
SMP="${QEMU_SMP:-2}"
VNC_PORT="${QEMU_VNC:-:1}"
if [[ -z "${QEMU_DISPLAY}" ]]; then
    if [[ -n "${DISPLAY}" || -n "${WAYLAND_DISPLAY}" ]]; then
        DISPLAY_BACKEND="gtk"
    else
        DISPLAY_BACKEND="none"
    fi
else
    DISPLAY_BACKEND="${QEMU_DISPLAY}"
fi
USE_EFI=false

find_ovmf() {
    for f in "/usr/share/OVMF/OVMF_CODE.fd" "/usr/share/edk2/ovmf/OVMF_CODE.fd" "/usr/share/edk2/ovmf/OVMF.stateless.fd"; do
        if [[ -f "$f" ]]; then
            echo "$f"
            return 0
        fi
    done
    return 1
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --interactive       Launch interactive QEMU session on serial console (default)"
    echo "  --efi               Boot in UEFI environment with OVMF firmware (supports disk & ISO)"
    echo "  --uefi-disk         Boot the UEFI GPT disk image (myelinos-uefi.img)"
    echo "  --iso               Launch interactive Live ISO session in QEMU"
    echo "  --iso-test          Run automated Live ISO verification test suite"
    echo "  --uefi-test         Run automated UEFI GPT disk verification test suite"
    echo "  --gui               Launch QEMU with a graphical window (GTK/SDL if host displays available)"
    echo "  --gl                Enable hardware OpenGL 3D acceleration via virtio-vga-gl (GTK gl=on)"
    echo "  --test              Run automated verification test suite on disk image"
    echo "  --build             Rebuild rootfs image before running"
    echo "  --build-iso         Rebuild Live ISO before running"
    echo "  --build-uefi        Rebuild UEFI GPT disk image before running"
    echo "  -h, --help          Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  QEMU_MEM            Memory size (default: 4096M)"
    echo "  QEMU_SMP            Number of CPU cores (default: 2)"
    echo "  QEMU_VNC            VNC display offset (default: :1 -> localhost:5901)"
    echo "  QEMU_DISPLAY        Display backend (default: none)"
    echo ""
    echo "Desktop Environment & Remote Access:"
    echo "  - Serial Console:   Interactive terminal attached directly to stdio"
    echo "  - GNOME 50 Desktop: Rendered via VirtIO GPU on VNC display localhost:5901"
    echo "  - SSH Server:       Forwarded to host port 2222 ('ssh -p 2222 root@localhost')"
    echo ""
    echo "To exit interactive QEMU: press 'Ctrl-a x' or run 'poweroff' inside the shell."
}

# Auto-build if images don't exist
ensure_images() {
    if [[ ! -f "${KERNEL}" || ! -f "${ROOTFS}" ]]; then
        echo "[*] Disk image missing. Running bootstrap first..."
        python3 "${ROOT_DIR}/build/bootstrap/bootstrap.py"
    fi
}

ensure_iso() {
    if [[ ! -f "${ISO_IMAGE}" ]]; then
        echo "[*] Live ISO missing. Running build_iso.py first..."
        python3 "${ROOT_DIR}/tools/build_iso.py"
    fi
}

ensure_uefi_disk() {
    if [[ ! -f "${UEFI_DISK}" ]]; then
        echo "[*] UEFI disk image missing. Running build_uefi_disk.py first..."
        python3 "${ROOT_DIR}/tools/build_uefi_disk.py"
    fi
}

auto_launch_vncviewer() {
    local target_port="5901"
    if [[ "${VNC_PORT}" =~ ^:([0-9]+)$ ]]; then
        target_port=$((5900 + BASH_REMATCH[1]))
    fi
    if command -v vncviewer >/dev/null 2>&1 && [[ -n "${DISPLAY:-${WAYLAND_DISPLAY}}" ]]; then
        (
            for i in {1..80}; do
                if ss -tln 2>/dev/null | grep -q ":${target_port}\b"; then
                    sleep 0.5
                    echo "[*] VNC server active on port ${target_port}. Launching vncviewer..."
                    vncviewer "localhost:${target_port}" >/dev/null 2>&1 &
                    break
                fi
                sleep 0.2
            done
        ) &
    fi
}

configure_display_and_gpu() {
    if [[ "${DISPLAY_BACKEND}" == "gtk" ]]; then
        if [[ "${ENABLE_GL:-false}" == "true" || "${QEMU_GL:-0}" == "1" ]]; then
            GPU_DEVICE="virtio-vga-gl"
            DISPLAY_OPTS=("-display" "gtk,gl=on,zoom-to-fit=on,show-cursor=on")
        else
            GPU_DEVICE="virtio-vga"
            DISPLAY_OPTS=("-display" "gtk,zoom-to-fit=on,show-cursor=on" "-vnc" "${VNC_PORT}")
        fi
    elif [[ "${DISPLAY_BACKEND}" == "sdl" ]]; then
        if [[ "${ENABLE_GL:-false}" == "true" || "${QEMU_GL:-0}" == "1" ]]; then
            GPU_DEVICE="virtio-vga-gl"
            DISPLAY_OPTS=("-display" "sdl,gl=on,show-cursor=on")
        else
            GPU_DEVICE="virtio-vga"
            DISPLAY_OPTS=("-display" "sdl,show-cursor=on" "-vnc" "${VNC_PORT}")
        fi
    elif [[ "${DISPLAY_BACKEND}" == "none" ]]; then
        GPU_DEVICE="virtio-vga"
        DISPLAY_OPTS=("-display" "none" "-vnc" "${VNC_PORT}")
    else
        GPU_DEVICE="virtio-vga"
        DISPLAY_OPTS=("-display" "${DISPLAY_BACKEND}" "-vnc" "${VNC_PORT}")
    fi
}

run_iso() {
    ensure_iso
    local efi_banner=""
    local efi_args=()
    if [[ "${USE_EFI}" == "true" ]]; then
        local ovmf
        ovmf=$(find_ovmf) || { echo "[-] Error: OVMF UEFI firmware not found on host!"; exit 1; }
        efi_banner=" (UEFI Mode: ${ovmf})"
        efi_args=("-bios" "${ovmf}")
    fi

    echo "=========================================================="
    echo " Starting MyelinOS Live ISO (LFS systemd + GNOME 50)${efi_banner} in QEMU"
    echo " - Live Medium:    ${ISO_IMAGE}"
    echo " - Serial Console: Auto-login active on stdio"
    echo " - GNOME Desktop:  VirtIO GPU display available at VNC localhost:5901"
    echo " To exit: type 'poweroff' in root shell or press 'Ctrl-a x'"
    echo "=========================================================="

    KVM_ARG=""
    if [[ -r /dev/kvm && -w /dev/kvm ]]; then
        KVM_ARG="-enable-kvm"
    fi

    # Auto-spawn vncviewer in the background once VNC is listening
    auto_launch_vncviewer
    configure_display_and_gpu

    exec qemu-system-x86_64 \
        ${KVM_ARG} \
        -m "${MEMORY}" \
        -smp "${SMP}" \
        "${efi_args[@]}" \
        -cdrom "${ISO_IMAGE}" \
        -boot d \
        -netdev user,id=net0,hostfwd=tcp::2222-:22 \
        -device virtio-net-pci,netdev=net0 \
        -device "${GPU_DEVICE}" \
        -device virtio-tablet-pci \
        -device intel-hda -device hda-duplex \
        -serial mon:stdio \
        "${DISPLAY_OPTS[@]}"
}

run_uefi_disk() {
    ensure_uefi_disk
    local ovmf
    ovmf=$(find_ovmf) || { echo "[-] Error: OVMF UEFI firmware not found on host!"; exit 1; }

    echo "=========================================================="
    echo " Starting MyelinOS UEFI GPT Disk (GNOME 50 Desktop) in QEMU"
    echo " - Firmware:       ${ovmf}"
    echo " - Disk Medium:    ${UEFI_DISK} (GPT Partition Table)"
    echo " - Serial Console: Auto-login active on stdio"
    echo " - GNOME Desktop:  VirtIO GPU display available at VNC localhost:5901"
    echo " - SSH Service:    Forwarded to host localhost:2222"
    echo " To exit: type 'poweroff' in root shell or press 'Ctrl-a x'"
    echo "=========================================================="

    KVM_ARG=""
    if [[ -r /dev/kvm && -w /dev/kvm ]]; then
        KVM_ARG="-enable-kvm"
    fi

    auto_launch_vncviewer
    configure_display_and_gpu

    exec qemu-system-x86_64 \
        ${KVM_ARG} \
        -m "${MEMORY}" \
        -smp "${SMP}" \
        -bios "${ovmf}" \
        -drive file="${UEFI_DISK}",format=raw,if=virtio \
        -netdev user,id=net0,hostfwd=tcp::2222-:22 \
        -device virtio-net-pci,netdev=net0 \
        -device "${GPU_DEVICE}" \
        -device virtio-tablet-pci \
        -device intel-hda -device hda-duplex \
        -serial mon:stdio \
        "${DISPLAY_OPTS[@]}"
}

run_interactive() {
    ensure_images
    echo "=========================================================="
    echo " Starting MyelinOS (LFS systemd + GNOME 50 Desktop) in QEMU"
    echo " - Serial Console: Auto-login active on stdio"
    echo " - GNOME Desktop:  VirtIO GPU display available at VNC localhost:5901"
    echo " - SSH Service:    Forwarded to host localhost:2222"
    echo " To exit: type 'poweroff' in root shell or press 'Ctrl-a x'"
    echo "=========================================================="
    
    KVM_ARG=""
    if [[ -r /dev/kvm && -w /dev/kvm ]]; then
        KVM_ARG="-enable-kvm"
    fi

    # Auto-spawn vncviewer in the background once VNC is listening
    auto_launch_vncviewer
    configure_display_and_gpu

    exec qemu-system-x86_64 \
        ${KVM_ARG} \
        -m "${MEMORY}" \
        -smp "${SMP}" \
        -kernel "${KERNEL}" \
        -drive file="${ROOTFS}",format=raw,if=virtio \
        -netdev user,id=net0,hostfwd=tcp::2222-:22 \
        -device virtio-net-pci,netdev=net0 \
        -device "${GPU_DEVICE}" \
        -device virtio-tablet-pci \
        -device intel-hda -device hda-duplex \
        -serial mon:stdio \
        "${DISPLAY_OPTS[@]}" \
        -append "root=/dev/vda rw console=ttyS0 init=/usr/lib/systemd/systemd audit=0 selinux=0 enforcing=0 quiet"
}

run_test() {
    ensure_images
    echo "[*] Running automated QEMU boot & display server test..."
    python3 "${SCRIPT_DIR}/test_boot.py"
}

run_iso_test() {
    ensure_iso
    echo "[*] Running automated Live ISO boot & display verification test..."
    python3 "${SCRIPT_DIR}/test_iso_boot.py"
}

run_uefi_test() {
    ensure_uefi_disk
    echo "[*] Running automated UEFI GPT disk boot & application verification test..."
    python3 "${SCRIPT_DIR}/test_uefi_boot.py"
}

MODE="interactive"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --interactive)
            MODE="interactive"
            shift
            ;;
        --efi)
            USE_EFI=true
            shift
            ;;
        --uefi-disk)
            MODE="uefi-disk"
            shift
            ;;
        --uefi-test)
            MODE="uefi-test"
            shift
            ;;
        --iso)
            MODE="iso"
            shift
            ;;
        --iso-test)
            MODE="iso-test"
            shift
            ;;
        --gui)
            DISPLAY_BACKEND="gtk"
            shift
            ;;
        --gl)
            ENABLE_GL="true"
            DISPLAY_BACKEND="gtk"
            shift
            ;;
        --test)
            MODE="test"
            shift
            ;;
        --build)
            echo "[*] Rebuilding bootstrap image..."
            python3 "${ROOT_DIR}/build/bootstrap/bootstrap.py"
            shift
            ;;
        --build-iso)
            echo "[*] Rebuilding Live ISO..."
            python3 "${ROOT_DIR}/tools/build_iso.py" --force
            shift
            ;;
        --build-uefi)
            echo "[*] Rebuilding UEFI GPT disk image..."
            python3 "${ROOT_DIR}/tools/build_uefi_disk.py"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

if [[ "${MODE}" == "test" ]]; then
    run_test
elif [[ "${MODE}" == "iso-test" ]]; then
    run_iso_test
elif [[ "${MODE}" == "uefi-test" ]]; then
    run_uefi_test
elif [[ "${MODE}" == "iso" ]]; then
    run_iso
elif [[ "${MODE}" == "uefi-disk" ]] || [[ "${USE_EFI}" == "true" && "${MODE}" == "interactive" ]]; then
    run_uefi_disk
else
    run_interactive
fi
