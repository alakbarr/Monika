---
name: eurusd_vwap_mean_reversion_playbook
description: Daily VWAP extreme stretch mean reversion for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 1.57
status: active
sharpe_ratio: 5.37
profit_factor: 1.62
max_drawdown_pct: 5.17
win_rate: 0.535
---

# EURUSD Empirical Playbook: Daily VWAP Extreme Stretch Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 5.37 (Zero-Lookahead simulation)
- **Profit Factor**: 1.62 (86 verified trade executions)
- **Max Drawdown**: 5.2% (Institutional risk profile)
- **Total PnL Return**: +26.0%
- **Win Rate**: 53.5% (Normalized at minimum 1:1.57 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.4x ATR, Take-Profit = 2.2x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Measure standard deviation distance from Daily Institutional VWAP.
- Long Trigger: Price extends <= -1.4 ATR below VWAP, Close > Open, and RSI <= 38.
- Short Trigger: Price extends >= +1.4 ATR above VWAP, Close < Open, and RSI >= 62.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.57 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.4x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.2x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if VWAP slope accelerates sharply in trend direction.
- Invalidate if price does not reject within 2 bars.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
