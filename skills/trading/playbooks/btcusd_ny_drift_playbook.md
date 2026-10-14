---
name: btcusd_ny_drift_playbook
description: New York afternoon trend momentum drift for BTCUSD.
symbol: BTCUSD
regime: trending
timeframe: H1
min_rr: 2.33
status: active
sharpe_ratio: 1.7
profit_factor: 1.18
max_drawdown_pct: 11.79
win_rate: 0.385
---

# BTCUSD Empirical Playbook: New York Afternoon Trend Momentum Drift

## Quantitative Track Record
- **Asset / Instrument**: BTCUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 1.70 (Zero-Lookahead simulation)
- **Profit Factor**: 1.18 (156 verified trade executions)
- **Max Drawdown**: 11.8% (Institutional risk profile)
- **Total PnL Return**: +16.9%
- **Win Rate**: 38.5% (Normalized at minimum 1:2.33 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.5x ATR, Take-Profit = 3.5x ATR, Max Holding = 28 bars

## Trigger Conditions & Tactical Directives
- Active during late US session hours (16:00 to 18:00 UTC).
- Long Trigger: Close > EMA 50, candle closes higher than open, and RSI >= 52.
- Short Trigger: Close < EMA 50, candle closes lower than open, and RSI <= 48.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:2.33 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.5x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 3.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price prints an evening star / morning star reversal pattern.
- Invalidate during US bond market early close or low-liquidity holidays.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 28 bars.
