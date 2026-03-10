#!/bin/bash
# Start the Polymarket Trading Dashboard

WORKSPACE="/root/.openclaw/workspace"
DASHBOARD_DIR="$WORKSPACE/trading-dashboard"
PIDFILE="$DASHBOARD_DIR/dashboard.pid"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

cd "$DASHBOARD_DIR" || exit 1

# Check if already running
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${RED}Dashboard is already running (PID: $PID)${NC}"
        echo "Visit: http://localhost:8080"
        exit 1
    else
        rm -f "$PIDFILE"
    fi
fi

echo -e "${BLUE}Starting PolyClaw Trading Dashboard...${NC}"

# Install dependencies if needed
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -q -r requirements.txt
fi

# Start the server
python3 dashboard_server.py > "$DASHBOARD_DIR/server.log" 2>&1 &
PID=$!
echo $PID > "$PIDFILE"

sleep 2

if ps -p "$PID" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Dashboard started successfully!${NC}"
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  Dashboard URL: http://localhost:8080${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Logs: tail -f $DASHBOARD_DIR/server.log"
else
    echo -e "${RED}✗ Failed to start dashboard${NC}"
    echo "Check logs: $DASHBOARD_DIR/server.log"
    exit 1
fi