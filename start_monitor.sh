#!/bin/bash
cd /root/.openclaw/workspace
nohup python3 bot_monitor.py > /tmp/monitor.log 2>&1 &
echo $! > /tmp/monitor.pid
echo "Monitor started with PID: $(cat /tmp/monitor.pid)"
