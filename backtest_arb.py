#!/usr/bin/env python3
"""
backtest_arb.py — Validate time-decay strategy before risking real money.

HONEST FINDING FROM BACKTESTING:
  The edge requires BOTH:
    1. Real probability in the 0.70-0.97 zone (not already certain)
    2. Market maker pricing that lags real probability by 15%+

  Under rational MM pricing: ~0 trades (no edge — correct)
  Under 30% MM lag (realistic): ~1 trade per 860 windows, ~80% win rate
  Under 50% MM lag (optimistic): ~1 trade per 400 windows, ~87% win rate

  CRITICAL: These win rates assume our log-normal model is correctly
  calibrated. Real validation requires historical Polymarket data.

Run: python3 /root/.openclaw/workspace/backtest_arb.py
  Options: --sweep  (parameter sensitivity sweep)
           --lag 0.35  (test specific MM lag assumption)
"""
import math, random, sys, time

def ncdf(x):
    a1,a2,a3,a4,a5=0.319381530,-0.356563782,1.781477937,-1.821255978,1.330274429
    L=abs(x); K=1/(1+0.2316419*L)
    w=1-(1/math.sqrt(2*math.pi))*math.exp(-L*L/2)*(a1*K+a2*K**2+a3*K**3+a4*K**4+a5*K**5)
    return w if x>=0 else 1-w

def detect(spot, threshold, t_rem, yes_p, no_p, VOL=0.003, FEE=0.02,
           MIN_PROB=0.70, MAX_PROB=0.97, MIN_EDGE=0.12):
    """Mirror of CrossMarketArb.detect_arbitrage — must stay in sync."""
    if not (10 < t_rem <= 90): return None
    if not (0.88 <= yes_p + no_p <= 1.12): return None
    T = t_rem / 60
    try: d = math.log(spot / threshold) / (VOL * math.sqrt(T))
    except: return None
    pa = ncdf(d)
    side = 'YES' if spot > threshold else 'NO'
    mp = yes_p if side == 'YES' else no_p
    p  = pa if side == 'YES' else 1 - pa
    if not (MIN_PROB <= p <= MAX_PROB): return None
    ev = p * (1 - mp) * (1 - FEE) - (1 - p) * mp
    ne = ev / max(mp, 1e-6)
    if ne < MIN_EDGE: return None
    return {'side': side, 'mp': mp, 'p': p, 'ne': ne, 'd': d, 'cushion': spot - threshold, 't': t_rem}

def kelly(p, mp, bankroll):
    b = (1 - mp) / max(mp, 1e-6)
    k = max(0, (p * b - (1 - p)) / max(b, 1e-6)) / 2
    amt = min(bankroll * k, bankroll * 0.05, 5.0)
    return max(1.0, round(amt, 2)) if amt >= 1.0 else 0.0

def run_sim(lag_fraction=0.35, n_windows=50000, seed=42, bankroll=56.71):
    """
    lag_fraction: how much MM price is based on stale data.
      0.0 = fully rational MM (no trades possible)
      0.3 = updates every ~30s (realistic liquid market)
      0.5 = updates every ~60s (less liquid)
    """
    random.seed(seed)
    VOL = 0.003
    thresholds = [60000, 62000, 65000, 66000, 67000, 68000, 69000, 70000, 72000, 75000]
    trades = []; balance = bankroll; peak = bankroll; max_dd = 0.0

    for _ in range(n_windows):
        threshold  = random.choice(thresholds)
        spot_0     = threshold * random.uniform(0.90, 1.10)
        elapsed    = random.uniform(0.0, 4.8)
        t_rem      = max(0.0, (5.0 - elapsed) * 60)
        spot_now   = spot_0 * math.exp(VOL * math.sqrt(elapsed) * random.gauss(0, 1))

        T_cur   = t_rem / 60.0
        T_stale = (t_rem + 60) / 60.0
        spot_stale = spot_now * math.exp(-VOL * math.sqrt(1.0) * random.gauss(0, 1) * 0.8)

        rc = ncdf(math.log(spot_now   / threshold) / (VOL * math.sqrt(max(T_cur,   0.001))))
        rs = ncdf(math.log(spot_stale / threshold) / (VOL * math.sqrt(max(T_stale, 0.001))))

        mm_yes = (1 - lag_fraction) * rc + lag_fraction * rs + random.gauss(0, 0.02)
        yes_p  = max(0.05, min(0.95, mm_yes))
        no_p   = max(0.05, min(0.95, 1 - mm_yes + random.gauss(0, 0.01)))

        sig = detect(spot_now, threshold, t_rem, yes_p, no_p)
        if sig is None: continue

        amt = kelly(sig['p'], sig['mp'], balance)
        if amt < 1.0 or balance < amt: continue

        # Simulate outcome (independent of detection model)
        spot_fin = spot_now * math.exp(VOL * math.sqrt(t_rem / 60) * random.gauss(0, 1))
        res_yes  = spot_fin > threshold
        won = (res_yes and sig['side'] == 'YES') or (not res_yes and sig['side'] == 'NO')
        pnl = amt * (1 / sig['mp'] - 1) * 0.98 if won else -amt

        balance += pnl
        peak     = max(peak, balance)
        max_dd   = max(max_dd, (peak - balance) / max(peak, 1))
        trades.append({'won': won, 'pnl': pnl, 'ne': sig['ne'], 'd': sig['d'],
                       't': sig['t'], 'mp': sig['mp'], 'p': sig['p'], 'amt': amt})
        if balance < bankroll * 0.40: break  # ruin stop

    return trades, balance, max_dd

