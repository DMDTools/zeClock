#!/bin/bash
# Build zeClock Raspberry Pi image using Docker
# Requires: Docker with privileged mode (for loop mounts inside container)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DOCKER_IMAGE="mkaczanowski/packer-builder-arm:latest"
OUTPUT_IMG="zeclock-rpi.img"
EXPORT_DIR="/tmp/zeclock-export"

echo "=== zeClock Raspberry Pi Image Builder ==="
echo ""

# Check Docker
if ! command -v docker &>/dev/null; then
    echo "ERROR: Docker is required but not installed."
    exit 1
fi

if ! docker info &>/dev/null 2>&1; then
    echo "ERROR: Docker daemon is not running. Start it with: sudo service docker start"
    exit 1
fi

# --- Export clean source tree (no .git, .venv, etc.) ---
echo "Exporting zeClock source tree..."
rm -rf "${EXPORT_DIR}"
mkdir -p "${EXPORT_DIR}"
git -C "${REPO_ROOT}" archive --format=tar HEAD | tar -x -C "${EXPORT_DIR}"
echo "  Exported to ${EXPORT_DIR} ($(du -sh "${EXPORT_DIR}" | cut -f1))"

# --- Pre-download .deb packages for aarch64 (avoids apt-get update in chroot) ---
echo "Pre-downloading .deb packages..."
DEBS_DIR="${EXPORT_DIR}/.debs"
mkdir -p "${DEBS_DIR}"
# f2fs-tools and libserialport0 for arm64 - direct from Debian mirrors
curl -sSL -o "${DEBS_DIR}/f2fs-tools.deb" \
    "http://deb.debian.org/debian/pool/main/f/f2fs-tools/f2fs-tools_1.16.0-1.1+b1_arm64.deb"
curl -sSL -o "${DEBS_DIR}/libserialport0.deb" \
    "http://deb.debian.org/debian/pool/main/libs/libserialport/libserialport0_0.1.2-1_arm64.deb"
echo "  Packages: $(ls "${DEBS_DIR}"/*.deb | wc -l) files ($(du -sh "${DEBS_DIR}" | cut -f1))"
echo "Pre-downloading Python wheels for aarch64..."
WHEELS_DIR="${EXPORT_DIR}/.wheels"
mkdir -p "${WHEELS_DIR}"
pip download \
    --dest "${WHEELS_DIR}" \
    --platform manylinux2014_aarch64 \
    --platform manylinux_2_27_aarch64 \
    --platform manylinux_2_28_aarch64 \
    --platform linux_aarch64 \
    --python-version 313 \
    --implementation cp \
    --abi cp313 \
    --only-binary=:all: \
    pillow colorama pyyaml aiohttp pyserial 2>/dev/null || true
# Also download pure-python packages
pip download \
    --dest "${WHEELS_DIR}" \
    --platform any \
    --python-version 313 \
    --implementation cp \
    --abi none \
    --only-binary=:all: \
    pillow colorama pyyaml aiohttp pyserial 2>/dev/null || true
echo "  Wheels: $(ls "${WHEELS_DIR}" | wc -l) files ($(du -sh "${WHEELS_DIR}" | cut -f1))"

# --- Pre-download DotClk resources zip (15 MB, included in image, extracted to /data at first boot) ---
echo "Pre-downloading DotClk resources zip..."
curl -sSL -o "${EXPORT_DIR}/.dotclk-resources.zip" \
    https://github.com/sigmafx/DotClk-Resources/archive/refs/heads/master.zip
echo "  Resources zip: $(du -sh "${EXPORT_DIR}/.dotclk-resources.zip" | cut -f1)"
echo ""

# --- Build with Packer ---
echo "Building Raspberry Pi image with Packer..."
echo "  Docker image: ${DOCKER_IMAGE}"
echo "  Output: ${SCRIPT_DIR}/${OUTPUT_IMG}"
echo ""

docker run --rm \
    --privileged \
    -v /dev:/dev \
    -v "${SCRIPT_DIR}:/build" \
    -v "${EXPORT_DIR}:/tmp/zeclock-export:ro" \
    -w /build \
    "${DOCKER_IMAGE}" \
    build rpi-zeclock.pkr.hcl

# --- Cleanup export ---
rm -rf "${EXPORT_DIR}"

# --- Output ---
if [ -f "${SCRIPT_DIR}/${OUTPUT_IMG}" ]; then
    echo ""
    echo "=== Build complete! ==="
    echo "Image: ${SCRIPT_DIR}/${OUTPUT_IMG}"
    echo "Size:  $(du -h "${SCRIPT_DIR}/${OUTPUT_IMG}" | cut -f1)"
    echo ""
    echo "Flash to SD card:"
    echo "  sudo dd if=${OUTPUT_IMG} of=/dev/sdX bs=4M status=progress"
    echo ""
    echo "First boot will:"
    echo "  - Create /data partition (p3) on remaining SD card space"
    echo "  - Format it as f2fs"
    echo "  - Initialize zeClock config"
else
    echo ""
    echo "WARNING: Output image not found at expected location."
    ls -la "${SCRIPT_DIR}/"*.img 2>/dev/null || echo "  No .img files found."
fi
