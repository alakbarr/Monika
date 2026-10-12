---
name: mt5_slippage_defense
description: Handling broker requotes during high NFP volatility
version: 1.0.0
category: CRYSTALLIZED
learned_at: "2026-10-12 08:26:51"
platforms:
  - windows
  - linux
  - macos
---

# Learned Skill: mt5_slippage_defense

## Problem & Context
Broker returns 10004 REQUOTE error on market order during news spike.

## Resolution & Standard Procedure
Switch to IOC (Immediate or Cancel) with 5 pips deviation tolerance or place pending stop order.

## Verification Checklist
- [ ] Confirm context conditions match before applying.
- [ ] Execute exact validated steps above.
- [ ] Avoid repeating previously diagnosed pitfalls.
