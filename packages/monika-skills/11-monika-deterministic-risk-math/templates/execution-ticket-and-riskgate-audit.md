# Execution Ticket & 12-Point RiskGate Pre-Execution Audit: [SYMBOL]

**Audit Timestamp (UTC)**: [YYYY-MM-DD HH:MM:SS UTC]
**Symbol**: [SYMBOL] | **Direction**: [BUY / SELL]
**Asset Class**: [Forex Major / JPY Pair / Commodity / Crypto]

---

## 1. Concrete Deterministic Bracket
```json
{
  "symbol": "[SYMBOL]",
  "direction": "[BUY / SELL]",
  "entry_price": [Price],
  "stop_loss": [SL],
  "take_profit_1": [TP1],
  "risk_distance_points": [Distance],
  "sl_atr_ratio": [X.XX]x,
  "reward_to_risk": [X.XX]
}
```

---

## 2. Fixed-Fractional Decimal Sizing Ticket
- **Account Equity**: $[Equity]
- **Base Risk %**: [X.X]% | **Effective Risk %**: [X.X]%
- **Calculated Dollar Risk Budget**: $[Amount]
- **Raw Unrounded Lots**: [X.XXXX] Lots
- **Floored Recommended Lots**: **[X.XX] Lots** (`ROUND_FLOOR` enforced)
- **Actual Dollar Risk at Stop Loss**: **$[Actual Amount]** (Budget compliant: [YES / NO])

---

## 3. 12-Point Pre-Execution RiskGate Audit Checklist
| # | Audit Check Name | Evaluation Criteria | Result | Detail |
|---|---|---|---|---|
| 1 | `valid_finite_inputs` | Inputs positive, finite, non-NaN | [PASS / FAIL] | All inputs verified |
| 2 | `directional_bracket_ordering` | SL < Entry < TP (or inverse for Sell) | [PASS / FAIL] | Order validated |
| 3 | `noise_floor_protection` | SL >= [1.25x/1.35x] ATR | [PASS / FAIL] | [X.XX]x ATR >= floor |
| 4 | `max_stop_cap` | SL <= 3.0x ATR and <= 1.0x ADR | [PASS / FAIL] | Cap respected |
| 5 | `minimum_rr_ratio` | R:R >= 1.50 | [PASS / FAIL] | Exact R:R = [X.XX] |
| 6 | `spatial_dealing_range_anti_chasing`| pos in [0.15 .. 0.85] | [PASS / FAIL] | pos = [X.XXXX] |
| 7 | `daily_drawdown_limit` | Daily drawdown < 3.00% | [PASS / FAIL] | Loss = [X.XX]% |
| 8 | `spread_spike_gate` | Spread ratio <= 2.0x typical | [PASS / FAIL] | Ratio = [X.XX]x |
| 9 | `rollover_blackout_window` | Outside 21:55 - 22:15 UTC | [PASS / FAIL] | Checked against clock |
| 10 | `event_blackout_window` | No Tier-1 event in window | [PASS / FAIL] | Calendar verified |
| 11 | `systemic_crisis_gate` | VIX <= 30.0, HY OAS < 450 bps | [PASS / FAIL] | VIX=[XX.X], OAS=[XXX] |
| 12 | `stale_data_verified` | Fresh data or 0.5x scaling applied | [PASS / FAIL] | TTL compliant |

**AUDIT VERDICT**: **[APPROVED FOR ORDER EXECUTION / REJECTED — FAIL CLOSED]**
