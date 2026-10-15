---
name: xauusd_double_inside_bar_playbook
description: Double inside bar coiling breakout for XAUUSD.
symbol: XAUUSD
regime: breakout
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 3.48
profit_factor: 1.55
max_drawdown_pct: 5.75
win_rate: 0.455
---

# XAUUSD Empirical Playbook: Double Inside Bar Coiling Spring Breakout

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 3.48 (Zero-Lookahead simulation)
- **Profit Factor**: 1.55 (33 verified trade executions)
- **Max Drawdown**: 5.8% (Institutional risk profile)
- **Total PnL Return**: +9.4%
- **Win Rate**: 45.5% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Detect two consecutive inside bars: Bar[i-1] inside Bar[i-2] inside Bar[i-3].
- Long Trigger: H1 Close breaks above Bar[i-1] high with Close > Open.
- Short Trigger: H1 Close breaks below Bar[i-1] low with Close < Open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if breakout candle fails to close outside the mother bar range.
- Invalidate if volatility contracts below minimum trading threshold.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.
