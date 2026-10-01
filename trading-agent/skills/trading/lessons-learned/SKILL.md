---
name: lessons-learned
description: "Empirical trade lessons, post-SL protocols, and edge retention heuristics."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [lessons_learned, execution, post_sl, liquidity, risk_heuristics]
---

# Empirical Lessons Learned & Trade Execution Directives

## 1. Post Stop-Loss Protocol (Revenge Trading Defense)
- **4-Hour Lockout**: If an asset hits stop-loss within the preceding 4 hours, re-entry in the identical direction is prohibited absent a confirmed H4 Market Structure Shift (MSS).
- **Sweep vs Trend Break Distinction**: Stop-loss hits frequently represent institutional liquidity sweeps. Require an H4 bar close back inside the prior range (reclaim) via `get_liquidity_sweep_context` before considering reversal setups.
- **Cool-Down Window**: Enforce a minimum 1 H4 candle close following a stop-loss before re-evaluating the symbol.

## 2. Trap & Fakeout Avoidance
- **Priced-In Score $\ge 8$**: When market anticipation is fully saturated ahead of Tier-1 releases (NFP, FOMC, CPI), expect high-probability "sell-the-news" or mean-reverting dynamics. Mandatory `WAIT`.
- **FVG Confirmation**: Do not enter solely on Fair Value Gap presence without visible mitigation or rejection price action on H4/H1.
- **Fakeout Detection**: An H4 candle breaching a key S/R level and subsequently closing back inside the range indicates a failed breakout. Wait for adjacent candle confirmation.

## 3. Multi-Timeframe Discipline (D1 vs H4)
- **D1 Trend Dominance**: H4 setups conflicting with the D1 primary trend show historically lower win rates ($< 35\%$). Counter-trend positions require extreme RSI divergence alongside verified H4 ChoCH.
- **Minimum Reward-to-Risk**: Reject setups where expected reward-to-risk falls below $1.30:1$ (intraday) or $1.50:1$ (swing) net of broker spreads and slippage.
- **Confluence Alignment**: Strict directional alignment across D1 and H4 trends provides execution confidence.

## 4. High-Conviction Tactical Signals
- **D1 Trend + H4 FVG/Order Block Confluence + Unextended Price**: High-probability setup across trend-following strategies.
- **Post-Data Liquidity Sweeps (within 2h)**: Following economic data spikes, allow the H4 bar to close to confirm directional commitment.
- **London Open (08:00–09:30 UTC)**: Asian session liquidity sweep coupled with FVG formation represents prime execution windows.
- **Bitcoin (BTCUSD)**: 4-hour close relative to key inflection levels aligned with derivatives funding rates signals sustained directional momentum.
- **London / New York Session Overlap (13:00–16:00 UTC)**: Prime institutional liquidity window offering tightened spreads and optimal order fill quality.

## 5. Win Rate Adaptation Framework
- **Win Rate < 35% across 10+ samples**: Automatically increment confluence entry threshold by $+1$. Audit for systemic directional or regime bias.
- **Win Rate > 55% across 10+ samples**: Eligible for $-1$ threshold reduction to capture additional opportunity.
- **Streak Safeguard (3 consecutive SL hits)**: Triggers temporary symbol-level cooldown.

## 6. Confluence Score Threshold Guidelines
- **Score 6–7 with D1 ADX > 25 (Strong Trend)**: Validated for entry under trend-following regimes (effective threshold -1).
- **Score 6–7 with Unanimous Specialist Consensus (Technical + Sentiment + Macro)**: Validated for execution.
- **Score < 6**: Mandatory `WAIT` — execution unjustified.
- **Score $\ge 8$**: High-conviction alignment permitting standard position sizing.

## 7. Operational Diagnostics for Excess Inaction
Excessive `WAIT` outputs across all universe assets indicate operational friction rather than prudence:
- Run system diagnostics: `python -m cli.main doctor` to check database, broker IPC, and tool registries.
- Verify tool execution integrity via `get_volatility_regime` and `get_daily_range_context`.
- Audit whether thresholds are artificially suppressed by high VIX or priced-in penalties.
