#!/bin/bash
# Step 2: Install zeClock — pre-built libzedmd + Python app + DotClk resources
set -euo pipefail

ZECLOCK_HOME="/home/zeclock"
ZECLOCK_DATA="${ZECLOCK_HOME}/.zeclock"

echo ">>> Installing libzedmd ${LIBZEDMD_VERSION} (pre-built aarch64)..."

# Use pre-downloaded tarball if available, otherwise download
LIBZEDMD_VER_NUM="${LIBZEDMD_VERSION#v}"
mkdir -p "${ZECLOCK_DATA}/lib"
if [ -f /tmp/zeclock-src/.libzedmd-aarch64.tar.gz ]; then
    echo "  Using pre-downloaded libzedmd tarball..."
    tar xzf /tmp/zeclock-src/.libzedmd-aarch64.tar.gz -C "${ZECLOCK_DATA}/lib"
else
    LIBZEDMD_URL="https://github.com/PPUC/libzedmd/releases/download/${LIBZEDMD_VERSION}/libzedmd-${LIBZEDMD_VER_NUM}-linux-aarch64.tar.gz"
    curl -sSL "${LIBZEDMD_URL}" | tar xz -C "${ZECLOCK_DATA}/lib"
fi
echo "${LIBZEDMD_VERSION}" > "${ZECLOCK_DATA}/lib/.libzedmd-version"

# Remove test binaries and static lib — keep only shared libs
rm -f "${ZECLOCK_DATA}/lib/zedmd-client" "${ZECLOCK_DATA}/lib/zedmd-client-portable" \
      "${ZECLOCK_DATA}/lib/zedmd-test" "${ZECLOCK_DATA}/lib/zedmd-test-portable" \
      "${ZECLOCK_DATA}/lib/libzedmd.a"
rm -rf "${ZECLOCK_DATA}/lib/test"

# Do NOT copy to /usr/local/lib — use LD_LIBRARY_PATH in systemd service only

# Trixie ships libgpiod3 (SONAME 3) but libzedmd needs libgpiod.so.2 (SONAME 2, v1.x API)
# Use pre-downloaded .deb if available (installed with other debs in 01-system-setup.sh)
if ! dpkg -l libgpiod2 2>/dev/null | grep -q "^ii"; then
    if [ -f /tmp/zeclock-src/.debs/libgpiod2.deb ]; then
        dpkg -i /tmp/zeclock-src/.debs/libgpiod2.deb
    else
        curl -sSL http://ftp.debian.org/debian/pool/main/libg/libgpiod/libgpiod2_1.6.3-1+b3_arm64.deb -o /tmp/libgpiod2.deb
        dpkg -i /tmp/libgpiod2.deb
        rm /tmp/libgpiod2.deb
    fi
fi

ldconfig

echo ">>> Installing zeClock Python application..."

# Create virtualenv
python3 -m venv "${ZECLOCK_HOME}/venv"
source "${ZECLOCK_HOME}/venv/bin/activate"

# Install Python deps using pre-downloaded wheels (no network, fast)
WHEELS="/tmp/zeclock-src/.wheels"
if [ -d "${WHEELS}" ] && [ "$(ls ${WHEELS}/*.whl 2>/dev/null | wc -l)" -gt 0 ]; then
    echo "  Using pre-downloaded wheels from ${WHEELS}..."
    pip install --no-cache-dir --no-index --find-links "${WHEELS}" \
        pillow colorama pyyaml aiohttp pyserial reolink-aio
else
    echo "  WARNING: No pre-downloaded wheels found, downloading from network..."
    pip install --no-cache-dir \
        pillow \
        colorama \
        pyyaml \
        aiohttp \
        pyserial \
        reolink-aio
fi

deactivate

echo ">>> Bundling DotClk resources zip (will be extracted to /data at first boot)..."

# Store the zip in the image — extraction happens on /data at first boot
mkdir -p "${ZECLOCK_DATA}/resources"
if [ -f /tmp/zeclock-src/.dotclk-resources.zip ]; then
    cp /tmp/zeclock-src/.dotclk-resources.zip "${ZECLOCK_DATA}/resources/.dotclk-resources.zip"
else
    curl -sSL -o "${ZECLOCK_DATA}/resources/.dotclk-resources.zip" \
        https://github.com/sigmafx/DotClk-Resources/archive/refs/heads/master.zip
fi
echo "  Zip size: $(du -sh "${ZECLOCK_DATA}/resources/.dotclk-resources.zip" | cut -f1)"

# Copy custom fonts from the app if available
if [ -d "${ZECLOCK_HOME}/app/DotClk/Fonts" ]; then
    cp "${ZECLOCK_HOME}/app/DotClk/Fonts/"*.fnt "${ZECLOCK_DATA}/resources/Fonts/" 2>/dev/null || true
fi

# Fix ownership
chown -R zeclock:zeclock "${ZECLOCK_HOME}"

echo ">>> zeClock dependencies installed."
