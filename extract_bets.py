import re

print("=" * 100)
print("ALL BETS PLACED BY V6 BOT - March 8, 2026")
print("=" * 100)
print(f"{'#':<5} {'Time':<20} {'Market':<10} {'Side':<6} {'Entry Price':<12} {'Edge':<10} {'Size':<10}")
print("-" * 100)

count = 0
with open('all_bets_raw.txt', 'r') as f:
    for line in f:
        count += 1
        # Extract data using regex
        time_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        market_match = re.search(r'(BTC|ETH)/5m', line)
        side_match = re.search(r'\s(YES|NO)\s', line)
        price_match = re.search(r'@\s+([\d.]+)', line)
        edge_match = re.search(r'edge=([\d.]+)%', line)
        size_match = re.search(r'size=\$([\d.]+)', line)
        
        if all([time_match, market_match, side_match, price_match, edge_match, size_match]):
            time = time_match.group(1)
            market = market_match.group(1)
            side = side_match.group(1)
            price = price_match.group(1)
            edge = edge_match.group(1)
            size = size_match.group(1)
            
            print(f"{count:<5} {time:<20} {market+'/5m':<10} {side:<6} ${price:<11} {edge+'%':<10} ${size:<10}")

print("=" * 100)
print(f"Total bets: {count}")
print("=" * 100)
