#!/bin/bash
# Start dmdserver + zeclock locally for development
set -e

COLOR="${1:-auto}"
MODE="${2:-real}"  # "real" or "virtual"
DMDSERVER_BIN="$HOME/.zeclock/bin/dmdserver"
DMDSERVER_INI="$HOME/.zeclock/config/dmdserver.ini"
DMDSERVER_VIRTUAL_INI="$(dirname "$0")/../config/dmdserver-virtual.ini"
PIDFILE="/tmp/zeclock-dmdserver.pid"

# Kill any existing instances
scripts/dev-stop.sh 2>/dev/null || true

if [ "$MODE" = "virtual" ]; then
    echo "▶️  Starting fake dmdserver (virtual — browser preview)..."
    uv run python scripts/fake-dmdserver.py 6789 &
else
    echo "▶️  Starting dmdserver (real ZeDMD)..."
    $DMDSERVER_BIN -c "$DMDSERVER_INI" -w -l 2>&1 &
fi
echo $! > "$PIDFILE"

echo "⏳ Waiting for dmdserver (up to 20s)..."
for i in $(seq 1 20); do
    if bash -c "echo > /dev/tcp/localhost/6789" 2>/dev/null; then
        echo "✅ dmdserver ready on :6789"
        break
    fi
    if [ $i -eq 20 ]; then
        echo "⚠️  dmdserver port not open after 20s — starting zeclock anyway"
    fi
    sleep 1
done

echo "▶️  Starting zeclock (color=$COLOR) — Ctrl+C to stop"
trap 'echo ""; scripts/dev-stop.sh' INT TERM

uv run zeclock --color "$COLOR"

# Cleanup on exit
scripts/dev-stop.sh
