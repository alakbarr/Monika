---
name: adjudication-framework
description: "Stage 2 synthesis adjudication rules for specialist conflict resolution."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [adjudication, synthesis, confluence, stage2, trade_gate]
---

# Adjudication Framework — Stage 2 Synthesis Rules

## 1. Evidence Quality Hierarchy
1. **PRICE ACTION (Technical)**: Highest baseline weight ($45\%$). Price displacement, structural breaks (BOS/ChoCH), and unmitigated institutional zones define actual entry timing and risk boundaries.
2. **MACRO BRIEF (Macro)**: Sovereign directional tailwinds ($35\%$). High weight ($< 3\text{h}$ old), Medium ($3\text{--}5\text{h}$), Low ($> 5\text{h}$).
3. **POSITIONING (Sentiment)**: Contrarian positioning filter ($20\%$). CFTC COT multi-week extremes + Retail crowding sentiment ($> 70\%$ retail skew = contrarian signal).

## 2. Directional Synthesis Decision Matrix

| Scenario | Specialist Alignment | Synthesized Action | Sizing & Invariants |
|:---|:---|:---|:---|
| **Full Alignment** | Tech=BULL/BEAR, Macro=BULL/BEAR, Sent=ALIGNED/NEUT | **BUY / SELL** | Standard risk sizing ($1.0\times$). Execute at structural zone with score $\ge \text{threshold}$. |
| **Contrarian Sentiment** | Tech=BULL, Macro=BULL, Retail=BEARISH ($> 70\%$) | **BUY** | Standard risk sizing ($1.0\times$). Retail trap amplifies institutional move. |
| **Contrarian Sentiment** | Tech=BEAR, Macro=BEAR, Retail=BULLISH ($> 70\%$) | **SELL** | Standard risk sizing ($1.0\times$). |
| **Technical vs Macro Conflict** | Tech=BULL, Macro=BEAR (or vice-versa) | **BUY / SELL** (Follow Tech) | Downscale risk to $0.70\times$. Must have confirmed H4 Market Structure Shift + FVG retest. If structure is weak $\rightarrow$ `WAIT`. |
| **Tech Neutral + Strong Macro** | Tech=NEUT (Mid-range), Macro=STRONG ($\text{Conf} \ge 0.80$) | **WAIT for Pullback** | Do not chase. Place pending limit/stop order at structural OTE / Order Block level. |
| **Macro Neutral + Strong Tech** | Tech=STRONG ($\text{Score} \ge 8$), Macro=NEUT | **BUY / SELL** | Standard risk sizing ($1.0\times$). Technical edge independently verifiable. |
| **Ambiguous / Mixed** | Mixed signals with zero high-conviction anchors | **WAIT** | Submit `WAIT` with explicit re-evaluation price trigger. |

## 3. Mechanical Risk Gate Enforcement (Non-Negotiable)
- **Score Sub-Threshold**: If `confluence_score < effective_threshold` $\rightarrow$ Decision MUST be `WAIT`.
- **Priced-In Exhaustion**: If `priced_in_score >= 8` $\rightarrow$ Decision MUST be `WAIT`.
- **RiskGate Invalidation**: If RiskGate returns an active blocking issue (drawdown, spread, news window) $\rightarrow$ Decision MUST be `WAIT` or `AVOID`.
- Output structured analysis strictly via `submit_asset_analysis`.
