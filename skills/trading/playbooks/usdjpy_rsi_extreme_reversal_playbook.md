---
name: usdjpy_rsi_extreme_reversal_playbook
description: RSI deep extreme exhaustion reversal for USDJPY.
symbol: USDJPY
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 1.03
profit_factor: 1.14
max_drawdown_pct: 8.76
win_rate: 0.388
---

# USDJPY Empirical Playbook: RSI Deep Extreme Exhaustion Reversal

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.03 (Zero-Lookahead simulation)
- **Profit Factor**: 1.14 (67 verified trade executions)
- **Max Drawdown**: 8.8% (Institutional risk profile)
- **Total PnL Return**: +4.8%
- **Win Rate**: 38.8% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Monitor 14-period RSI on H1 for structural exhaustion levels.
- Long Trigger: RSI <= 32 and candle prints bullish close (Close > Open).
- Short Trigger: RSI >= 68 and candle prints bearish close (Close < Open).

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if RSI continues pushing deeper into extreme without divergence.
- Invalidate if price fails to form a swing pivot within 2 bars.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.
