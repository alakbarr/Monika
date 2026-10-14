---
name: eurusd_rsi_extreme_reversal_playbook
description: RSI deep extreme exhaustion reversal for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.5
status: active
sharpe_ratio: 2.18
profit_factor: 1.22
max_drawdown_pct: 6.07
win_rate: 0.388
---

# EURUSD Empirical Playbook: RSI Deep Extreme Exhaustion Reversal

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.18 (Zero-Lookahead simulation)
- **Profit Factor**: 1.22 (80 verified trade executions)
- **Max Drawdown**: 6.1% (Institutional risk profile)
- **Total PnL Return**: +10.4%
- **Win Rate**: 38.8% (Normalized at minimum 1:2.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 3.0x ATR, Max Holding = 22 bars

## Trigger Conditions & Tactical Directives
- Monitor 14-period RSI on H1 for structural exhaustion levels.
- Long Trigger: RSI <= 32 and candle prints bullish close (Close > Open).
- Short Trigger: RSI >= 68 and candle prints bearish close (Close < Open).

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if RSI continues pushing deeper into extreme without divergence.
- Invalidate if price fails to form a swing pivot within 2 bars.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 22 bars.
