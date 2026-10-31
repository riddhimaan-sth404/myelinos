.PHONY: all build run test clean help

all: build

help:
	@echo "MyelinOS (LFS systemd) Build & Run Targets:"
	@echo "  make build  - Bootstrap the LFS rootfs and build ext4 disk image"
	@echo "  make run    - Run interactive QEMU serial session"
	@echo "  make test   - Run automated verification test suite"
	@echo "  make clean  - Remove built rootfs and disk images"

build:
	python3 build/bootstrap/bootstrap.py

run:
	./tools/run_qemu.sh --interactive

test:
	./tools/run_qemu.sh --test

clean:
	podman unshare rm -rf build/bootstrap/rootfs build/images/myelinos-rootfs.ext4 build/images/vmlinuz
