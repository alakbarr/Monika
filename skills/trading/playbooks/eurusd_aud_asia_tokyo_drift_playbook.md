---
name: eurusd_aud_asia_tokyo_drift_playbook
description: Asian session trend drift playbook for EURUSD.
symbol: EURUSD
regime: trending
timeframe: H1
min_rr: 1.5
status: active
sharpe_ratio: 2.35
profit_factor: 1.14
max_drawdown_pct: 3.26
win_rate: 0.452
---

# EURUSD Empirical Playbook: Asian Morning Session Institutional Trend Drift

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.35 (Zero-Lookahead simulation)
- **Profit Factor**: 1.14 (31 verified trade executions)
- **Max Drawdown**: 3.3% (Institutional risk profile)
- **Total PnL Return**: +2.3%
- **Win Rate**: 45.2% (Normalized at minimum 1:1.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 1.5x ATR, Max Holding = 12 bars

## Trigger Conditions & Tactical Directives
- Active during Tokyo liquidity build (02:00 to 04:00 UTC).
- Long Trigger: Close > EMA 20, Close > Open, and volume >= 1.05x volume MA.
- Short Trigger: Close < EMA 20, Close < Open, and volume >= 1.05x volume MA.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price crosses back across the 20-period EMA.
- Invalidate if pre-London orderflow disrupts the trend.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 12 bars.
