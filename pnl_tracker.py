#!/usr/bin/env python3
"""
pnl_tracker.py — P&L Tracking for Master Bot v6
Drop into /root/.openclaw/workspace/

Tracks: trade entry → resolution → win/loss → cumulative P&L + win rate

INTEGRATION (4 changes in master_bot_v6 / cross_market_arb):

  1. Import:
       from pnl_tracker import PnLTracker

  2. Init in MasterBot.__init__():
       self.pnl_tracker = PnLTracker()

  3. On trade entry — add to _execute_arb() after position is created:
       self.bot.pnl_tracker.record_entry(
           trade_id   = market_key,
           market_id  = market_key,
           side       = side,
           entry_price= fill_price,
           shares     = filled_size,
           amount_usd = amount,
           coin       = coin,
           strategy   = 'ARB',
           spread     = opportunity.get('spread', 0),
           edge       = opportunity.get('edge', 0),
       )

  4. On trade exit — add to _execute_exit() before _save_state():
       self.pnl_tracker.record_exit(
           trade_id   = pos.market_id,
           exit_price = cp,
           exit_reason= reason.value,
       )

  Output files (workspace):
    pnl_trades.json     — every trade with full entry+exit data
    pnl_summary.json    — rolling summary: win rate, P&L, by strategy/coin
"""

import json
import time
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List
from collections import defaultdict

log = logging.getLogger('pnl_tracker')

WORKSPACE       = '/root/.openclaw/workspace'
TRADES_FILE     = f'{WORKSPACE}/pnl_trades.json'
SUMMARY_FILE    = f'{WORKSPACE}/pnl_summary.json'

# Polymarket charges 2% fee on winnings
POLYMARKET_FEE  = 0.02


class TradeRecord:
    """Single trade lifecycle: entry → exit → outcome."""

    def __init__(
        self,
        trade_id:    str,
        market_id:   str,
        side:        str,
        entry_price: float,
        shares:      float,
        amount_usd:  float,
        coin:        str        = '',
        strategy:    str        = 'ARB',
        spread:      float      = 0.0,
        edge:        float      = 0.0,
    ):
        self.trade_id    = trade_id
        self.market_id   = market_id
        self.side        = side
        self.entry_price = entry_price
        self.shares      = shares
        self.amount_usd  = amount_usd
        self.coin        = coin.upper()
        self.strategy    = strategy
        self.spread      = spread
        self.edge        = edge

        self.entry_time  = time.time()
        self.entry_ts    = datetime.now(tz=timezone.utc).isoformat()

        # Exit fields — populated on close
        self.exit_price  : Optional[float] = None
        self.exit_reason : str             = ''
        self.exit_time   : Optional[float] = None
        self.exit_ts     : Optional[str]   = None

        # Outcome
        self.status      : str             = 'open'   # open | won | lost
        self.gross_pnl   : float           = 0.0
        self.fee         : float           = 0.0
        self.net_pnl     : float           = 0.0
        self.pnl_pct     : float           = 0.0
        self.hold_secs   : float           = 0.0

    def close(self, exit_price: float, exit_reason: str):
        self.exit_price  = exit_price
        self.exit_reason = exit_reason
        self.exit_time   = time.time()
        self.exit_ts     = datetime.now(tz=timezone.utc).isoformat()
        self.hold_secs   = self.exit_time - self.entry_time

        # Gross P&L: (exit - entry) * shares
        # On Polymarket binary markets:
        #   WIN  → exit_price = 1.0, gross = (1.0 - entry) * shares
        #   LOSS → exit_price = 0.0, gross = (0.0 - entry) * shares = -amount_usd
        # [FIX-1] Binary market P&L — NOT a stock spread formula
        # WIN:  you paid entry_price per share, collect $1.00 per share
        # LOSS: you lose your entry_price stake per share
        # exit_price is 1.0 (win) or 0.0 (loss) from resolution
        if exit_price >= 0.99:  # resolved YES / winning side
            self.gross_pnl = (1.0 - self.entry_price) * self.shares
        elif exit_price <= 0.01:  # resolved NO / losing side
            self.gross_pnl = -self.entry_price * self.shares
        else:
            # Mid-market early exit — use spread formula
            self.gross_pnl = (exit_price - self.entry_price) * self.shares
        # Safety: if shares=0 (not recorded), fall back to amount_usd basis
        if self.shares == 0 and self.amount_usd > 0 and self.entry_price > 0:
            estimated_shares = self.amount_usd / self.entry_price
            if exit_price >= 0.99:
                self.gross_pnl = (1.0 - self.entry_price) * estimated_shares
            else:
                self.gross_pnl = -self.entry_price * estimated_shares
            import logging as _log
            _log.getLogger(__name__).warning(
                f"[PnL] shares=0 for {getattr(self, 'trade_id', '?')} — "
                f"estimated {estimated_shares:.2f} shares from ${self.amount_usd:.2f}"
            )

        # Fee: 2% of winnings only
        self.fee = self.gross_pnl * POLYMARKET_FEE if self.gross_pnl > 0 else 0.0

        self.net_pnl = self.gross_pnl - self.fee
        self.pnl_pct = (self.net_pnl / self.amount_usd * 100) if self.amount_usd > 0 else 0.0
        self.status  = 'won' if self.net_pnl > 0 else 'lost'

    def to_dict(self) -> dict:
        return {
            'trade_id':    self.trade_id,
            'market_id':   self.market_id,
            'coin':        self.coin,
            'side':        self.side,
            'strategy':    self.strategy,
            'status':      self.status,

            'entry_price': round(self.entry_price, 5),
            'entry_ts':    self.entry_ts,
            'exit_price':  round(self.exit_price, 5) if self.exit_price is not None else None,
            'exit_ts':     self.exit_ts,
            'exit_reason': self.exit_reason,

            'shares':      round(self.shares, 6),
            'amount_usd':  round(self.amount_usd, 4),
            'gross_pnl':   round(self.gross_pnl, 6),
            'fee':         round(self.fee, 6),
            'net_pnl':     round(self.net_pnl, 6),
            'pnl_pct':     round(self.pnl_pct, 4),
            'hold_secs':   round(self.hold_secs, 1),

            'edge':        round(self.edge, 4),
            'spread':      round(self.spread, 4),
        }


