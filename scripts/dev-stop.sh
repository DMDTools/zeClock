#!/bin/bash
# Stop local dmdserver + zeclock
PIDFILE="/tmp/zeclock-dmdserver.pid"

echo "🛑 Stopping local zeclock + dmdserver..."

# Kill zeclock python process
pkill -f "from zeclock.clock" 2>/dev/null || true

# Kill dmdserver via pidfile or pattern
if [ -f "$PIDFILE" ]; then
    kill -9 "$(cat $PIDFILE)" 2>/dev/null || true
    rm -f "$PIDFILE"
fi
pkill -9 -f "dmdserver" 2>/dev/null || true

echo "✅ Stopped"
