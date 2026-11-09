# Reference: Deterministic Bracket Invariants & Fixed-Fractional Decimal Sizing

Dokumen ini memuat dasar matematis perhitungan bounding box bracket harga dan ukuran posisi lot berbasis `decimal.Decimal` (`ROUND_FLOOR`).

---

## 1. Invarian Bounding Box Harga Konkret

Untuk instrumen simbol $S$ pada harga terkini $P_0$, ATR 14-periode $ATR$, dan ADR 5-hari $ADR$:

### Parameter Lantai Kebisingan (Noise Floor Buffer):
$$\text{Noise Multiplier } M_{\text{noise}} = \begin{cases} 1.35, & \text{jika } S \in \{\text{BTC, ETH, XAU, XAG, XTI, XBR, BRENT, WTI}\} \\ 1.25, & \text{untuk Pasangan FX Lainnya} \end{cases}$$
$$\text{Minimum SL Distance} = M_{\text{noise}} \times ATR$$

### Batas Maksimal Stop Loss (Cap):
$$\text{Max SL Distance} = \min(2.5 \times ATR, \max(\text{Minimum SL Distance}, 0.35 \times ADR))$$

### Target Take Profit:
$$\text{Target TP Distance} = \text{SL Distance} \times \max(1.50, \text{Target R:R})$$

---

## 2. Fixed-Fractional Decimal Lot Sizing

$$\text{Dollar Risk} = \text{Equity} \times \frac{\text{Effective Risk \%}}{100}$$

$$\text{SL Pips} = \frac{|\text{Entry} - \text{Stop Loss}|}{\text{Pip Size}}$$

$$\text{Raw Lots} = \frac{\text{Dollar Risk}}{\text{SL Pips} \times \text{Pip Value USD}}$$

$$\text{Floored Lots} = \text{ROUND\_FLOOR}\left(\frac{\text{Raw Lots}}{\text{Lot Step}}\right) \times \text{Lot Step}$$

### Pembuktian Invarian Anggaran Risiko:
Karena $\text{Floored Lots} \le \text{Raw Lots}$, maka:
$$\text{Actual Risk USD} = \text{Floored Lots} \times \text{SL Pips} \times \text{Pip Value USD} \le \text{Dollar Risk}$$
Hal ini membuktikan secara matematis bahwa akun tidak akan pernah menanggung risiko melebihi anggaran risiko yang telah ditetapkan.
