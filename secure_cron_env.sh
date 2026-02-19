#!/bin/bash
# Secure Cron Environment Setup
# Loads wallet credentials without exposing them in cron payload

# Load GitHub token if needed
if [ -f /root/.openclaw/workspace/.github.env ]; then
    export $(cat /root/.openclaw/workspace/.github.env | xargs)
fi

# Load PolyClaw environment
if [ -f /root/.openclaw/skills/polyclaw/.env ]; then
    export $(cat /root/.openclaw/skills/polyclaw/.env | grep -v '^#' | xargs)
fi

# Add uv to path
export PATH="$HOME/.local/bin:$PATH"

# Run the command passed as arguments
"$@"
