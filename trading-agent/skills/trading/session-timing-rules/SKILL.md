---
name: session-timing-rules
description: "Market session timing rules, UTC windows, and kill-zone operating mandates."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [session_timing, tokyo, london, new_york, kill_zones, utc_windows]
---

# Market Session Timing Rules & Liquidity Windows

> **Runtime Variable Resolution**: Placeholders such as `{effective_threshold}` are dynamically substituted at analysis time by the skill loader. Default baseline threshold: `7/14`.

## 1. UTC Trading Windows & Execution Dynamics

| Session | UTC Window | Primary Assets | Execution Dynamics |
|:---|:---|:---|:---|
| **Tokyo (Asian)** | 00:00–08:00 | USDJPY, AUDUSD | Range-bound liquidity accumulation. Avoid EUR/GBP/XAU unless confluence $\ge \text{threshold}+1$. Native setups for USDJPY/AUDUSD allowed at standard threshold. |
| **London Open** | 08:00–10:00 | EUR, GBP, XAU | High volatility and initial stop-hunt liquidity sweeps. Wait for 08:30 UTC candle confirmation before entering. |
| **London Full** | 08:00–16:00 | EUR, GBP, XAU | Primary directional European trend expansion. |
| **NY-London Overlap** | 13:00–16:00 | ALL ASSETS | **PRIME TRADING KILLZONE** (Peak global volume). **+1 Confluence Bonus**. Optimal limit order fill quality. |
| **NY Post-London** | 16:00–21:00 | XTIUSD, USD, BTC | Volume drops 40–60%. After 17:00 UTC, require confluence $\ge \text{threshold}+1$ on European pairs. |
| **Off-Peak / Rollover** | 22:00–00:00 | ALL ASSETS | Thin interbank liquidity and spread widening across daily rollover. Exercise extreme caution. |

## 2. Session Modifiers Matrix
- **NY-London Overlap (13:00–16:00 UTC)**: `+1 point`
- **London Open Sweep Zone (08:00–08:30 UTC)**: `-1 point` (await displacement confirmation)
- **High-Impact News Embargo (-15m to +15m)**: Server-side RiskGate blocks execution; mandatory `WAIT`
- **Off-Peak Rollover Window (22:00–00:00 UTC)**: Neutral baseline in calculator (`score += 0`), but manual entry discouraged

## 3. Calendar & Daylight Saving Time (DST) Considerations
- **US / UK DST Desynchronization**: In March and October/November, US and UK DST clocks shift on different weeks. London/NY overlap shifts temporarily by 1 hour (12:00–15:00 UTC).
- **Public & Bank Holiday Liquidity**: On US Bank Holidays (Memorial Day, Labor Day, Thanksgiving, July 4th) and UK Bank Holidays, interbank liquidity is reduced by $> 70\%$. Tighten TP targets and do not execute breakout strategies.

## 4. Intraday Range Remaining (ADR Context)
- **`room_remaining_pct` < 25%**: Price is exhausted near daily ADR extremes. Strongly prefer `WAIT`.
- **`room_remaining_pct` 25%–50%**: Target lower conservative boundary of TP band (50% ADR).
- **`room_remaining_pct` $\ge$ 50%**: Full institutional TP target band (50%–80% ADR) is achievable.

## 5. High-Risk Avoidance Windows (Mandatory)
- **22:00–00:00 UTC**: Daily rollover window with wide spreads.
- **Friday 17:00+ UTC**: Weekend gap risk. Require confluence $\ge \text{threshold}+2$ or submit `WAIT`.
- **Monday 00:00–01:00 UTC**: Market opening gap stabilization; execution prohibited.
