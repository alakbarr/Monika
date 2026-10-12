---
name: smt-divergence-playbook
description: "Smart Money Technique (SMT) divergence playbook across correlated assets."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [smt, smc, ict, divergence, correlation, dxy, eurusd, gbpusd]
---

# Smart Money Technique (SMT) Divergence Playbook

## 1. Overview & Institutional Rationale
SMT (Smart Money Technique) Divergence occurs when two fundamentally or statistically correlated instruments fail to confirm each other's swing highs or swing lows. 
This crack in correlation is one of the highest-conviction signatures of institutional accumulation or distribution:
- When Pair A takes out liquidity (makes a Lower Low / Higher High) but Pair B fails to do so (makes a Higher Low / Lower High), the non-breaking pair exhibits underlying relative strength or weakness.
- The failure to confirm signifies that smart money is actively absorbing orders without allowing the second asset to break structure.

## 2. Canonical Asset Pairs
1. **Correlated Forex Pairs**:
   - `EURUSD` vs `GBPUSD`: Strongly correlated positively ($r \approx 0.85$).
   - `AUDUSD` vs `NZDUSD`: Commodity currency pair divergence.
2. **Inverted Dollar Index Pairs**:
   - `EURUSD` (or `GBPUSD`) vs `DXY`: Inverted correlation ($r \approx -0.90$).
3. **Crypto Assets**:
   - `BTCUSD` vs `ETHUSD`: High correlation in crypto liquidity cycles.

## 3. Divergence Patterns & Signal Classification

### Bullish SMT Divergence (Accumulation / Reversal Up)
- **Asset A (EURUSD)**: Sweeps key swing low -> Makes **Lower Low (LL)**.
- **Asset B (GBPUSD)**: Holds previous swing low -> Makes **Higher Low (HL)** (Relative Strength).
- **Execution Rule**:
  - Focus long setup on **Asset B** (the stronger pair with HL) or trade the displacement in Asset A once liquidity sweep is confirmed.
  - Confluence required: HTF Discount Zone (FVG / Bullish Order Block) or London/NY Killzone.

### Bearish SMT Divergence (Distribution / Reversal Down)
- **Asset A (EURUSD)**: Sweeps key swing high -> Makes **Higher High (HH)**.
- **Asset B (GBPUSD)**: Fails to sweep swing high -> Makes **Lower High (LH)** (Relative Weakness).
- **Execution Rule**:
  - Focus short setup on **Asset B** (the weaker pair with LH).
  - Confluence required: HTF Premium Zone (Bearish Order Block / FVG) during session Killzone.

### Inverted SMT (Asset vs DXY)
- **Normal State**: If DXY makes a Lower Low, EURUSD should make a Higher High.
- **Bearish Warning for EURUSD**: DXY makes a Lower Low, but EURUSD *fails* to make a Higher High (makes Lower High).
- **Bullish Warning for EURUSD**: DXY fails to make Lower Low (makes Higher Low), but EURUSD makes a Lower Low.

## 4. Analytical Tools in Monika
- Use `get_smt_divergence(symbol, compared_to, timeframe, lookback)` to compute divergence mathematically across swing points.
- Confluence cross-checks:
  - `get_smc_zones(symbol)` for unmitigated Order Blocks and Fair Value Gaps.
  - `get_market_session()` to verify timing within London Open (07:00-10:00 UTC) or New York Open (12:00-15:00 UTC).
  - `get_daily_range_context()` to verify whether the divergence occurred at ADR high/low boundaries.
