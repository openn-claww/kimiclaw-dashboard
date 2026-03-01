#!/usr/bin/env python3
"""Debug script to check what markets are being found"""

import subprocess

cmd = "bash -c 'cd /root/.openclaw/skills/polyclaw && source .env && uv run python scripts/polyclaw.py markets search \"Iran\" --limit 5'"
result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)

print("Return code:", result.returncode)
print("\nStdout:")
print(result.stdout)
print("\nStderr:")
print(result.stderr)

# Parse the output
if result.returncode == 0:
    lines = result.stdout.strip().split('\n')[2:]  # Skip header
    print("\n\nParsed lines:")
    for i, line in enumerate(lines):
        print(f"Line {i}: repr={repr(line)}")
        print(f"  Has '|': {'|' in line}")
        print(f"  Has '$': {'$' in line}")
        if '|' in line:
            parts = line.split('|')
            print(f"  Parts count: {len(parts)}")
            print(f"  Parts: {parts}")
            if len(parts) >= 5:
                try:
                    market_id = parts[0].strip()
                    yes_price_str = parts[1].replace('$', '').strip()
                    no_price_str = parts[2].replace('$', '').strip()
                    volume_str = parts[3].strip().replace('K', '000').replace('M', '000000').replace('$', '').replace(',', '')
                    question = parts[4].strip()
                    
                    yes_price = float(yes_price_str)
                    no_price = float(no_price_str)
                    volume = float(volume_str)
                    
                    print(f"  Market: {market_id}")
                    print(f"    YES: ${yes_price} | NO: ${no_price} | Vol: ${volume}")
                    print(f"    Q: {question}")
                    
                    # Check our criteria
                    if volume > 50000:
                        print(f"    ✓ Volume OK (${volume:,.0f})")
                        if yes_price < 0.40 and yes_price > 0:
                            print(f"    ✓ YES price OK (${yes_price:.2f})")
                        elif no_price < 0.40 and no_price > 0:
                            print(f"    ✓ NO price OK (${no_price:.2f})")
                        else:
                            print(f"    ✗ Prices not in range (YES: ${yes_price:.2f}, NO: ${no_price:.2f})")
                    else:
                        print(f"    ✗ Volume too low (${volume:,.0f})")
                except Exception as e:
                    print(f"  Parse error: {e}")
