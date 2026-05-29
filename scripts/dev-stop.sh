#!/bin/bash
# Stop local zeclock + virtual-dmd
PIDFILE="/tmp/zeclock-dmdserver.pid"

echo "🛑 Stopping local zeclock..."

# Kill zeclock python process
pkill -f "from zeclock.clock" 2>/dev/null || true

# Kill virtual-dmd via pidfile or pattern
if [ -f "$PIDFILE" ]; then
    kill -9 "$(cat $PIDFILE)" 2>/dev/null || true
    rm -f "$PIDFILE"
fi
pkill -9 -f "virtual-dmd.py" 2>/dev/null || true

echo "✅ Stopped"
