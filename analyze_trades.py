#!/usr/bin/env python3
"""
analyze_trades.py — Parse v6 bot log and calculate P&L
Run on OpenClaw: python /root/.openclaw/workspace/analyze_trades.py
Output: /root/.openclaw/workspace/manual_pnl_analysis.json
"""

import re
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

LOG_FILE  = '/root/.openclaw/workspace/v6_bot_output.log'
OUT_FILE  = '/root/.openclaw/workspace/manual_pnl_analysis.json'
PM_FEE    = 0.02   # 2% Polymarket fee on winnings

# ── Win rate assumptions when no exit log found ───────────────────────────────
def assumed_win_rate(edge_pct: float) -> float:
    if edge_pct >= 30: return 0.70
    if edge_pct >= 15: return 0.55
    return 0.45

# ── Regex patterns ────────────────────────────────────────────────────────────
# Entry line:  ARB SIGNAL: BTC/5m YES @ 0.505 | spread=-0.443 edge=44.3% size=$5.00
ENTRY_RE = re.compile(
    r'(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'
    r'.*?ARB SIGNAL.*?(?P<coin>BTC|ETH|SOL|XRP)/(?P<tf>\d+m)\s+'
    r'(?P<side>YES|NO)\s+@\s+(?P<price>[\d.]+)'
    r'.*?edge=(?P<edge>[\d.]+)%'
    r'.*?size=\$(?P<size>[\d.]+)'
)

# Exit line:  EXIT BTC-5m | stop_loss | PnL -22.3%
EXIT_RE = re.compile(
    r'(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'
    r'.*?EXIT\s+(?P<market>[\w\-]+)'
    r'.*?(?P<reason>stop_loss|take_profit|trailing_stop|time_stop|resolved)'
    r'.*?PnL\s+(?P<pnl>[+-]?[\d.]+)%'
)

# Resolution line:  RESOLVED BTC-5m winner=YES
RESOLVED_RE = re.compile(
    r'(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'
    r'.*?(?:RESOLVED|resolved).*?(?P<market>[\w\-]+)'
    r'.*?winner[=:]\s*(?P<winner>YES|NO)'
)

# ── Parse log ─────────────────────────────────────────────────────────────────
def parse_log(path: str):
    entries    = []      # list of entry dicts
    exits      = {}      # market_key → exit dict (first match wins per market)
    resolutions = {}     # market_key → winner string

    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"ERROR: Log file not found: {path}")
        sys.exit(1)

    print(f"Scanning {len(lines):,} log lines...")

    for line in lines:
        m = ENTRY_RE.search(line)
        if m:
            entries.append({
                'ts':     m.group('ts'),
                'coin':   m.group('coin'),
                'tf':     m.group('tf'),
                'market': f"{m.group('coin')}-{m.group('tf')}",
                'side':   m.group('side'),
                'price':  float(m.group('price')),
                'edge':   float(m.group('edge')),
                'size':   float(m.group('size')),
            })
            continue

        m = EXIT_RE.search(line)
        if m:
            key = m.group('market').upper()
            if key not in exits:
                exits[key] = {
                    'ts':     m.group('ts'),
                    'reason': m.group('reason'),
                    'pnl_pct': float(m.group('pnl')),
                }
            continue

        m = RESOLVED_RE.search(line)
        if m:
            key = m.group('market').upper()
            resolutions[key] = m.group('winner')

    print(f"Found: {len(entries)} entries, {len(exits)} exits, {len(resolutions)} resolutions")
    return entries, exits, resolutions

