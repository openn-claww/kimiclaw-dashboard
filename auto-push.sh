#!/bin/bash
# Auto-push script for dashboard updates
# Pushes directly to master without PRs

cd /root/.openclaw/workspace

# Configure git to push directly
git config pull.rebase false

# Add all changes
git add -A

# Commit with timestamp
COMMIT_MSG="Dashboard update: $(date '+%Y-%m-%d %H:%M:%S')"
git commit -m "$COMMIT_MSG" || exit 0

# Push directly to master (no PR)
git push origin master

echo "✅ Pushed to master: $COMMIT_MSG"
