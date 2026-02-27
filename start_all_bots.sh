#!/bin/bash
# Launch all 4 optimized wallet bots

echo "=========================================="
echo "STARTING 4 OPTIMIZED WALLET BOTS"
echo "=========================================="
echo ""

# Kill any existing bots
pkill -f "wallet.*bot.*optimized.py" 2>/dev/null
sleep 1

# Start Wallet 1 - Conservative
nohup python3 /root/.openclaw/workspace/wallet1_bot_optimized.py > /tmp/w1.log 2>&1 &
echo "✅ Wallet 1 (Conservative) - PID: $!"

# Start Wallet 2 - Aggressive  
nohup python3 /root/.openclaw/workspace/wallet2_bot_optimized.py > /tmp/w2.log 2>&1 &
echo "✅ Wallet 2 (Aggressive) - PID: $!"

# Start Wallet 3 - BTC Specialist
nohup python3 /root/.openclaw/workspace/wallet3_bot_optimized.py > /tmp/w3.log 2>&1 &
echo "✅ Wallet 3 (BTC Specialist) - PID: $!"

# Start Wallet 4 - Arbitrage Hunter
nohup python3 /root/.openclaw/workspace/wallet4_bot_optimized.py > /tmp/w4.log 2>&1 &
echo "✅ Wallet 4 (Arbitrage Hunter) - PID: $!"

echo ""
echo "=========================================="
echo "All bots started!"
echo ""
echo "Monitor logs:"
echo "  tail -f /tmp/w1.log  # Wallet 1"
echo "  tail -f /tmp/w2.log  # Wallet 2"
echo "  tail -f /tmp/w3.log  # Wallet 3"
echo "  tail -f /tmp/w4.log  # Wallet 4"
echo ""
echo "Stop all: pkill -f 'wallet.*bot.*optimized.py'"
echo "=========================================="
