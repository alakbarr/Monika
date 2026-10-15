---
name: xauusd_ema_retest_macd_playbook
description: EMA pullback with MACD confluence for XAUUSD.
symbol: XAUUSD
regime: trending
timeframe: H1
min_rr: 2.0
status: active
sharpe_ratio: 3.32
profit_factor: 1.5
max_drawdown_pct: 10.59
win_rate: 0.457
---

# XAUUSD Empirical Playbook: EMA 21 Trend Retest with MACD Confluence

## Quantitative Track Record
- **Asset / Instrument**: XAUUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 3.32 (Zero-Lookahead simulation)
- **Profit Factor**: 1.50 (94 verified trade executions)
- **Max Drawdown**: 10.6% (Institutional risk profile)
- **Total PnL Return**: +26.8%
- **Win Rate**: 45.7% (Normalized at minimum 1:2.0 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 2.0x ATR, Take-Profit = 4.0x ATR, Max Holding = 48 bars

## Trigger Conditions & Tactical Directives
- Long Trigger: Close > EMA 50, Low tests EMA 21, Close > EMA 21, MACD Hist > 0.
- Short Trigger: Close < EMA 50, High tests EMA 21, Close < EMA 21, MACD Hist < 0.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.0 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 2.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 4.0x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if candle body closes completely across EMA 50.
- Invalidate if MACD histogram turns against trend direction.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 48 bars.
