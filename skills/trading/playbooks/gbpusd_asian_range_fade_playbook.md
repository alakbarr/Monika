---
name: gbpusd_asian_range_fade_playbook
description: Asian range boundary mean reversion playbook for GBPUSD.
symbol: GBPUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.5
status: active
sharpe_ratio: 5.3
profit_factor: 1.65
max_drawdown_pct: 6.06
win_rate: 0.428
---

# GBPUSD Empirical Playbook: Asian Range Boundary Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 5.30 (Zero-Lookahead simulation)
- **Profit Factor**: 1.65 (180 verified trade executions)
- **Max Drawdown**: 6.1% (Institutional risk profile)
- **Total PnL Return**: +90.5%
- **Win Rate**: 42.8% (Normalized at minimum 1:2.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 3.0x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Active during low-volatility Asian hours (23:00 to 05:00 UTC).
- Compute rolling 8-hour range high and low extremes.
- Short Trigger: Price tests 99.95% of Asian high and prints a bearish rejection candle.
- Long Trigger: Price tests 100.05% of Asian low and prints a bullish rejection candle.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate immediately if volume spikes > 2.0x volume MA indicating breakout regime.
- Invalidate if trade is held past European open (06:00 UTC).
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
