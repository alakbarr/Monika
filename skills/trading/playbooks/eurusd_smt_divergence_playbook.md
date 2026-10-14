---
name: eurusd_smt_divergence_playbook
description: Smart Money Technique RSI divergence playbook for EURUSD.
symbol: EURUSD
regime: mean_reverting
timeframe: H1
min_rr: 2.33
status: active
sharpe_ratio: 2.88
profit_factor: 1.34
max_drawdown_pct: 11.63
win_rate: 0.419
---

# EURUSD Empirical Playbook: Smart Money Technique (SMT) RSI Divergence

## Quantitative Track Record
- **Asset / Instrument**: EURUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.88 (Zero-Lookahead simulation)
- **Profit Factor**: 1.34 (191 verified trade executions)
- **Max Drawdown**: 11.6% (Institutional risk profile)
- **Total PnL Return**: +43.1%
- **Win Rate**: 41.9% (Normalized at minimum 1:2.33 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.5x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Identify divergence between price swings and 14-period RSI indicator.
- Long Trigger: Price makes lower low over 8 bars but RSI prints higher low (+2.0 pts).
- Short Trigger: Price makes higher high over 8 bars but RSI prints lower high (-2.0 pts).

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.33 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price continues running strongly against divergence for 2 bars.
- Invalidate if RSI crosses midpoint (50.0) prior to entry execution.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
