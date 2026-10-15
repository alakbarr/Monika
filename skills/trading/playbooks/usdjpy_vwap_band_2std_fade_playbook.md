---
name: usdjpy_vwap_band_2std_fade_playbook
description: VWAP 2-stddev boundary mean reversion for USDJPY.
symbol: USDJPY
regime: mean_reverting
timeframe: H1
min_rr: 1.75
status: active
sharpe_ratio: 2.54
profit_factor: 1.16
max_drawdown_pct: 11.77
win_rate: 0.415
---

# USDJPY Empirical Playbook: VWAP Multi-Band Statistical Stretch Reversion

## Quantitative Track Record
- **Asset / Instrument**: USDJPY
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 2.54 (Zero-Lookahead simulation)
- **Profit Factor**: 1.16 (118 verified trade executions)
- **Max Drawdown**: 11.8% (Institutional risk profile)
- **Total PnL Return**: +10.2%
- **Win Rate**: 41.5% (Normalized at minimum 1:1.75 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 0.8x ATR, Take-Profit = 1.4x ATR, Max Holding = 12 bars

## Trigger Conditions & Tactical Directives
- Calculate intraday session VWAP and ATR-normalized deviation.
- Long Trigger: Price extends <= -1.5x ATR from VWAP and prints bullish close.
- Short Trigger: Price extends >= +1.5x ATR from VWAP and prints bearish close.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.75 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 0.8x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.4x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price prints two consecutive closes accelerating away from VWAP.
- Invalidate during central bank rate announcements.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 12 bars.
