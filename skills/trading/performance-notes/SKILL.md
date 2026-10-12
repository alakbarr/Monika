---
name: performance-notes
description: "Stage 2 execution performance review notes and per-asset bias tracking."
category: TRADING
version: 1.0.0
platforms: [windows, linux, macos]
tags: [performance_notes, stage2, paper_trading, calibration, execution_notes]
---

# Performance Notes — Auto-Generated Review

> **Runtime Variable Resolution**: Placeholders like `{effective_threshold}` are dynamically injected at runtime by `skills/loader.py` from active `settings.yaml` / `AdaptiveRiskPolicy`. When viewing raw text, the default confluence threshold is `7/14`.

## Current Performance Status
*Auto-populated weekly by `analysis/memory/background_review.py` after 10+ closed paper trades. Default operational thresholds apply during initialization.*

## Default Operational Thresholds
- **Standard Confluence Floor**: `{effective_threshold}/14` (default 7/14) applies universally across the asset universe.
- **Symbol-Specific Risk Allocations**: Calibrated per volatility profile (FX: 1.0%, XAUUSD: 1.0%, BTCUSD: 0.60%).
- **Dynamic Risk Scaling**: Active window scaling based on rolling 20-trade win rate.

## Execution Discipline Invariants (Binding)
1. **Priced-In Gate**: Must verify priced-in score < 8 before executing. Any score >= 8 mandates an immediate WAIT decision.
2. **Stop Loss Protection**: SL must sit strictly beyond verified structural invalidation AND maintain a distance >= 1.0x H4 ATR(14).
3. **Multi-Timeframe Alignment**: D1 market structure establishes sovereign macro context; H4/H1 provides entry precision.
4. **Anti-Deliberation Directive**: A valid technical setup with confluence >= threshold MUST be submitted as an active trade. Do not use WAIT to express analytical hesitation on qualified setups.
5. **Legitimate WAIT Criteria**: Submit WAIT only when price has not yet tapped the required institutional entry zone or when confluence is objectively sub-threshold.

*This file is regenerated weekly by the background memory engine.*
