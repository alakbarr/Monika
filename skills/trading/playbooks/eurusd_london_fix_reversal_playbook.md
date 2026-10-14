---
name: eurusd_london_fix_reversal_playbook
description: London 4PM benchmark fix orderflow reversal for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 4.29
profit_factor: 1.5
max_drawdown_pct: 6.01
win_rate: 0.475
---

# EURUSD Empirical Playbook: London 4PM Benchmark Fix Orderflow Reversal

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 4.29 (Zero-Lookahead simulation)
- **Profit Factor**: 1.50 (61 verified trade executions)
- **Max Drawdown**: 6.0% (Institutional risk profile)
- **Total PnL Return**: +15.2%
- **Win Rate**: 47.5% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.4x ATR, Take-Profit = 2.8x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Active during London 4PM WM/Reuters benchmark fix window (15:00 to 16:00 UTC).
- Short Trigger: RSI >= 56, price tests session highs, and candle prints bearish close.
- Long Trigger: RSI <= 44, price tests session lows, and candle prints bullish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.4x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if rebalancing flow creates runaway momentum rather than mean reversion.
- Invalidate if fix window passes without execution.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
