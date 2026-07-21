#!/bin/bash
# Bundle GIF files into the image (optional — local builds only)
# GIFs are expected at /tmp/zeclock-gifs (Docker volume mount)
# The image chroot is at /tmp/<numeric_id>/
set -e

GIF_SRC="/tmp/zeclock-gifs"

# Check if GIFs are available
if [ ! -d "${GIF_SRC}" ]; then
    echo ">>> No GIFs at ${GIF_SRC} — skipping (CI build)"
    exit 0
fi

GIF_COUNT=$(find "${GIF_SRC}" -maxdepth 3 -name '*.gif' -o -name '*.GIF' 2>/dev/null | wc -l)
if [ "${GIF_COUNT}" -eq 0 ]; then
    echo ">>> No GIF files found in ${GIF_SRC} — skipping"
    exit 0
fi

# Find the chroot directory (packer-builder-arm uses /tmp/<numeric_id>/)
CHROOT=$(find /tmp -maxdepth 1 -mindepth 1 -type d -regex '/tmp/[0-9]+' 2>/dev/null | head -1)

if [ -z "${CHROOT}" ] || [ ! -d "${CHROOT}/home/zeclock" ]; then
    echo ">>> WARN: chroot dir not found, skipping GIFs"
    exit 0
fi

echo ">>> Copying ${GIF_COUNT} GIFs into image (chroot: ${CHROOT})..."
mkdir -p "${CHROOT}/home/zeclock/.zeclock/plugins/gif"
# Copy GIFs but exclude Windows Zone.Identifier metadata files
find "${GIF_SRC}" -mindepth 1 -maxdepth 1 -type d -exec cp -r {} "${CHROOT}/home/zeclock/.zeclock/plugins/gif/" \;
# Copy top-level GIFs if any
find "${GIF_SRC}" -maxdepth 1 -name '*.gif' -o -name '*.GIF' | while read -r f; do
    cp "$f" "${CHROOT}/home/zeclock/.zeclock/plugins/gif/"
done
# Remove Zone.Identifier files (Windows NTFS metadata)
find "${CHROOT}/home/zeclock/.zeclock/plugins/gif" -name '*:Zone.Identifier' -delete 2>/dev/null || true
chown -R 1000:1000 "${CHROOT}/home/zeclock/.zeclock/plugins"
FINAL_COUNT=$(find "${CHROOT}/home/zeclock/.zeclock/plugins/gif" -name '*.gif' -o -name '*.GIF' | wc -l)
FINAL_SIZE=$(du -sh "${CHROOT}/home/zeclock/.zeclock/plugins/gif" | cut -f1)
echo ">>> Done: ${FINAL_COUNT} GIFs (${FINAL_SIZE})"
