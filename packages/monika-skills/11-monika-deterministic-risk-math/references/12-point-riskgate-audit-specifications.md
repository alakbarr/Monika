# Reference: 12-Point RiskGate Pre-Execution Audit Specifications

Dokumen ini menjelaskan spesifikasi rinci dari ke-12 pemeriksaan pra-eksekusi `RiskGate` Monika.

---

## 1. Spesifikasi Teknis 12 Pemeriksaan RiskGate

1. `valid_finite_inputs`:
   - Memastikan $Entry, SL, TP, ATR, ADR, Equity$ semuanya terdefinisi, bernilai riil positif, dan tidak mengandung $NaN$ atau $\pm \infty$.
2. `directional_bracket_ordering`:
   - Buy: Memastikan $SL < Entry < TP$.
   - Sell: Memastikan $TP < Entry < SL$.
3. `noise_floor_protection`:
   - Memastikan jarak $|Entry - SL| \ge M_{\text{noise}} \times ATR$ (toleransi pembulatan $2\%$).
4. `max_stop_cap`:
   - Memastikan jarak $|Entry - SL| \le 3.0 \times ATR$ dan $\le 1.0 \times ADR$.
5. `minimum_rr_ratio`:
   - Memastikan rasio $\frac{|TP - Entry|}{|Entry - SL|} \ge 1.48$ (pembulatan aman untuk standar 1.50).
6. `spatial_dealing_range_anti_chasing`:
   - Memastikan tidak ada order Buy pada $pos > 0.85$ atau order Sell pada $pos < 0.15$.
7. `daily_drawdown_limit`:
   - Memastikan total kerugian harian saat ini $< 3.0\%$ dari ekuitas awal.
8. `spread_spike_gate`:
   - Memastikan rasio spread pasar terhadap spread tipikal instrumen $\le 2.0\text{x}$.
9. `rollover_blackout_window`:
   - Memastikan waktu eksekusi berada di luar jendela `21:55 - 22:15 UTC`.
10. `event_blackout_window`:
    - Memastikan tidak ada rilis berita berdampak tinggi (Tier-1) dalam rentang $[-15\text{ menit}, +30\text{ menit}]$.
11. `systemic_crisis_gate`:
    - Memastikan $VIX \le 30.0$ dan $HY\text{ OAS} < 450\text{ bps}$.
12. `stale_data_verified`:
    - Memastikan seluruh data pasar berada dalam jendela TTL atau penalti pemotongan lot $50\%$ telah diterapkan.
