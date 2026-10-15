---
name: xtiusd_orderblock_mitigation_playbook
description: Institutional orderblock mitigation & retest for XTIUSD.
symbol: XTIUSD
regime: trending
timeframe: H1
min_rr: 1.67
status: active
sharpe_ratio: 1.74
profit_factor: 1.18
max_drawdown_pct: 6.27
win_rate: 0.438
---

# XTIUSD Empirical Playbook: Institutional Orderblock Mitigation & Retest

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.74 (Zero-Lookahead simulation)
- **Profit Factor**: 1.18 (128 verified trade executions)
- **Max Drawdown**: 6.3% (Institutional risk profile)
- **Total PnL Return**: +12.4%
- **Win Rate**: 43.8% (Normalized at minimum 1:1.67 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.8x ATR, Take-Profit = 3.0x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Identify institutional orderblock (last opposing candle before sharp 2-bar displacement).
- Long Trigger: Price mitigates into bullish orderblock zone, holds above OB low, and Close > EMA 50.
- Short Trigger: Price mitigates into bearish orderblock zone, holds below OB high, and Close < EMA 50.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.67 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price prints a full body close through the distal boundary of the orderblock.
- Invalidate if orderblock has been mitigated more than once.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