# ── Calculate P&L per trade ───────────────────────────────────────────────────
def calculate_pnl(entries, exits, resolutions):
    trades     = []
    trade_num  = defaultdict(int)   # market → count (for unique IDs)

    for e in entries:
        market = e['market'].upper()
        trade_num[market] += 1
        trade_id = f"{market}-{trade_num[market]:03d}"

        price  = e['price']
        size   = e['size']
        side   = e['side']
        edge   = e['edge']

        # ── Determine outcome ─────────────────────────────────────────────────
        source = 'assumed'
        won    = None

        if market in resolutions:
            winner = resolutions[market]
            won    = (side == winner)
            source = 'resolved'

        elif market in exits:
            ex     = exits[market]
            won    = ex['pnl_pct'] > 0
            source = f"exit:{ex['reason']}"

        else:
            # No exit data — use assumed win rate
            import random
            random.seed(hash(trade_id))   # deterministic per trade
            wr  = assumed_win_rate(edge)
            won = random.random() < wr
            source = f'assumed_wr={wr:.0%}'

        # ── P&L formula ───────────────────────────────────────────────────────
        # WIN:  profit = size × (1 - entry_price) × (1 - fee)
        # LOSS: loss   = size × entry_price   [you lose your stake on the side you bought]
        if won:
            gross   = size * (1.0 - price)
            fee     = gross * PM_FEE
            net_pnl = gross - fee
        else:
            gross   = -size * price
            fee     = 0.0
            net_pnl = gross

        trades.append({
            'trade_id':    trade_id,
            'timestamp':   e['ts'],
            'market':      market,
            'coin':        e['coin'],
            'tf':          e['tf'],
            'side':        side,
            'entry_price': price,
            'edge_pct':    edge,
            'size_usd':    size,
            'outcome':     'WIN' if won else 'LOSS',
            'gross_pnl':   round(gross, 6),
            'fee':         round(fee, 6),
            'net_pnl':     round(net_pnl, 6),
            'pnl_pct':     round(net_pnl / size * 100, 2) if size else 0,
            'source':      source,
        })

    return trades

# ── Summary stats ─────────────────────────────────────────────────────────────
def build_summary(trades):
    total  = len(trades)
    wins   = [t for t in trades if t['outcome'] == 'WIN']
    losses = [t for t in trades if t['outcome'] == 'LOSS']

    net_pnl   = sum(t['net_pnl']  for t in trades)
    gross_pnl = sum(t['gross_pnl'] for t in trades)
    fees      = sum(t['fee']       for t in trades)
    win_rate  = len(wins) / total if total else 0

    best  = max(trades, key=lambda t: t['net_pnl'])
    worst = min(trades, key=lambda t: t['net_pnl'])

    # By coin
    by_coin = defaultdict(lambda: {'trades': 0, 'wins': 0, 'net_pnl': 0.0, 'total_size': 0.0})
    for t in trades:
        c = t['coin']
        by_coin[c]['trades']     += 1
        by_coin[c]['wins']       += 1 if t['outcome'] == 'WIN' else 0
        by_coin[c]['net_pnl']    += t['net_pnl']
        by_coin[c]['total_size'] += t['size_usd']
    for c in by_coin:
        n = by_coin[c]['trades']
        by_coin[c]['win_rate'] = round(by_coin[c]['wins'] / n, 4) if n else 0
        by_coin[c]['net_pnl']  = round(by_coin[c]['net_pnl'], 4)
        by_coin[c]['roi_pct']  = round(
            by_coin[c]['net_pnl'] / by_coin[c]['total_size'] * 100, 2
        ) if by_coin[c]['total_size'] else 0

    # By edge bucket
    buckets = {'edge_5_15': [], 'edge_15_30': [], 'edge_30_plus': []}
    for t in trades:
        if t['edge_pct'] >= 30:    buckets['edge_30_plus'].append(t)
        elif t['edge_pct'] >= 15:  buckets['edge_15_30'].append(t)
        else:                      buckets['edge_5_15'].append(t)

    by_edge = {}
    for bucket, ts in buckets.items():
        if ts:
            by_edge[bucket] = {
                'trades':   len(ts),
                'win_rate': round(sum(1 for t in ts if t['outcome']=='WIN') / len(ts), 4),
                'net_pnl':  round(sum(t['net_pnl'] for t in ts), 4),
                'avg_pnl':  round(sum(t['net_pnl'] for t in ts) / len(ts), 4),
            }

    # Source breakdown (how many trades were assumed vs confirmed)
    sources = defaultdict(int)
    for t in trades:
        src = 'confirmed' if t['source'] in ('resolved',) or t['source'].startswith('exit:') else 'assumed'
        sources[src] += 1

    total_size = sum(t['size_usd'] for t in trades)

    return {
        'total_trades':      total,
        'wins':              len(wins),
        'losses':            len(losses),
        'win_rate':          round(win_rate, 4),
        'net_pnl':           round(net_pnl, 4),
        'gross_pnl':         round(gross_pnl, 4),
        'fees_paid':         round(fees, 4),
        'total_size_wagered': round(total_size, 2),
        'roi_pct':           round(net_pnl / total_size * 100, 2) if total_size else 0,
        'avg_pnl_per_trade': round(net_pnl / total, 4) if total else 0,
        'best_trade':        {'id': best['trade_id'],  'net_pnl': best['net_pnl'],
                              'edge': best['edge_pct'], 'market': best['market']},
        'worst_trade':       {'id': worst['trade_id'], 'net_pnl': worst['net_pnl'],
                              'edge': worst['edge_pct'], 'market': worst['market']},
        'by_coin':           {k: dict(v) for k, v in by_coin.items()},
        'by_edge_bucket':    by_edge,
        'outcome_source':    dict(sources),
        'note':              (
            'WARNING: trades marked assumed_wr used statistical win rates, '
            'not actual outcomes. Integrate pnl_tracker.py for exact results.'
            if sources.get('assumed', 0) > 0 else
            'All outcomes confirmed from log data.'
        ),
    }

