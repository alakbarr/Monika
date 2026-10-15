---
name: usdjpy_adr_exhaustion_reversal_playbook
description: Average daily range exhaustion reversal for USDJPY.
symbol: USDJPY
regime: mean_reverting
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 2.32
profit_factor: 1.34
max_drawdown_pct: 5.19
win_rate: 0.402
---

# USDJPY Empirical Playbook: 24-Hour Range Exhaustion Mean Reversion

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.32 (Zero-Lookahead simulation)
- **Profit Factor**: 1.34 (87 verified trade executions)
- **Max Drawdown**: 5.2% (Institutional risk profile)
- **Total PnL Return**: +17.1%
- **Win Rate**: 40.2% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Rolling 24-hour range expands >= 1.1x 14-period ATR.
- Long Trigger: Low tests 24h low, RSI <= 40, and candle closes bullish.
- Short Trigger: High tests 24h high, RSI >= 60, and candle closes bearish.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price prints a runaway trend candle closing beyond the extreme.
- Invalidate if fundamental catalyst triggers sustained orderflow.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.
