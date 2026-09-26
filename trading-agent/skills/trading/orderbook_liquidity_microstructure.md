---
name: orderbook_liquidity_microstructure
description: "Order book imbalance, market depth analysis, and microstructure sweeps."
version: 1.0.0
category: TRADING
tags: [orderbook, microstructure, depth_of_market, liquidity, vwap, execution]
---

# Order Book Liquidity & Microstructure Execution

## Core Metrics
1. **Order Book Imbalance (OBI)**:
   - Compute top-of-book volume ratio:
     $$OBI = \frac{V_{bid} - V_{ask}}{V_{bid} + V_{ask}}$$
   - Persistent positive OBI (> 0.40) over rolling 5-minute windows precedes short-term upward price pressure.

2. **Spread Expansion & Toxic Flow**:
   - Monitor real-time bid-ask spread relative to 20-period ATR.
   - When spread widens > 2.5x normal baseline during news embargo periods, halt market order executions and route limit orders only.

3. **Execution Algorithmic Routing**:
   - For trade tickets exceeding 10 lots: split via Time-Weighted Average Price (TWAP) or Volume-Weighted Average Price (VWAP) to minimize market impact and slippage.