# ── Print to terminal ─────────────────────────────────────────────────────────
def print_report(summary, trades):
    print("\n" + "=" * 60)
    print("  P&L ANALYSIS REPORT")
    print("=" * 60)
    print(f"  Total trades     : {summary['total_trades']}")
    print(f"  Wins / Losses    : {summary['wins']} / {summary['losses']}")
    print(f"  Win rate         : {summary['win_rate']:.1%}")
    print(f"  Net P&L          : ${summary['net_pnl']:+.4f}")
    print(f"  ROI              : {summary['roi_pct']:+.2f}%")
    print(f"  Avg per trade    : ${summary['avg_pnl_per_trade']:+.4f}")
    print(f"  Total wagered    : ${summary['total_size_wagered']:.2f}")
    print(f"  Fees paid        : ${summary['fees_paid']:.4f}")
    print(f"\n  Best trade  : {summary['best_trade']['id']}  ${summary['best_trade']['net_pnl']:+.4f}  edge={summary['best_trade']['edge']:.1f}%")
    print(f"  Worst trade : {summary['worst_trade']['id']}  ${summary['worst_trade']['net_pnl']:+.4f}  edge={summary['worst_trade']['edge']:.1f}%")

    print("\n  By Coin:")
    for coin, d in summary['by_coin'].items():
        print(f"    {coin:4s}  trades={d['trades']:3d}  WR={d['win_rate']:.1%}  "
              f"net=${d['net_pnl']:+.4f}  ROI={d['roi_pct']:+.2f}%")

    print("\n  By Edge Bucket:")
    for bucket, d in summary['by_edge_bucket'].items():
        label = bucket.replace('_', ' ').replace('edge ', 'edge=')
        print(f"    {label:15s}  trades={d['trades']:3d}  WR={d['win_rate']:.1%}  "
              f"avg_pnl=${d['avg_pnl']:+.4f}  total=${d['net_pnl']:+.4f}")

    src = summary['outcome_source']
    print(f"\n  Data quality: {src.get('confirmed',0)} confirmed exits, "
          f"{src.get('assumed',0)} assumed (statistical)")
    if src.get('assumed', 0) > 0:
        print("  ⚠️  Assumed trades use statistical win rates — not exact.")
        print("     Integrate pnl_tracker.py for precise tracking.")

    print(f"\n  Full data → {OUT_FILE}")
    print("=" * 60)

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    log_path = sys.argv[1] if len(sys.argv) > 1 else LOG_FILE

    entries, exits, resolutions = parse_log(log_path)

    if not entries:
        print("No trade entries found. Check log format matches:")
        print("  'ARB SIGNAL: BTC/5m YES @ 0.505 | ... edge=44.3% size=$5.00'")
        sys.exit(1)

    trades  = calculate_pnl(entries, exits, resolutions)
    summary = build_summary(trades)

    output  = {'summary': summary, 'trades': trades}
    tmp     = OUT_FILE + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(output, f, indent=2)
    Path(tmp).replace(OUT_FILE)

    print_report(summary, trades)
    print(f"\nSaved {len(trades)} trades to {OUT_FILE}")
