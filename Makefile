.PHONY: all build iso run run-iso test test-iso clean help

all: build iso

help:
	@echo "MyelinOS (LFS systemd + COSMIC) Build & Run Targets:"
	@echo "  make build     - Bootstrap rootfs and build ext4 disk image"
	@echo "  make iso       - Build bootable hybrid Live ISO image"
	@echo "  make run       - Run interactive QEMU serial session with disk image"
	@echo "  make run-iso   - Run interactive QEMU session with bootable Live ISO"
	@echo "  make test      - Run automated verification test suite on disk image"
	@echo "  make test-iso  - Run automated verification test suite on Live ISO"
	@echo "  make clean     - Remove built rootfs, disk images, and ISO staging"

build:
	python3 build/bootstrap/bootstrap.py

iso:
	python3 tools/build_iso.py

run:
	./tools/run_qemu.sh --interactive

run-iso:
	./tools/run_qemu.sh --iso

test:
	./tools/run_qemu.sh --test

test-iso:
	./tools/run_qemu.sh --iso-test

clean:
	podman unshare rm -rf build/bootstrap/rootfs build/images/myelinos-rootfs.ext4 build/images/myelinos-live.iso build/images/vmlinuz build/iso_staging