def report(trades, final_balance, max_dd, bankroll=56.71, lag=0.35, n_windows=50000):
    n   = len(trades)
    roi = (final_balance - bankroll) / bankroll
    print("=" * 65)
    print("  BACKTEST REPORT — Time-Decay Arbitrage Strategy")
    print(f"  MM lag assumption: {lag:.0%}  |  Windows scanned: {n_windows:,}")
    print("=" * 65)
    print(f"  Trades taken:    {n}  ({n/n_windows*1000:.1f} per 1,000 windows)")
    if n == 0:
        print("\n  ❌ Zero trades. MM may be too rational for this parameter set.")
        print("     Try: --lag 0.40  or check MIN_PROB/MAX_PROB/MIN_EDGE params")
        return

    wr  = sum(1 for t in trades if t['won']) / n
    pnl = sum(t['pnl'] for t in trades)
    se  = math.sqrt(wr * (1 - wr) / n)
    ci  = 1.96 * se

    print(f"  Win rate:        {wr:.1%}   95% CI [{wr-ci:.1%} – {wr+ci:.1%}]")
    print(f"  Net P&L:         ${pnl:+.2f}  ({roi:+.1%})")
    print(f"  Final balance:   ${final_balance:.2f}")
    print(f"  Max drawdown:    {max_dd:.1%}")
    print()
    print(f"  Signal stats:")
    print(f"    Avg d-stat:    {sum(t['d'] for t in trades)/n:.2f}  (>1.5 = meaningful)")
    print(f"    Avg net edge:  {sum(t['ne'] for t in trades)/n:.1%}")
    print(f"    Avg real prob: {sum(t['p'] for t in trades)/n:.3f}")
    print(f"    Avg mkt price: {sum(t['mp'] for t in trades)/n:.3f}")
    print(f"    Prob-mkt gap:  {sum(t['p']-t['mp'] for t in trades)/n:+.3f}")
    print(f"    Avg time:      {sum(t['t'] for t in trades)/n:.1f}s remaining")
    print(f"    Avg bet:       ${sum(t['amt'] for t in trades)/n:.2f}")

    print()
    print("  VERDICT:")
    flags = []
    if n < 100:
        flags.append(f"⚠️  Small sample ({n} trades) — CI wide, results not conclusive")
    if wr < 0.54:
        flags.append(f"🔴 Win rate {wr:.1%} below fee break-even — do not trade live")
    elif wr < 0.57:
        flags.append(f"🟡 Win rate {wr:.1%} marginal — barely beats fees")
    else:
        flags.append(f"🟢 Win rate {wr:.1%} above 57% target")
    if max_dd > 0.25:
        flags.append(f"🔴 Drawdown {max_dd:.1%} too high")
    else:
        flags.append(f"🟢 Drawdown {max_dd:.1%} acceptable")
    if pnl < 0:
        flags.append(f"🔴 Net negative — do not trade live")
    else:
        flags.append(f"🟢 Net positive ${pnl:+.2f}")

    for f in flags: print(f"    {f}")

    ready = all(not f.startswith("🔴") for f in flags) and n >= 50
    print()
    if ready:
        print("  ✅ SIMULATION: GO (under these assumptions)")
        print()
        print("  BEFORE going live — required real data validation:")
        print("    1. Pull Binance 1m KLINES (free, no auth):")
        print("       curl 'https://api.binance.com/api/v3/klines?symbol=BTCUSDT")
        print("             &interval=1m&limit=1500' > btc_klines.json")
        print("    2. Match to known Polymarket window resolutions")
        print("    3. Replay detect() on real prices vs real resolutions")
        print("    4. Need ≥250 real events, ≥56% win rate before live")
    else:
        print("  ❌ DO NOT TRADE REAL MONEY")
        print("     Tune parameters or lower MM lag assumption")

    print()
    print("  CALIBRATION NOTE:")
    print(f"    This assumes MM is {lag:.0%} stale (prices off real prob by ~{lag*15:.0f}pp).")
    print("    Real Polymarket BTC 5-min markets: unknown — validate with real data.")
    print("    Conservative assumption: 20-30% lag. Optimistic: 40-50%.")

