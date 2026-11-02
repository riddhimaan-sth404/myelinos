.PHONY: all build uefi iso installer-iso run run-system run-installer run-uefi run-iso test test-uefi test-iso clean help

all: build uefi iso installer-iso

help:
	@echo "MyelinOS (LFS systemd + GNOME 50) Build & Run Targets:"
	@echo "  make build         - Bootstrap rootfs and build ext4 disk image"
	@echo "  make uefi          - Build bootable UEFI GPT disk image"
	@echo "  make iso           - Build bootable hybrid Live ISO image"
	@echo "  make installer-iso - Build ultra-lightweight bootstrap installer ISO (~50 MB)"
	@echo "  make run-system    - Run installed MyelinOS system in QEMU (./run_system.sh)"
	@echo "  make run-installer - Run TUI Bootstrap Installer in QEMU (./run_installer.sh)"
	@echo "  make test          - Run automated verification test suite on disk image"
	@echo "  make test-uefi     - Run automated verification test suite on UEFI GPT disk"
	@echo "  make test-iso      - Run automated verification test suite on Live ISO"
	@echo "  make clean         - Remove built rootfs, disk images, and ISO staging"

build:
	python3 build/bootstrap/bootstrap.py

uefi:
	python3 tools/build_uefi_disk.py

iso:
	python3 tools/build_iso.py

installer-iso:
	python3 tools/build_bootstrap_iso.py

run: run-system

run-system:
	./run_system.sh

run-installer:
	./run_installer.sh

run-uefi:
	./tools/run_qemu.sh --uefi-disk

run-iso:
	./tools/run_qemu.sh --iso

test:
	./tools/run_qemu.sh --test

test-uefi:
	./tools/run_qemu.sh --uefi-test

test-iso:
	./tools/run_qemu.sh --iso-test

clean:
	podman unshare rm -rf build/bootstrap/rootfs build/images/myelinos-rootfs.ext4 build/images/myelinos-live.iso build/images/vmlinuz build/iso_staging
