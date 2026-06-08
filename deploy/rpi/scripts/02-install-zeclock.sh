#!/bin/bash
# Step 2: Install zeClock — pre-built libzedmd + Python app + DotClk resources
set -euo pipefail

ZECLOCK_HOME="/home/zeclock"
ZECLOCK_DATA="${ZECLOCK_HOME}/.zeclock"

echo ">>> Installing libzedmd ${LIBZEDMD_VERSION} (pre-built aarch64)..."

# Download pre-built binaries (compatible with Trixie's glibc 2.41)
LIBZEDMD_VER_NUM="${LIBZEDMD_VERSION#v}"
LIBZEDMD_URL="https://github.com/PPUC/libzedmd/releases/download/${LIBZEDMD_VERSION}/libzedmd-${LIBZEDMD_VER_NUM}-linux-aarch64.tar.gz"

mkdir -p "${ZECLOCK_DATA}/lib"
curl -sSL "${LIBZEDMD_URL}" | tar xz -C "${ZECLOCK_DATA}/lib"
echo "${LIBZEDMD_VERSION}" > "${ZECLOCK_DATA}/lib/.libzedmd-version"

# Remove test binaries and static lib — keep only shared libs
rm -f "${ZECLOCK_DATA}/lib/zedmd-client" "${ZECLOCK_DATA}/lib/zedmd-client-portable" \
      "${ZECLOCK_DATA}/lib/zedmd-test" "${ZECLOCK_DATA}/lib/zedmd-test-portable" \
      "${ZECLOCK_DATA}/lib/libzedmd.a"
rm -rf "${ZECLOCK_DATA}/lib/test"

# Do NOT copy to /usr/local/lib — use LD_LIBRARY_PATH in systemd service only

# Trixie ships libgpiod3 (SONAME 3) but libzedmd needs libgpiod.so.2 (SONAME 2, v1.x API)
# Install libgpiod2 from Bookworm — dpkg -i handles it cleanly
curl -sSL http://ftp.debian.org/debian/pool/main/libg/libgpiod/libgpiod2_1.6.3-1+b3_arm64.deb -o /tmp/libgpiod2.deb
dpkg -i /tmp/libgpiod2.deb
rm /tmp/libgpiod2.deb

ldconfig

echo ">>> Installing zeClock Python application..."

# Create virtualenv
python3 -m venv "${ZECLOCK_HOME}/venv"
source "${ZECLOCK_HOME}/venv/bin/activate"

# Install Python deps (app itself will be installed via file provisioner)
# Use pre-downloaded wheels if available (faster than pip over network in qemu)
if [ -d /tmp/zeclock-src/.wheels ] && [ "$(ls /tmp/zeclock-src/.wheels/*.whl 2>/dev/null | wc -l)" -gt 0 ]; then
    echo "  Using pre-downloaded wheels..."
    pip install --no-cache-dir --no-index --find-links /tmp/zeclock-src/.wheels \
        pillow colorama pyyaml aiohttp pyserial 2>/dev/null \
    || pip install --no-cache-dir pillow colorama pyyaml aiohttp pyserial
else
    pip install --no-cache-dir \
        pillow \
        colorama \
        pyyaml \
        aiohttp \
        pyserial
fi

deactivate

echo ">>> Downloading DotClk resources..."

mkdir -p "${ZECLOCK_DATA}/resources"
curl -sSL -o /tmp/res.zip \
    https://github.com/sigmafx/DotClk-Resources/archive/refs/heads/master.zip
unzip -q /tmp/res.zip -d /tmp/res
cp -r /tmp/res/DotClk-Resources-master/Fonts "${ZECLOCK_DATA}/resources/Fonts"
cp -r /tmp/res/DotClk-Resources-master/Scenes "${ZECLOCK_DATA}/resources/animations"
rm -rf /tmp/res /tmp/res.zip

# Copy custom fonts from the app if available
if [ -d "${ZECLOCK_HOME}/app/DotClk/Fonts" ]; then
    cp "${ZECLOCK_HOME}/app/DotClk/Fonts/"*.fnt "${ZECLOCK_DATA}/resources/Fonts/" 2>/dev/null || true
fi

# Fix ownership
chown -R zeclock:zeclock "${ZECLOCK_HOME}"

echo ">>> zeClock dependencies installed."
