---
name: partial-take-profit-and-runner-management
description: "Position lifecycle: partial profit taking, breakeven, and runner trailing."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [partial_tp, breakeven, trailing_stop, risk_management, execution]
---

# Partial Take Profit and Runner Management Playbook

## 1. Core Philosophy: Asymmetric Risk Neutralization
Institutional trade management seeks to convert speculative exposure into a "risk-free" trade as soon as structural milestones are achieved, while preserving upside potential to capture high-beta trending moves (runners).

Key Objectives:
1. **Capital Preservation**: Eliminate catastrophic loss risk by moving stop loss to breakeven once Target 1 is secured.
2. **Profit Banked**: Realize partial gains (typically 50% to 70% of total volume) at high-probability liquidity pools (opposing liquidity, session extremes, ADR boundaries).
3. **Runner Exploitation**: Allow residual volume (30% to 50%) to trail dynamic market structure (ATR trail or swing point trail) into higher-timeframe targets.

## 2. Multi-Stage Scale-Out Architecture

### Stage 1: Initial Risk Zone (Entry to 1.5R - 2.0R)
- **Stop Loss**: Maintained strictly at structural invalidation point (beyond Order Block or swing low/high).
- **Rule**: No premature breakeven adjustment before reaching at least 1.5R or key opposing liquidity. Premature BE increases chop-out rate by up to 35%.

### Stage 2: Target 1 (TP1) & Breakeven Trigger
- **Milestone**: Price reaches first significant liquidity pool (e.g. Asia High/Low, Internal FVG, or 1.5R - 2.0R).
- **Action**:
  - Close 50% - 60% of open volume via `propose_action(action_type="partial_close_and_breakeven", params={"ticket": ticket, "volume": partial_vol})`.
  - Concurrently move Stop Loss on remaining volume to Entry Price + buffer ($+1$ to $+2$ pips to cover broker commission & spread).

### Stage 3: Runner Trailing Protocol
- **Remaining Exposure**: 40% - 50% of original position.
- **Dynamic Trail Methods**:
  1. **Structure Trail**: Move SL behind each newly formed H1/H4 swing low (for longs) or swing high (for shorts).
  2. **ATR Multiple Trail**: Set trailing stop at $2.0 \times \text{ATR}(14)$ distance via `set_trailing_stop(ticket=ticket, trail_atr_multiple=2.0)`.
  3. **Milestone Targets (TP2 & TP3)**:
     - TP2: $3.0R$ to $4.0R$ (close additional 25%).
     - TP3: Macro liquidity pool or HTF Order Block (close remaining runner).

## 3. Operational Tool Commands in Monika
- **Partial Close & Breakeven**:
  `propose_action(action_type="partial_close_and_breakeven", params={"ticket": 12345, "volume": 0.05, "reason": "TP1 hit at opposing H1 liquidity"})`
- **Bulk Risk Neutralization**:
  `propose_action(action_type="bulk_breakeven", params={"only_profit": True, "symbol": "EURUSD"})`
- **Set Trailing Stop**:
  `propose_action(action_type="set_trailing_stop", params={"ticket": 12345, "trailing_pips": 25.0})`
- **Emergency Protection**:
  `propose_action(action_type="secure_positions", params={"only_profit": True})`
