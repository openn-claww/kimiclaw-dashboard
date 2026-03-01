#!/bin/bash
# settle.sh — Manually check and settle all open trades
cd "$(dirname "${BASH_SOURCE[0]}")"
echo "Checking open trades for settlement..."
python3 trade_manager.py settle
echo ""
python3 trade_manager.py status
