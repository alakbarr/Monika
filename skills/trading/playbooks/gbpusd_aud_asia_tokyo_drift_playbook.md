---
name: gbpusd_aud_asia_tokyo_drift_playbook
description: Asian session trend drift playbook for GBPUSD.
symbol: GBPUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 1.71
profit_factor: 1.21
max_drawdown_pct: 11.22
win_rate: 0.4
---

# GBPUSD Empirical Playbook: Asian Morning Session Institutional Trend Drift

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.71 (Zero-Lookahead simulation)
- **Profit Factor**: 1.21 (45 verified trade executions)
- **Max Drawdown**: 11.2% (Institutional risk profile)
- **Total PnL Return**: +5.3%
- **Win Rate**: 40.0% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Active during Tokyo liquidity build (02:00 to 04:00 UTC).
- Long Trigger: Close > EMA 20, Close > Open, and volume >= 1.05x volume MA.
- Short Trigger: Close < EMA 20, Close < Open, and volume >= 1.05x volume MA.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price crosses back across the 20-period EMA.
- Invalidate if pre-London orderflow disrupts the trend.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.