class PnLTracker:
    """
    Thread-safe P&L tracker.
    Call record_entry() on open, record_exit() on close.
    Writes pnl_trades.json and pnl_summary.json after every exit.
    """

    def __init__(self):
        self._lock   = threading.Lock()
        self._trades : Dict[str, TradeRecord] = {}   # trade_id → record
        self._closed : List[dict]             = []   # completed trade dicts
        self._load_existing()
        log.info(f"[PnL] Tracker ready — {len(self._closed)} historical trades loaded")

    # ── Public API ────────────────────────────────────────────────────────────

    def record_entry(
        self,
        trade_id:    str,
        market_id:   str,
        side:        str,
        entry_price: float,
        shares:      float,
        amount_usd:  float,
        coin:        str   = '',
        strategy:    str   = 'ARB',
        spread:      float = 0.0,
        edge:        float = 0.0,
    ):
        with self._lock:
            if trade_id in self._trades:
                log.debug(f"[PnL] Entry already recorded for {trade_id}")
                return
            self._trades[trade_id] = TradeRecord(
                trade_id=trade_id, market_id=market_id,
                side=side, entry_price=entry_price,
                shares=shares, amount_usd=amount_usd,
                coin=coin, strategy=strategy,
                spread=spread, edge=edge,
            )
        self._persist()  # [FIX-2] persist entry immediately — survives crashes
        log.info(
            f"[PnL] ENTRY {trade_id} | {side}@{entry_price:.4f} "
            f"${amount_usd:.2f} edge={edge:.1%}"
        )

    def record_exit(
        self,
        trade_id:    str,
        exit_price:  float,
        exit_reason: str = '',
    ):
        with self._lock:
            rec = self._trades.pop(trade_id, None)
            # [FIX-3B] Fuzzy match: trade_id stored as "BTC-5m-<slot>" but
            # _execute_exit passes "BTC-5m" — find the most recent open trade
            if rec is None:
                candidates = [
                    (k, v) for k, v in self._trades.items()
                    if k.startswith(trade_id) and v.status == 'open'
                ]
                if candidates:
                    # Take the most recently opened
                    best_key = max(candidates, key=lambda x: x[1].entry_time)[0]
                    rec = self._trades.pop(best_key)
                    log.info(f"[PnL] record_exit: fuzzy match '{trade_id}' → '{best_key}'")
            if rec is None:
                log.warning(f"[PnL] No open trade found for {trade_id} — creating stub")
                # Create minimal stub so we don't lose the exit data
                rec = TradeRecord(
                    trade_id=trade_id, market_id=trade_id,
                    side='?', entry_price=exit_price,
                    shares=0, amount_usd=0,
                )

            rec.close(exit_price, exit_reason)
            self._closed.append(rec.to_dict())

        won = rec.status == 'won'
        log.info(
            f"[PnL] EXIT  {trade_id} | "
            f"{'WIN  ✅' if won else 'LOSS ❌'} | "
            f"net=${rec.net_pnl:+.4f} ({rec.pnl_pct:+.2f}%) | "
            f"hold={rec.hold_secs:.0f}s | reason={exit_reason}"
        )

        self._persist()
        self._write_summary()

    def get_open_trades(self) -> List[dict]:
        with self._lock:
            return [
                {
                    'trade_id':    t.trade_id,
                    'coin':        t.coin,
                    'side':        t.side,
                    'entry_price': t.entry_price,
                    'amount_usd':  t.amount_usd,
                    'age_secs':    round(time.time() - t.entry_time, 0),
                    'edge':        t.edge,
                }
                for t in self._trades.values()
            ]

    def summary(self) -> dict:
        """Current P&L summary — used by health file."""
        with self._lock:
            closed = list(self._closed)

        if not closed:
            return self._empty_summary()

        total     = len(closed)
        wins      = sum(1 for t in closed if t['status'] == 'won')
        losses    = total - wins
        win_rate  = wins / total if total else 0.0
        net_pnl   = sum(t['net_pnl'] for t in closed)
        gross_pnl = sum(t['gross_pnl'] for t in closed)
        fees_paid = sum(t['fee'] for t in closed)
        avg_hold  = sum(t['hold_secs'] for t in closed) / total if total else 0

        # Last 50 trades rolling win rate
        recent    = closed[-50:]
        recent_wr = sum(1 for t in recent if t['status'] == 'won') / len(recent)

        # By coin
        by_coin: Dict[str, dict] = defaultdict(lambda: {'trades': 0, 'wins': 0, 'net_pnl': 0.0})
        for t in closed:
            c = t.get('coin', 'UNK')
            by_coin[c]['trades']  += 1
            by_coin[c]['wins']    += 1 if t['status'] == 'won' else 0
            by_coin[c]['net_pnl'] += t['net_pnl']
        for c in by_coin:
            n = by_coin[c]['trades']
            by_coin[c]['win_rate'] = round(by_coin[c]['wins'] / n, 4) if n else 0

        # By strategy
        by_strat: Dict[str, dict] = defaultdict(lambda: {'trades': 0, 'wins': 0, 'net_pnl': 0.0})
        for t in closed:
            s = t.get('strategy', 'UNK')
            by_strat[s]['trades']  += 1
            by_strat[s]['wins']    += 1 if t['status'] == 'won' else 0
            by_strat[s]['net_pnl'] += t['net_pnl']

        # Best / worst trade
        best  = max(closed, key=lambda t: t['net_pnl'])
        worst = min(closed, key=lambda t: t['net_pnl'])

        # Open positions value
        with self._lock:
            open_count    = len(self._trades)
            open_exposure = sum(t.amount_usd for t in self._trades.values())

        return {
            'total_trades':    total,
            'open_trades':     open_count,
            'open_exposure':   round(open_exposure, 2),
            'wins':            wins,
            'losses':          losses,
            'win_rate':        round(win_rate, 4),
            'win_rate_last50': round(recent_wr, 4),
            'net_pnl':         round(net_pnl, 4),
            'gross_pnl':       round(gross_pnl, 4),
            'fees_paid':       round(fees_paid, 4),
            'avg_hold_secs':   round(avg_hold, 1),
            'best_trade':      {'id': best['trade_id'],  'net_pnl': round(best['net_pnl'], 4)},
            'worst_trade':     {'id': worst['trade_id'], 'net_pnl': round(worst['net_pnl'], 4)},
            'by_coin':         {k: dict(v) for k, v in by_coin.items()},
            'by_strategy':     {k: dict(v) for k, v in by_strat.items()},
            'last_updated':    datetime.now(tz=timezone.utc).isoformat(),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _empty_summary(self) -> dict:
        return {
            'total_trades': 0, 'open_trades': len(self._trades),
            'wins': 0, 'losses': 0, 'win_rate': 0.0,
            'net_pnl': 0.0, 'fees_paid': 0.0,
            'last_updated': datetime.now(tz=timezone.utc).isoformat(),
        }

    def _persist(self):
        """Append-safe atomic write to pnl_trades.json."""
        with self._lock:
            data = list(self._closed)
        self._atomic_write(data, TRADES_FILE)

    def _write_summary(self):
        s = self.summary()
        self._atomic_write(s, SUMMARY_FILE)

        # Also log a one-liner so it shows in the run log
        log.info(
            f"[PnL] SUMMARY | trades={s['total_trades']} "
            f"WR={s['win_rate']:.1%} (last50={s['win_rate_last50']:.1%}) | "
            f"net_pnl=${s['net_pnl']:+.4f} | open={s['open_trades']}"
        )

    def _load_existing(self):
        """Load historical closed trades from disk on startup."""
        try:
            with open(TRADES_FILE) as f:
                data = json.load(f)
            if isinstance(data, list):
                # Only load closed trades
                self._closed = [t for t in data if t.get('status') in ('won', 'lost')]
                log.info(f"[PnL] Loaded {len(self._closed)} closed trades from disk")
        except (FileNotFoundError, json.JSONDecodeError):
            self._closed = []

    @staticmethod
    def _atomic_write(data, path: str):
        tmp = path + '.tmp'
        try:
            with open(tmp, 'w') as f:
                json.dump(data, f, indent=2)
            Path(tmp).replace(path)
        except Exception as e:
            log.error(f"[PnL] Write failed {path}: {e}")


# ── Standalone diagnostic: run directly to check existing trade logs ──────────

if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    print("=" * 60)
    print("  PnL Tracker — Diagnostic Mode")
    print("=" * 60)

    tracker = PnLTracker()
    s = tracker.summary()

    if s['total_trades'] == 0:
        print("\n  No closed trades found in pnl_trades.json")
        print("  → Integrate tracker into bot and run for one full cycle")
        print(f"  → Open trades loaded: {s.get('open_trades', 0)}")
        sys.exit(0)

    print(f"\n  Total closed trades : {s['total_trades']}")
    print(f"  Wins / Losses       : {s['wins']} / {s['losses']}")
    print(f"  Win rate            : {s['win_rate']:.1%}  (last 50: {s['win_rate_last50']:.1%})")
    print(f"  Net P&L             : ${s['net_pnl']:+.4f}")
    print(f"  Gross P&L           : ${s['gross_pnl']:.4f}")
    print(f"  Fees paid           : ${s['fees_paid']:.4f}")
    print(f"  Avg hold time       : {s['avg_hold_secs']:.0f}s")
    print(f"  Open trades         : {s['open_trades']} (${s['open_exposure']:.2f} exposure)")

    if s.get('by_coin'):
        print("\n  By Coin:")
        for coin, d in s['by_coin'].items():
            print(f"    {coin:4s}  trades={d['trades']:3d}  WR={d['win_rate']:.1%}  net=${d['net_pnl']:+.4f}")

    if s.get('best_trade'):
        print(f"\n  Best trade  : {s['best_trade']['id']}  ${s['best_trade']['net_pnl']:+.4f}")
        print(f"  Worst trade : {s['worst_trade']['id']}  ${s['worst_trade']['net_pnl']:+.4f}")

    print("=" * 60)
