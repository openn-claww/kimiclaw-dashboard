#!/usr/bin/env python3
"""Move Strategy Performance section to top of dashboard"""

with open('/root/.openclaw/workspace/trading-dashboard/templates/index.html', 'r') as f:
    content = f.read()

# Find the page-dashboard div start
page_start = content.find('<div class="page active" id="page-dashboard">')
if page_start == -1:
    print("ERROR: Could not find page-dashboard div")
    exit(1)

# Find where stats-grid starts (after page-dashboard)
stats_start = content.find('<div class="stats-grid">', page_start)
if stats_start == -1:
    print("ERROR: Could not find stats-grid")
    exit(1)

# Find the Strategy Performance section
strategy_start = content.find('<div style="margin-top: 24px;" class="animate-fadeIn">\n                        <div class="card">\n                            <div class="card-header">\n                                <div class="card-title">\n                                    <i class="fas fa-filter"></i>\n                                    Strategy Performance History')

if strategy_start == -1:
    print("ERROR: Could not find Strategy Performance section")
    exit(1)

# Find where this section ends (before Recent Trades)
strategy_end = content.find('<!-- Trading Control Page -->', strategy_start)
if strategy_end == -1:
    strategy_end = content.find('<div style="margin-top: 24px;">\n                        <div class="card">\n                            <div class="card-header">\n                                <div class="card-title">\n                                    <i class="fas fa-history"></i>\n                                    Recent Trades', strategy_start)

if strategy_end == -1:
    print("ERROR: Could not find end of Strategy Performance section")
    exit(1)

# Extract the Strategy Performance section
strategy_section = content[strategy_start:strategy_end]

# Remove it from original location
content_without_strategy = content[:strategy_start] + content[strategy_end:]

# Insert it right after page-dashboard div starts (before stats-grid)
insert_pos = stats_start
new_content = content_without_strategy[:insert_pos] + strategy_section + content_without_strategy[insert_pos:]

# Write back
with open('/root/.openclaw/workspace/trading-dashboard/templates/index.html', 'w') as f:
    f.write(new_content)

print("✅ Strategy Performance History moved to TOP of dashboard")
print(f"Original position: {strategy_start}")
print(f"New position: {insert_pos}")