def sweep():
    print("\n" + "=" * 65)
    print("  PARAMETER SENSITIVITY (30,000 windows each, lag=0.35)")
    print("=" * 65)
    print(f"  {'MinProb':>8} {'MaxProb':>8} {'MinEdge':>8} | {'Trades':>7} {'WinRate':>9} {'P&L':>9}")
    print("  " + "-" * 58)
    for min_prob in [0.65, 0.70, 0.75]:
        for max_prob in [0.92, 0.97]:
            for min_edge in [0.08, 0.12]:
                # Quick run with modified params
                random.seed(42)
                VOL=0.003; thresholds=[65000,67000,68000,69000,70000]
                ts=[]; bal=56.71; lag=0.35
                for _ in range(30000):
                    th=random.choice(thresholds)
                    s0=th*random.uniform(0.90,1.10); el=random.uniform(0,4.8)
                    tr=max(0,(5-el)*60)
                    sn=s0*math.exp(VOL*math.sqrt(el)*random.gauss(0,1))
                    Tc=tr/60; Ts=(tr+60)/60
                    ss=sn*math.exp(-VOL*math.sqrt(1)*random.gauss(0,1)*0.8)
                    rc=ncdf(math.log(sn/th)/(VOL*math.sqrt(max(Tc,0.001))))
                    rs_=ncdf(math.log(ss/th)/(VOL*math.sqrt(max(Ts,0.001))))
                    mm=(1-lag)*rc+lag*rs_+random.gauss(0,0.02)
                    yp=max(0.05,min(0.95,mm)); np_=max(0.05,min(0.95,1-mm+random.gauss(0,0.01)))
                    sig=detect(sn,th,tr,yp,np_,MIN_PROB=min_prob,MAX_PROB=max_prob,MIN_EDGE=min_edge)
                    if sig is None: continue
                    amt=kelly(sig['p'],sig['mp'],bal)
                    if amt<1 or bal<amt: continue
                    sf=sn*math.exp(VOL*math.sqrt(tr/60)*random.gauss(0,1))
                    ry=sf>th; w=(ry and sig['side']=='YES') or (not ry and sig['side']=='NO')
                    p_=amt*(1/sig['mp']-1)*0.98 if w else -amt
                    bal+=p_; ts.append({'won':w,'pnl':p_})
                    if bal<20: break
                nt=len(ts)
                wr=sum(1 for t in ts if t['won'])/max(nt,1)
                pnl=sum(t['pnl'] for t in ts)
                fl="🟢" if wr>=0.56 and pnl>0 and nt>=20 else ("🟡" if wr>=0.53 else "🔴")
                print(f"  {min_prob:>8.2f} {max_prob:>8.2f} {min_edge:>8.0%} | {nt:>7} {wr:>9.1%} {pnl:>+9.2f}  {fl}")
    print()

if __name__ == '__main__':
    lag = 0.35
    do_sweep = '--sweep' in sys.argv
    for i, arg in enumerate(sys.argv):
        if arg == '--lag' and i+1 < len(sys.argv):
            lag = float(sys.argv[i+1])

    N = 50000
    print(f"Running Monte Carlo ({N:,} windows, MM lag={lag:.0%})...")
    t0 = time.time()
    trades, final_bal, max_dd = run_sim(lag_fraction=lag, n_windows=N)
    report(trades, final_bal, max_dd, lag=lag, n_windows=N)
    print(f"\n  Simulation time: {time.time()-t0:.1f}s")

    if do_sweep:
        sweep()
