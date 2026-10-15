---
name: audusd_rsi_extreme_reversal_playbook
description: RSI deep extreme exhaustion reversal for AUDUSD.
symbol: AUDUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.53
status: active
sharpe_ratio: 3.84
profit_factor: 1.51
max_drawdown_pct: 5.06
win_rate: 0.413
---

# AUDUSD Empirical Playbook: RSI Deep Extreme Exhaustion Reversal

## Quantitative Track Record
- **Asset / Instrument**: AUDUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 3.84 (Zero-Lookahead simulation)
- **Profit Factor**: 1.51 (75 verified trade executions)
- **Max Drawdown**: 5.1% (Institutional risk profile)
- **Total PnL Return**: +24.5%
- **Win Rate**: 41.3% (Normalized at minimum 1:2.53 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.8x ATR, Max Holding = 36 bars

## Trigger Conditions & Tactical Directives
- Monitor 14-period RSI on H1 for structural exhaustion levels.
- Long Trigger: RSI <= 32 and candle prints bullish close (Close > Open).
- Short Trigger: RSI >= 68 and candle prints bearish close (Close < Open).

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.53 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.8x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if RSI continues pushing deeper into extreme without divergence.
- Invalidate if price fails to form a swing pivot within 2 bars.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 36 bars.
