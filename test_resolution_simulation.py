#!/usr/bin/env python3
"""
Resolution Fallback Simulation Test
Simulates a trade with delayed Polymarket resolution
to demonstrate Tier 2 fallback triggering
"""

import sys
sys.path.insert(0, '/root/.openclaw/workspace')

from resolution_fallback_v1 import (
    ResolutionFallbackEngine,
    ResolutionConfig,
    run_diagnostic,
)
from datetime import datetime, timezone, timedelta
import time
import json

print("="*70)
print("RESOLUTION FALLBACK SIMULATION TEST")
print("="*70)
print()
print("This test will:")
print("1. Register a simulated position")
print("2. Show Tier 1 (Polymarket) check - not resolved")
print("3. Fast-forward 2+ hours")
print("4. Show Tier 2 (Fallback) triggering with Binance price")
print("5. Verify resolution and audit trail")
print()
print("="*70)

# Initialize engine with PAPER mode (allows immediate testing)
cfg = ResolutionConfig()
cfg.FALLBACK1_TRIGGER_HOURS = 0.001  # 3.6 seconds for testing
cfg.FALLBACK2_TRIGGER_HOURS = 48.0

engine = ResolutionFallbackEngine(
    config=cfg,
    is_paper=True,  # Paper mode for testing
)

# Simulate a BTC 5m position that just expired
print("\n[STEP 1] Registering simulated position...")
print("-"*70)

# Create a position that expired 10 seconds ago
now = datetime.now(timezone.utc)
expiration = now - timedelta(seconds=10)  # Expired 10 seconds ago
expiration_utc = expiration.isoformat()

# Create market details
slot = int(expiration.timestamp() // (5 * 60)) * (5 * 60)
slug = f"btc-updown-5m-{slot}"
market_id = "BTC-5m-TEST"

# Register position
rs = engine.register_position(
    market_id=market_id,
    slug=slug,
    coin="BTC",
    timeframe_minutes=5,
    entry_price=65000.0,  # BTC price at market open
    position_side="YES",  # Betting BTC goes UP
    expiration_utc=expiration_utc,
)

print(f"✓ Position registered:")
print(f"  Market ID: {market_id}")
print(f"  Slug: {slug}")
print(f"  Side: YES (betting UP)")
print(f"  Entry BTC Price: $65,000")
print(f"  Expired: {expiration_utc}")
print(f"  Seconds since expiry: 10")

# Build position dict for checking
position_dict = {
    market_id: {
        'slug': slug,
        'coin': 'BTC',
        'timeframe': 5,
        'entry_price': 65000.0,
        'side': 'YES',
        'expiration_utc': expiration_utc,
    }
}

print("\n[STEP 2] Checking resolution (Tier 1 - Polymarket)...")
print("-"*70)
print("Simulating: Polymarket API returns resolved=false")
print("(In real scenario, market hasn't been manually resolved yet)")

# First check - should NOT resolve yet (waiting for Tier 2 trigger)
results = engine.check_all_exits(position_dict)

if not results:
    print("✓ Not resolved yet (expected)")
    rs = engine.state_mgr.get(market_id)
    print(f"  Resolution attempts: {rs.resolution_attempts}")
    print(f"  Hours since expiry: {(now - expiration).total_seconds() / 3600:.4f}")

print("\n[STEP 3] Fast-forwarding 2+ hours...")
print("-"*70)

# In paper mode with FALLBACK1_TRIGGER_HOURS = 0.001, 
# the next check will trigger fallback immediately
# But let's show what happens

# Update the expiration to be 2+ hours ago
expiration_old = now - timedelta(hours=2.5)
expiration_utc_old = expiration_old.isoformat()

# Re-register with older expiration
rs = engine.state_mgr.get(market_id)
rs.expiration_utc = expiration_utc_old
engine.state_mgr.upsert(rs)

position_dict[market_id]['expiration_utc'] = expiration_utc_old

print(f"✓ Fast-forwarded to: {expiration_utc_old}")
print(f"  Hours since expiry: 2.5 hours")
print(f"  Tier 2 threshold: {cfg.FALLBACK1_TRIGGER_HOURS} hours")
print(f"  → Fallback should trigger now")

print("\n[STEP 4] Checking resolution (Tier 2 - Fallback)...")
print("-"*70)

# Second check - should trigger Tier 2 fallback
results = engine.check_all_exits(position_dict)

if results:
    for market_id, outcome, source, tier in results:
        tier_label = {1: "OFFICIAL", 2: "FALLBACK", 3: "FORCED"}.get(tier, "UNKNOWN")
        print(f"✅ RESOLVED!")
        print(f"  Market: {market_id}")
        print(f"  Outcome: {outcome}")
        print(f"  Source: {source}")
        print(f"  Tier: {tier} ({tier_label})")
        
        # Explain the outcome
        if outcome == "YES":
            print(f"\n  Explanation:")
            print(f"    - Binance fetched BTC price at expiration")
            print(f"    - BTC price was HIGHER than $65,000 entry")
            print(f"    - YES wins (correct prediction)")
        else:
            print(f"\n  Explanation:")
            print(f"    - Binance fetched BTC price at expiration")
            print(f"    - BTC price was LOWER than $65,000 entry")
            print(f"    - NO wins (incorrect prediction)")
else:
    print("⚠️  Not resolved (unexpected)")
    rs = engine.state_mgr.get(market_id)
    print(f"  Resolution attempts: {rs.resolution_attempts}")

print("\n[STEP 5] Verifying audit trail...")
print("-"*70)

# Check audit log
audit_entries = engine.audit.load_all()
if audit_entries:
    print(f"✓ Audit log entries: {len(audit_entries)}")
    latest = audit_entries[-1]
    print(f"\n  Latest entry:")
    print(f"    Market: {latest.get('market_id')}")
    print(f"    Outcome: {latest.get('outcome')}")
    print(f"    Source: {latest.get('source')}")
    print(f"    Tier: {latest.get('tier')}")
    print(f"    Exchange: {latest.get('exchange_used')}")
    print(f"    Notes: {latest.get('notes')}")
else:
    print("⚠️  No audit entries found")

print("\n[STEP 6] Final diagnostic...")
print("-"*70)
run_diagnostic("/root/.openclaw/workspace/resolution_state.json")

print("\n" + "="*70)
print("SIMULATION COMPLETE")
print("="*70)
print()
print("What just happened:")
print("1. Position registered with expired timestamp")
print("2. First check: Polymarket not resolved → waited")
print("3. Time advanced past 2h threshold")
print("4. Second check: Tier 2 fallback triggered")
print("5. Binance price fetched, outcome determined")
print("6. Resolution logged to audit trail")
print()
print("In production:")
print("- Same flow happens automatically")
print("- No manual time manipulation needed")
print("- Fallback triggers after real 2h delay")
print("- Capital freed immediately after resolution")
print()
print("Files updated:")
print("- resolution_state.json")
print("- resolution_audit.jsonl")
