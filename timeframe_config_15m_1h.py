# 15m and 1h timeframe configuration for paper trading
# Add these to your bot configuration

TIMEFRAME_CONFIG = {
    "active_timeframes": [15, 60],  # 15m and 1h
    "coins": ["BTC", "ETH", "SOL", "XRP"],
    
    "15m": {
        "enabled": True,
        "velocity_threshold": 0.004,  # 0.4% (higher than 5m)
        "min_edge": 0.04,
        "max_positions": 2,  # Limit concurrent positions
        "cooldown_minutes": 5,  # Wait between trades
        "max_trade_size": 1.00,  # Max $1 per trade
    },
    
    "1h": {
        "enabled": True,
        "velocity_threshold": 0.006,  # 0.6% (higher for 1h)
        "min_edge": 0.05,
        "max_positions": 1,
        "cooldown_minutes": 10,
        "max_trade_size": 2.00,  # Can trade bigger on 1h
    },
    
    # Mean reversion settings (new strategy)
    "mean_reversion": {
        "enabled": True,
        "rsi_period": 14,
        "rsi_oversold": 30,
        "rsi_overbought": 70,
        "bb_period": 20,
        "bb_std_dev": 2,
        "timeframes": [15, 60, 240],  # 15m, 1h, 4h
    },
    
    # Bond buying strategy (new)
    "bond_buying": {
        "enabled": True,
        "min_probability": 0.90,  # Only buy 90%+ positions
        "max_probability": 0.98,
        "time_to_resolution_min": 60,  # At least 1 hour
        "time_to_resolution_max": 1440,  # Max 24 hours
        "timeframes": [60, 240, 1440],  # 1h, 4h, 1d
    },
    
    # Paper trading settings
    "paper_trading": {
        "enabled": True,
        "virtual_bankroll": 56.71,
        "hard_floor": 50.00,
        "max_daily_loss": 2.00,
        "max_consecutive_losses": 3,
    },
    
    # Reporting
    "reporting": {
        "log_trades": True,
        "report_interval_minutes": 60,
        "track_metrics": ["win_rate", "profit_factor", "sharpe", "max_drawdown"],
    }
}
