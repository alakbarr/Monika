---
name: gbpusd_vwap_mean_reversion_playbook
description: Daily VWAP extreme stretch mean reversion for GBPUSD.
symbol: GBPUSD
regime: mean_reverting
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: 1.03
profit_factor: 1.12
max_drawdown_pct: 13.48
win_rate: 0.474
---

# GBPUSD Empirical Playbook: Daily VWAP Extreme Stretch Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.03 (Zero-Lookahead simulation)
- **Profit Factor**: 1.12 (97 verified trade executions)
- **Max Drawdown**: 13.5% (Institutional risk profile)
- **Total PnL Return**: +5.4%
- **Win Rate**: 47.4% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.0x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Measure standard deviation distance from Daily Institutional VWAP.
- Long Trigger: Price extends <= -1.4 ATR below VWAP, Close > Open, and RSI <= 38.
- Short Trigger: Price extends >= +1.4 ATR above VWAP, Close < Open, and RSI >= 62.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if VWAP slope accelerates sharply in trend direction.
- Invalidate if price does not reject within 2 bars.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
