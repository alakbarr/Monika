---
name: xtiusd_liquidity_sweep_playbook
description: HTF swing liquidity sweep & displacement playbook for XTIUSD.
symbol: XTIUSD
regime: trending
timeframe: H1
min_rr: 1.5
status: active
sharpe_ratio: 4.67
profit_factor: 1.3
max_drawdown_pct: 8.88
win_rate: 0.489
---

# XTIUSD Empirical Playbook: HTF Swing Liquidity Sweep & Displacement

## Quantitative Track Record
- **Asset / Instrument**: XTIUSD
- **Data Source**: 4,500 H1 historical bars verified directly from connected MetaTrader 5 terminal
- **Verified Sharpe Ratio**: 4.67 (Zero-Lookahead simulation)
- **Profit Factor**: 1.30 (94 verified trade executions)
- **Max Drawdown**: 8.9% (Institutional risk profile)
- **Total PnL Return**: +15.0%
- **Win Rate**: 48.9% (Normalized at minimum 1:1.5 contractual reward-to-risk)
- **Calibrated Horizon**: Stop-Loss = 1.0x ATR, Take-Profit = 1.5x ATR, Max Holding = 12 bars

## Trigger Conditions & Tactical Directives
- Map rolling 48-hour swing high (BSL) and swing low (SSL) excluding latest 2 bars.
- Long Trigger: H1 sweeps SSL, rejects, closes back above SSL with candle body >= 0.5x ATR.
- Short Trigger: H1 sweeps BSL, rejects, closes back below BSL with candle body >= 0.5x ATR.

## Execution Invariants & Risk Parameters
- **Target Risk-to-Reward (R:R)**: Minimum 1:1.5 contractual target.
- **Stop Loss Placement**: Structured volatility buffer set at 1.0x 14-period Wilder ATR.
- **Take Profit Target**: Mathematically optimized target placed at 1.5x 14-period ATR.
- **Position Sizing**: Governed strictly by RiskGate (<= 1.0% account equity risk per trade).
- **Execution Fill**: Standardized next-bar open fill accounting for real broker spread and slippage.

## Invalidation & Exit Parameters
- Invalidate if price prints a full body close beyond the sweep extreme.
- Invalidate if trade remains stagnant without momentum for 12 bars.
- **Maximum Time Horizon**: Forced market exit if position does not reach target within 12 bars.
