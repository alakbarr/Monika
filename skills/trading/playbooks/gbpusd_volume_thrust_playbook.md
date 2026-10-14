---
name: gbpusd_volume_thrust_playbook
description: High-volume momentum thrust continuation for GBPUSD.
symbol: GBPUSD
regime: trending
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: 1.63
profit_factor: 1.14
max_drawdown_pct: 13.12
win_rate: 0.429
---

# GBPUSD Empirical Playbook: High-Volume Momentum Thrust Continuation

## Quantitative Track Record
- **Asset / Instrument**: GBPUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.63 (Zero-Lookahead simulation)
- **Profit Factor**: 1.14 (191 verified trade executions)
- **Max Drawdown**: 13.1% (Institutional risk profile)
- **Total PnL Return**: +14.2%
- **Win Rate**: 42.9% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 2.5x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Volume surge: Tick volume >= 1.4x 20-period moving average and body >= 0.8x ATR.
- Long Trigger: Bullish thrust candle with Close > EMA 20.
- Short Trigger: Bearish thrust candle with Close < EMA 20.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if next candle closes below the 50% retracement level of the thrust bar.
- Invalidate if thrust bar exhibits exhaustion wicks > 40%.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
