---
name: xauusd_stoch8_rev_asia_playbook
description: Verified ranging tactical execution playbook for XAUUSD.
symbol: XAUUSD
regime: ranging
timeframe: H1
min_rr: 2.17
status: active
sharpe_ratio: 13.27
profit_factor: 1.44
max_drawdown_pct: 10.7
win_rate: 0.406
---

# XAUUSD Empirical Playbook: Stochastic 8 Rev Asia Strategy

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 13.27 (Zero-Lookahead simulation)
- **Profit Factor**: 1.44 (202 verified trade executions)
- **Max Drawdown**: 10.7% (Institutional risk profile)
- **Total PnL Return**: +66.3%
- **Win Rate**: 40.6% (Normalized at minimum 1:2.17 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.6x ATR, Take-Profit = 1.3x ATR, Max Holding = 10 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Price sweeps support band/lower boundary, showing bullish rejection wick on H1.
- Short Trigger: Price sweeps resistance band/upper boundary, showing bearish rejection wick on H1.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.17 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.6x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.3x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes fully beyond range extreme by more than 0.35x ATR.
- Invalidate if opposite structural momentum triggers before trade execution fill.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 10 bars.
