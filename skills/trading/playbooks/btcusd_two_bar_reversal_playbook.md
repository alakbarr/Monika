---
name: btcusd_two_bar_reversal_playbook
description: Two-bar railway track swing reversal for BTCUSD.
symbol: BTCUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.5
status: active
sharpe_ratio: 2.67
profit_factor: 1.28
max_drawdown_pct: 6.0
win_rate: 0.409
---

# BTCUSD Empirical Playbook: Two-Bar Railway Track Swing Reversal

## Quantitative Track Record
- **Asset / Instrument**: BTCUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.67 (Zero-Lookahead simulation)
- **Profit Factor**: 1.28 (66 verified trade executions)
- **Max Drawdown**: 6.0% (Institutional risk profile)
- **Total PnL Return**: +10.5%
- **Win Rate**: 40.9% (Normalized at minimum 1:2.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.2x ATR, Take-Profit = 3.0x ATR, Max Holding = 24 bars

## Trigger Conditions & Tactical Directives
- Two consecutive strong candles each with body >= 0.6x 14-period ATR.
- Long Trigger: Down candle followed by immediate equal/larger up candle closing above prev open.
- Short Trigger: Up candle followed by immediate equal/larger down candle closing below prev open.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.2x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if second candle fails to recover at least 90% of the first candle body.
- Invalidate if wick on reversal side exceeds 35% of total bar.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 24 bars.
