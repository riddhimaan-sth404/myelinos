#!/usr/bin/env bash
# MyelinOS QEMU Runner Script
# Launches MyelinOS with systemd, VirtIO GPU, OpenSSH, and COSMIC Desktop Environment
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

KERNEL="${ROOT_DIR}/build/images/vmlinuz"
ROOTFS="${ROOT_DIR}/build/images/myelinos-rootfs.ext4"
ISO_IMAGE="${ROOT_DIR}/build/images/myelinos-live.iso"
MEMORY="${QEMU_MEM:-2048M}"
SMP="${QEMU_SMP:-2}"
VNC_PORT="${QEMU_VNC:-:1}"
DISPLAY_BACKEND="${QEMU_DISPLAY:-none}"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --interactive       Launch interactive QEMU session on serial console (default)"
    echo "  --iso               Launch interactive Live ISO session in QEMU"
    echo "  --iso-test          Run automated Live ISO verification test suite"
    echo "  --gui               Launch QEMU with a graphical window (GTK/SDL if host displays available)"
    echo "  --test              Run automated verification test suite on disk image"
    echo "  --build             Rebuild rootfs image before running"
    echo "  --build-iso         Rebuild Live ISO before running"
    echo "  -h, --help          Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  QEMU_MEM            Memory size (default: 2048M)"
    echo "  QEMU_SMP            Number of CPU cores (default: 2)"
    echo "  QEMU_VNC            VNC display offset (default: :1 -> localhost:5901)"
    echo "  QEMU_DISPLAY        Display backend (default: none)"
    echo ""
    echo "Desktop Environment & Remote Access:"
    echo "  - Serial Console:   Interactive terminal attached directly to stdio"
    echo "  - COSMIC Desktop:   Rendered via VirtIO GPU on VNC display localhost:5901"
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

run_iso() {
    ensure_iso
    echo "=========================================================="
    echo " Starting MyelinOS Live ISO (LFS systemd + COSMIC) in QEMU"
    echo " - Live Medium:    ${ISO_IMAGE}"
    echo " - Serial Console: Auto-login active on stdio"
    echo " - COSMIC Desktop: VirtIO GPU display available at VNC localhost:5901"
    echo " To exit: type 'poweroff' in root shell or press 'Ctrl-a x'"
    echo "=========================================================="

    KVM_ARG=""
    if [[ -r /dev/kvm && -w /dev/kvm ]]; then
        KVM_ARG="-enable-kvm"
    fi

    DISPLAY_OPTS=("-display" "${DISPLAY_BACKEND}" "-vnc" "${VNC_PORT}")
    if [[ "${DISPLAY_BACKEND}" != "none" ]]; then
        DISPLAY_OPTS=("-display" "${DISPLAY_BACKEND}")
    fi

    exec qemu-system-x86_64 \
        ${KVM_ARG} \
        -m "${MEMORY}" \
        -smp "${SMP}" \
        -cdrom "${ISO_IMAGE}" \
        -boot d \
        -netdev user,id=net0,hostfwd=tcp::2222-:22 \
        -device virtio-net-pci,netdev=net0 \
        -device virtio-vga \
        -serial mon:stdio \
        "${DISPLAY_OPTS[@]}"
}

run_interactive() {
    ensure_images
    echo "=========================================================="
    echo " Starting MyelinOS (LFS systemd + COSMIC Desktop) in QEMU"
    echo " - Serial Console: Auto-login active on stdio"
    echo " - COSMIC Desktop: VirtIO GPU display available at VNC localhost:5901"
    echo " - SSH Service:    Forwarded to host localhost:2222"
    echo " To exit: type 'poweroff' in root shell or press 'Ctrl-a x'"
    echo "=========================================================="
    
    KVM_ARG=""
    if [[ -r /dev/kvm && -w /dev/kvm ]]; then
        KVM_ARG="-enable-kvm"
    fi

    DISPLAY_OPTS=("-display" "${DISPLAY_BACKEND}" "-vnc" "${VNC_PORT}")
    if [[ "${DISPLAY_BACKEND}" != "none" ]]; then
        DISPLAY_OPTS=("-display" "${DISPLAY_BACKEND}")
    fi

    exec qemu-system-x86_64 \
        ${KVM_ARG} \
        -m "${MEMORY}" \
        -smp "${SMP}" \
        -kernel "${KERNEL}" \
        -drive file="${ROOTFS}",format=raw,if=virtio \
        -netdev user,id=net0,hostfwd=tcp::2222-:22 \
        -device virtio-net-pci,netdev=net0 \
        -device virtio-vga \
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

MODE="interactive"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --interactive)
            MODE="interactive"
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
elif [[ "${MODE}" == "iso" ]]; then
    run_iso
else
    run_interactive
fi
