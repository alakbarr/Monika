---
name: orderbook-liquidity-microstructure
description: "Microstructure dynamics, spread regimes, depth imbalance, and toxicity."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [microstructure, liquidity, spread, slippage, execution, mt5]
---

# Order Book Liquidity & Microstructure Execution Dynamics

## 1. Platform Infrastructure & Data Availability Caveat
- **Level 2 Depth of Market (DOM)**: Full centralized order book depth is available in MT5 only for exchange-traded centralized instruments (futures) and select true ECN bridge brokers.
- **Retail FX & CFD Environment**: For decentralized OTC currency and CFD instruments, order book depth is inferred via tick volume velocity, bid-ask spread dynamics, and Price Action Structural Liquidity Pools (SMC sweeps).

## 2. Microstructure Metrics & Indicators
1. **Spread Expansion Velocity (Toxicity Filter)**:
   - Tool: `get_spread_snapshot`
   - Monitor real-time bid-ask spread against the 20-period M1 ATR baseline.
   - **Normal Baseline**: Spread $\le 1.5\times$ historical median. Full market order execution permitted.
   - **Elevated Liquidity Stress ($1.5\times\text{--}2.5\times$)**: Route via limit or stop pending orders; reject aggressive market fills.
   - **Toxic Flow Window ($> 2.5\times$)**: Immediate execution halt. Do not dispatch market orders due to severe slippage vulnerability.

2. **Order Book Imbalance (OBI) on Centralized/ECN Feeds**:
   $$OBI = \frac{V_{bid} - V_{ask}}{V_{bid} + V_{ask}}$$
   - Persistent positive $OBI > +0.35$ over rolling 5-minute bars signals strong institutional resting buy depth.
   - Sharp divergence between rising spot price and deeply negative OBI signals exhaustion and impending pullback.

## 3. Execution Routing Protocols for MT5
- **Single-Ticket Lot Splitting**: If calculated position size exceeds the broker's maximum single-ticket lot limit (typically 50.0–100.0 lots) or exceeds 5.0 lots during off-peak hours:
  - Split order into sequential sub-tickets of $\le 2.0\text{--}5.0$ lots with $500\text{ms}$ execution pacing.
- **Slippage Defense Integration**:
  - Always pair market execution with explicit deviation constraints (`deviation = 50` on 5-digit brokers).
  - Use `ORDER_FILLING_IOC` to prevent lingering unfilled balances across volatile liquidity voids.
