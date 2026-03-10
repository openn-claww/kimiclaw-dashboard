import json
from datetime import datetime

with open('/root/.openclaw/workspace/wallet_v4_production.json', 'r') as f:
    wallet = json.load(f)

for trade in wallet.get('trades', []):
    if trade.get('type') == 'EDGE' and trade.get('market') == 'ETH 15m' and 'pnl' not in trade:
        entry = trade['entry_price']
        amount = trade['amount']
        shares = amount / entry
        payout = shares * 1.0
        pnl = payout - amount
        
        trade['exit_price'] = 1.0
        trade['exit_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        trade['pnl'] = round(pnl, 2)
        trade['pnl_percent'] = round((pnl/amount)*100, 2)
        trade['resolution_status'] = 'RESOLVED_WIN'
        
        wallet['bankroll_current'] += payout
        wallet['total_trades'] = wallet.get('total_trades', 0) + 1
        wallet['winning_trades'] = wallet.get('winning_trades', 0) + 1
        wallet['total_pnl'] = wallet.get('total_pnl', 0) + pnl
        
        print(f'WIN: +${pnl:.2f} | Balance: ${wallet["bankroll_current"]:.2f}')
        break

with open('/root/.openclaw/workspace/wallet_v4_production.json', 'w') as f:
    json.dump(wallet, f, indent=2)
print('Done')
