#!/bin/bash
# Start zeclock locally for development
# Usage: dev-start.sh [COLOR] [MODE]
#   MODE: "real" (default) — uses --backend auto (libzedmd direct)
#         "virtual"        — starts virtual-dmd.py + uses --backend dmdserver (128x32)
#         "virtual-hd"    — starts virtual-dmd.py + uses --backend dmdserver (256x64 HD)
set -e

COLOR="${1:-auto}"
MODE="${2:-real}"  # "real", "virtual", or "virtual-hd"
PIDFILE="/tmp/zeclock-dmdserver.pid"

# Kill any existing instances
scripts/dev-stop.sh 2>/dev/null || true

if [ "$MODE" = "virtual" ] || [ "$MODE" = "virtual-hd" ]; then
    if [ "$MODE" = "virtual-hd" ]; then
        echo "▶️  Starting virtual HD mode (256x64, DMD in browser at http://localhost:3000)..."
    else
        echo "▶️  Starting virtual mode (128x32, DMD in browser at http://localhost:3000)..."
    fi
    uv run python scripts/virtual-dmd.py 6789 &
    echo $! > "$PIDFILE"

    echo "⏳ Waiting for virtual-dmd (up to 20s)..."
    for i in $(seq 1 20); do
        if bash -c "echo > /dev/tcp/localhost/6789" 2>/dev/null; then
            echo "✅ virtual-dmd ready on :6789"
            break
        fi
        if [ $i -eq 20 ]; then
            echo "⚠️  virtual-dmd port not open after 20s — starting zeclock anyway"
        fi
        sleep 1
    done

    BACKEND_ARGS="--backend dmdserver"
    if [ "$MODE" = "virtual-hd" ]; then
        BACKEND_ARGS="$BACKEND_ARGS --hd"
    fi
else
    echo "▶️  Starting zeclock with direct ZeDMD (libzedmd)..."
    BACKEND_ARGS="--backend auto"
fi

echo "▶️  Starting zeclock (color=$COLOR, backend=${MODE}) — Ctrl+C to stop"
trap 'echo ""; scripts/dev-stop.sh' INT TERM

uv run zeclock --color "$COLOR" $BACKEND_ARGS

# Cleanup on exit
scripts/dev-stop.sh
