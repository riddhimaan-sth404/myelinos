#!/usr/bin/env bash
# MyelinOS QEMU Runner Script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

KERNEL="${ROOT_DIR}/build/images/vmlinuz"
ROOTFS="${ROOT_DIR}/build/images/myelinos-rootfs.ext4"
MEMORY="${QEMU_MEM:-1024M}"
SMP="${QEMU_SMP:-2}"

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --interactive       Launch interactive QEMU session on serial console (default)"
    echo "  --test              Run automated verification test suite"
    echo "  --build             Rebuild rootfs image before running"
    echo "  -h, --help          Show this help message"
    echo ""
    echo "Environment Variables:"
    echo "  QEMU_MEM            Memory size (default: 1024M)"
    echo "  QEMU_SMP            Number of CPU cores (default: 2)"
    echo ""
    echo "To exit interactive QEMU: press 'Ctrl-a x' or run 'poweroff' inside the shell."
}

# Auto-build if images don't exist
ensure_images() {
    if [[ ! -f "${KERNEL}" || ! -f "${ROOTFS}" ]]; then
        echo "[*] Images missing. Running bootstrap first..."
        python3 "${ROOT_DIR}/build/bootstrap/bootstrap.py"
    fi
}

run_interactive() {
    ensure_images
    echo "=========================================================="
    echo " Starting MyelinOS (LFS systemd) in QEMU..."
    echo " To exit: type 'poweroff' in root shell or press 'Ctrl-a x'"
    echo "=========================================================="
    
    KVM_ARG=""
    if [[ -r /dev/kvm && -w /dev/kvm ]]; then
        KVM_ARG="-enable-kvm"
    fi

    exec qemu-system-x86_64 \
        ${KVM_ARG} \
        -m "${MEMORY}" \
        -smp "${SMP}" \
        -kernel "${KERNEL}" \
        -drive file="${ROOTFS}",format=raw,if=virtio \
        -append "root=/dev/vda rw console=ttyS0 init=/usr/lib/systemd/systemd audit=0 selinux=0 enforcing=0 quiet" \
        -nographic
}

run_test() {
    ensure_images
    echo "[*] Running automated QEMU boot test..."
    python3 "${SCRIPT_DIR}/test_boot.py"
}

MODE="interactive"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --interactive)
            MODE="interactive"
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
else
    run_interactive
fi
