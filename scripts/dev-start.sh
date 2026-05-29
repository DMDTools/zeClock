#!/bin/bash
# Start zeclock locally for development
# Usage: dev-start.sh [COLOR] [MODE]
#   MODE: "real" (default) — uses --backend auto (libzedmd direct)
#         "virtual"        — starts virtual-dmd.py + uses --backend dmdserver
set -e

COLOR="${1:-auto}"
MODE="${2:-real}"  # "real" or "virtual"
PIDFILE="/tmp/zeclock-dmdserver.pid"

# Kill any existing instances
scripts/dev-stop.sh 2>/dev/null || true

if [ "$MODE" = "virtual" ]; then
    echo "▶️  Starting virtual mode (DMD in browser at http://localhost:8080)..."
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
else
    echo "▶️  Starting zeclock with direct ZeDMD (libzedmd)..."
    BACKEND_ARGS="--backend auto"
fi

echo "▶️  Starting zeclock (color=$COLOR, backend=${MODE}) — Ctrl+C to stop"
trap 'echo ""; scripts/dev-stop.sh' INT TERM

uv run zeclock --color "$COLOR" $BACKEND_ARGS

# Cleanup on exit
scripts/dev-stop.sh
