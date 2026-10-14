---
name: xbrusd_atr_impulse_playbook
description: ATR expansion large-body impulse thrust for XBRUSD.
symbol: XBRUSD
regime: trending
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: 4.29
profit_factor: 1.5
max_drawdown_pct: 6.23
win_rate: 0.517
---

# XBRUSD Empirical Playbook: ATR Expansion Large-Body Impulse Thrust

## Quantitative Track Record
- **Asset / Instrument**: XBRUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 4.29 (Zero-Lookahead simulation)
- **Profit Factor**: 1.50 (116 verified trade executions)
- **Max Drawdown**: 6.2% (Institutional risk profile)
- **Total PnL Return**: +30.0%
- **Win Rate**: 51.7% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.0x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Filter for expansion candle with range >= 1.4x ATR and body >= 70% of candle range.
- Long Trigger: Strong bullish impulse candle with Close > EMA 50.
- Short Trigger: Strong bearish impulse candle with Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if subsequent bar closes past the 50% mark of the impulse candle.
- Invalidate if impulse candle displays exhaustion wicks > 30% of total range.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
