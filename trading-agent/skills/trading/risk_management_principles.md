# file: skills/risk_management_principles.md

# Risk Management Principles — Intraday Range-Edge

## Sizing & Stop Loss Rules
- Risk exactly `risk_percent_per_trade` (default 1-1.5%) of equity per trade.
- Lot size = (Equity × Risk%) ÷ (SL_pips × Pip_value_per_lot).
- **SL Structure**: Must be placed BEYOND valid swing/OB/FVG/SR level.
- **SL ATR Floor**: Distance ≥ 1.0× ATR_14(H4).
- **SL ADR Ceiling**: Distance ≤ 35% of 5-day ADR (7-day for crypto). If nearest structural SL exceeds ceiling → WAIT.
- **Never widen SL** after entry.

## Take Profit & Portfolio Rules
- **TP ADR Band**: Must land between 50% and 80% of ADR at an in-band structural target.
- **Minimum R:R**: ≥ 1.3:1 (intraday range).
- **Resolution**: Targeted within ~1 trading day. If open >30h without hitting TP/SL → thesis stalled → consider exit.
- Max open positions: `max_concurrent_positions` (default 5). Max 1 per symbol.
- Daily Drawdown ≥ 3% → PAUSE new entries.
- VIX > 30 → System-level pause.
