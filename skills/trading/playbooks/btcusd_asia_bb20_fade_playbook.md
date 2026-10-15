---
name: btcusd_asia_bb20_fade_playbook
description: Verified ranging tactical execution playbook for BTCUSD.
symbol: BTCUSD
regime: ranging
timeframe: H1
min_rr: 2.5
status: active
sharpe_ratio: 13.84
profit_factor: 1.49
max_drawdown_pct: 11.1
win_rate: 0.413
---

# BTCUSD Empirical Playbook: Asia Bb20 Fade Strategy

## Quantitative Track Record
- **Asset / Instrument**: BTCUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 13.84 (Zero-Lookahead simulation)
- **Profit Factor**: 1.49 (92 verified trade executions)
- **Max Drawdown**: 11.1% (Institutional risk profile)
- **Total PnL Return**: +29.0%
- **Win Rate**: 41.3% (Normalized at minimum 1:2.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 2.5x ATR, Max Holding = 20 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Price sweeps support band/lower boundary, showing bullish rejection wick on H1.
- Short Trigger: Price sweeps resistance band/upper boundary, showing bearish rejection wick on H1.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 2.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes fully beyond range extreme by more than 0.35x ATR.
- Invalidate if opposite structural momentum triggers before trade execution fill.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 20 bars.
