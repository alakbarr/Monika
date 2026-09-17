# file: skills/commodity_analysis.md

# Commodity Analysis Framework — XTIUSD (WTI Crude Oil)

## Driver Hierarchy
1. **EIA Inventory (Wed 14:30 UTC)**: Build > +2M bbl = bearish; Draw > -2M bbl = bullish. Surprise magnitude drives move. Tool: `get_eia_oil_inventory`.
2. **OPEC+ Policy**: Cuts = bullish spike; Hike = bearish. Check pre-meeting leaks 24-48h prior.
3. **USD Correlation**: Inverse correlation with DXY (-0.6 to -0.8).
4. **Geopolitical Risk**: Middle East escalation = supply disruption premium (compresses quickly if resolved).

## Technical & Entry Rules
- Round numbers ($70, $75, $80, $85, $90, $100) are major institutional levels.
- ATR is 2-3x FX pairs → SL must be ≥ 2× ATR from entry.
- Avoid new Friday entries (weekend gap risk).
- If OPEC meeting within 48h → reduce lot size by 50% or AVOID.
- Sizing follows standard ADR band (TP: 50-80% ADR, SL: ≤35% ADR).
