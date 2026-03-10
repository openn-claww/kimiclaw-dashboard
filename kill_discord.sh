#!/bin/bash
# Kill all Discord-related processes
pkill -f discord 2>/dev/null
pkill -f polytrader 2>/dev/null
pkill -f all_bets 2>/dev/null
echo "Discord processes killed"

# Remove Discord env files
rm -f /root/.openclaw/workspace/.discord.env
rm -f /root/.openclaw/workspace/.discord-channels.env
rm -f /root/.openclaw/skills/polytrader/.env 2>/dev/null
echo "Discord config files removed"

# Clear any Discord webhooks from polytrader
unset DISCORD_WEBHOOK_URL
unset DISCORD_TOKEN
echo "Discord env vars cleared"
