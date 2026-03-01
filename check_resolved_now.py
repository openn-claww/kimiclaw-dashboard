#!/usr/bin/env python3
import json

# Load positions
with open('/root/.openclaw/polyclaw/positions.json') as f:
    positions = json.load(f)

# Resolved markets with winners
resolved = {
    '1320793': 'No',        # Iran Feb 20 - NO won
    '1369917': 'Yes',       # BTC >$66K Feb 19 - YES won
    '1386650': 'No',        # Iran Feb 21 - NO won
    '1401343': 'Down',      # BTC Up/Down Feb 22 3AM - Down won
    '1385457': 'Warriors',  # Nuggets vs Warriors - Warriors won
    '1382242': 'Yes',       # BTC $66-68K Feb 22 - YES won (in range)
    '1382273': 'No',        # BTC >$68K Feb 22 - NO won
    '1388774': 'Spurs',     # Spurs vs Pistons - Spurs won
    '1385475': 'Trail Blazers',  # Blazers vs Suns - Trail Blazers won
    '1402947': 'Down',      # BTC Up/Down Feb 22 - Down won
}

print('Checking positions against resolved markets...')
print('='*70)

redeemable = []
losers = []

for pos in positions:
    market_id = pos.get('market_id')
    position_side = pos.get('position', '').strip()
    
    if market_id in resolved:
        winner = resolved[market_id]
        
        # Check if position matches winner
        pos_upper = position_side.upper()
        winner_upper = winner.upper()
        
        # Special case mapping for each market
        is_winner = False
        if market_id == '1385475' and pos_upper == 'NO':
            # Blazers vs Suns - position was NO (betting against Suns)
            # Winner was Trail Blazers, so NO on Suns = win
            is_winner = True
        elif market_id == '1388774' and pos_upper == 'YES':
            # Spurs vs Pistons - YES on Spurs
            is_winner = (winner == 'Spurs')
        elif market_id == '1385457' and pos_upper == 'YES':
            # Nuggets vs Warriors - YES on Nuggets
            is_winner = (winner == 'Nuggets')
        elif market_id == '1401343' and pos_upper == 'YES':
            # BTC Up/Down - YES means UP
            is_winner = (winner == 'Up')
        elif market_id == '1402947' and pos_upper == 'YES':
            # BTC Up/Down - YES means UP
            is_winner = (winner == 'Up')
        elif market_id == '1382273' and pos_upper == 'YES':
            # BTC >$68K - YES means above $68K
            is_winner = (winner == 'Yes')
        elif market_id == '1382242' and pos_upper == 'NO':
            # BTC $66-68K - NO means outside range
            is_winner = (winner == 'No')
        elif market_id == '1369917' and pos_upper == 'YES':
            # BTC >$66K Feb 19 - YES won
            is_winner = True
        elif market_id == '1320793' and pos_upper == 'NO':
            # Iran Feb 20 - NO won
            is_winner = True
        elif market_id == '1386650' and pos_upper == 'YES':
            # Iran Feb 21 - position YES, winner NO
            is_winner = False
        else:
            is_winner = (pos_upper == winner_upper)
        
        if is_winner:
            redeemable.append({
                'market_id': market_id,
                'question': pos.get('question'),
                'position': position_side,
                'amount': pos.get('entry_amount'),
                'winner': winner
            })
        else:
            losers.append({
                'market_id': market_id,
                'question': pos.get('question'),
                'position': position_side,
                'amount': pos.get('entry_amount'),
                'winner': winner
            })

print(f'\n✅ WINNING POSITIONS TO REDEEM ({len(redeemable)}):')
for r in redeemable:
    print(f"  • Market {r['market_id']}: {r['question']}")
    print(f"    Position: {r['position']} | Winner: {r['winner']} | Amount: ${r['amount']}")

print(f'\n❌ LOSING POSITIONS ({len(losers)}):')
for l in losers:
    print(f"  • Market {l['market_id']}: {l['question']}")
    print(f"    Position: {l['position']} | Winner: {l['winner']} | Amount: ${l['amount']}")

# Calculate totals
total_winnings = sum(r['amount'] for r in redeemable)
total_losses = sum(l['amount'] for l in losers)
print(f'\n💰 Total Winnings to Redeem: ${total_winnings:.2f}')
print(f'💸 Total Losses: ${total_losses:.2f}')
