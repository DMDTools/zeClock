#!/bin/bash
# Build libzedmd from source using Docker and install to ~/.zeclock/lib/
#
# This avoids needing libtool/automake/autoconf on the host system.
# Requires: docker with BuildKit support (Docker 18.09+)
#
# Usage:
#   scripts/build-libzedmd.sh
#
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LIB_DIR="$HOME/.zeclock/lib"

echo "╔════════════════════════════════════════════╗"
echo "║  🔧 Building libzedmd via Docker           ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# Create output directory
mkdir -p "$LIB_DIR"

# Build using Docker BuildKit output (exports files directly to host)
echo "🐳 Building in Docker container (this may take a few minutes)..."
DOCKER_BUILDKIT=1 docker build \
    -f "$SCRIPT_DIR/build-libzedmd.Dockerfile" \
    --output "type=local,dest=$LIB_DIR" \
    "$PROJECT_DIR"

echo ""
echo "✅ libzedmd built and installed to $LIB_DIR"
echo ""
echo "Installed files:"
ls -la "$LIB_DIR"/*.so* "$LIB_DIR/.libzedmd-version" 2>/dev/null || echo "  (no .so files found)"
echo ""
echo "Version: $(cat "$LIB_DIR/.libzedmd-version" 2>/dev/null || echo 'unknown')"
