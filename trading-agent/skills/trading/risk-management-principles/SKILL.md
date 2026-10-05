---
name: risk-management-principles
description: "Intraday range edge risk management, SL placement rules, and sizing gates."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [risk, lot, drawdown, sl, invalidation, margin, risk_management, position_sizing, stop_loss, adr, atr, operator]
---

# Risk Management Principles & Capital Preservation Fortress

## 1. Mathematical Position Sizing & Formulas
Position sizing is deterministically computed by `execution/service/sizing_calculator.py` using fixed fractional risk:

$$\text{Risk Amount (\$) } = \text{Account Equity} \times \text{Risk Percentage (e.g. 1.0\%)}$$
$$\text{Lot Size} = \frac{\text{Risk Amount (\$) }}{\text{SL Distance (Points)} \times \text{Tick Value per Point}}$$

### Concrete Sizing Example:
- **Account Equity**: $\$10,000.00$
- **Risk Allocation**: $1.0\% = \$100.00$
- **EURUSD Entry**: $1.08500$, **Structural SL**: $1.08250$ ($25.0\text{ pips} = 250\text{ points}$)
- **Tick Value**: $\$1.00$ per point per standard lot ($100,000$ units)
- **Calculated Lot Size**: $\frac{\$100.00}{250 \times \$1.00} = \mathbf{0.40\text{ Lots}}$

## 2. Mandatory Stop Loss & Take Profit Invariants
- **Structural Placement**: SL MUST be placed strictly beyond a verified swing high/low, Order Block boundary, or FVG invalidation.
- **ATR Distance Floor**: SL distance MUST be $\ge 1.0\times\text{ ATR}(14, \text{H4})$ ($1.1\times$ for Gold, $1.2\times$ for Crypto/Oil).
- **ADR Distance Ceiling**: SL distance MUST be $\le 35\%$ of 5-day ADR. If nearest structural protection exceeds 35% ADR $\rightarrow$ Submit `WAIT`.
- **Take Profit Target Band**: TP must land inside $50\%\text{--}80\%$ of ADR at a verified structural level.
- **Reward-to-Risk (R:R)**: Minimum $1.30:1$ (hard floor for intraday execution); preferred target $1:2.00$ or higher.
- **SL Tampering Prohibition**: NEVER widen or remove a stop loss post-execution.

## 3. Portfolio & Drawdown Risk Gates (Binding)
1. **Daily Drawdown Limit**:
   - Standard Daily Drawdown Ceiling: $\mathbf{3.0\%}$ (triggers system-level pause on new entries).
   - Absolute Hard Emergency Kill-Switch: $\mathbf{5.0\%}$ (triggers emergency pause and operator notification).
2. **Weekly Drawdown Limit**: Max $6.0\%$ total equity drawdown.
3. **Concurrent Exposure**: Maximum $5$ simultaneous open positions across portfolio; strictly max $1$ active position per symbol.
4. **Consecutive Loss Cooldown**: $3$ consecutive stop-loss hits on a single asset triggers a mandatory $12$-hour symbol suspension.
5. **Paper Trading Graduation Gate**: Live capital deployment requires $\ge 50$ closed paper trades with a win rate $\ge 55.0\%$.
