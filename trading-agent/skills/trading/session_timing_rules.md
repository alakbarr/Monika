# file: skills/session_timing_rules.md

# Market Session Timing Rules

## Session Windows & Characteristics (UTC)

| Session | UTC | Key Pairs | Dynamics |
|:---|:---|:---|:---|
| **Tokyo** | 00:00-08:00 | USDJPY, AUDUSD | Range-bound. Avoid EUR/GBP/XAU unless confluence ≥ {effective_threshold}+1. For USDJPY/AUDUSD: standard threshold (native Asian session). SL +15% wider. |
| **London Open** | 08:00-10:00 | ALL | High volatility / initial stop-hunts. Wait for 08:30 UTC candle close before entering. |
| **London Full** | 08:00-16:00 | EUR, GBP, XAU | Primary European trend moves. |
| **NY-London Overlap** | 13:00-16:00 | ALL | **PRIME TRADING WINDOW** (Highest volume). **+1 Confluence bonus.** Best limit order execution. |
| **NY Post-London** | 16:00-21:00 | XTIUSD, USD | Volume drops 40-60%. After 17:00 UTC, only enter EUR/GBP if confluence ≥ {effective_threshold}+1. |
| **Off-Peak** | 22:00-00:00 | None | Thin liquidity, wide spreads. **-1 Confluence penalty.** Exercise caution for new entries. |

## Session Modifiers Summary
- NY-London Overlap (13:00-16:00 UTC): **+1 point**
- Off-Peak (22:00-00:00 UTC): **-1 point**
- 30 min before/after high-impact event: **-2 points** (prefer WAIT or probe size)
- London Open spike zone (08:00-08:30 UTC): **-1 point**

## Intraday Range Remaining (ADR)
- `room_remaining_pct` < 25%: Strongly prefer WAIT.
- `room_remaining_pct` 25-50%: Target lower end of TP band (50% ADR).
- `room_remaining_pct` ≥ 50%: Full TP target band (50-80% ADR) achievable.

## Prime Entry Windows (Highest Quality)
| Window | UTC | Quality | Condition |
|:---|:---|:---|:---|
| Asian Range Sweep + London Open | 07:30-09:30 | ★★★★★ | Asian range swept → FVG forms at London open → best setup |
| Post-High-Impact News (2h window) | Variable | ★★★★★ | Liquidity swept by news spike → H4 close confirms direction |
| NY Open Dust Settles | 14:00-15:00 | ★★★★ | After initial NY volatility → real directional move begins |
| NY-London Overlap | 13:00-16:00 | ★★★★ | Highest liquidity FX window |

## AVOID Windows
- **22:00-00:00 UTC**: Thin liquidity → -1 confluence score penalty. Exercise caution.
- **Friday 17:00+ UTC**: Weekend gap risk → require confluence at +2 above threshold or WAIT.
- **30 min before/after major scheduled news**: Violent spike risk → WAIT until news resolved.
- **Monday 00:00-01:00 UTC**: Market open gap risk, spread wide → no entries.

## Crypto (BTCUSD) Timing Rules
- No session restrictions EXCEPT: 20:00-21:00 UTC (NY close) often sees fake moves.
- **Weekend**: Require 10/14 confluence minimum (not negotiable — gap risk).
- **Best window**: 13:00-17:00 UTC (institutional hours crossover, highest volume).
- **Funding rate check**: Extreme positive funding (>0.05% per 8h) = crowded longs → prefer SELL or WAIT.
- **Extreme negative funding (<-0.02% per 8h)** = crowded shorts → prefer BUY or WAIT.

## Oil (XTIUSD) Timing Rules
- Primary volume: 13:00-20:00 UTC (US session + overlap).
- EIA Weekly Inventory (Wednesday ~14:30 UTC): -3 confluence penalty 30min before/after.
- OPEC news: Treat as major event → WAIT or reduce size 50%.

