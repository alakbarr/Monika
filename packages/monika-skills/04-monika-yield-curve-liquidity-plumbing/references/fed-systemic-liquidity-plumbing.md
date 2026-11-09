# Reference: Federal Reserve Systemic Liquidity Plumbing

Dokumen ini merinci interaksi antara neraca Federal Reserve, kas Departemen Keuangan AS, dan pasar repo perbankan.

---

## 1. Neraca Sistemik Likuiditas Bank AS

Cadangan likuiditas bank komersial di Federal Reserve dipengaruhi oleh persamaan aliran kas:
$$\text{Bank Reserves} \approx \text{Fed Assets (WALCL)} - \text{TGA} - \text{ON RRP} - \text{Currency in Circulation}$$

### Komponen Kunci:
1. **WALCL (Total Assets of the Federal Reserve)**:
   - Merefleksikan ukuran neraca Fed.
   - Menyusut selama siklus Quantitative Tightening (QT) dengan target penarikan bulanan obligasi Treasury dan Mortgage-Backed Securities (MBS).
2. **TGA (Treasury General Account)**:
   - Rekening giro pemerintah AS di Fed New York.
   - Bertindak seperti "penghisap debu likuiditas": Ketika kas TGA naik (akibat penerimaan pajak atau penjualan obligasi), cadangan kas perbankan komersial berkurang secara langsung.
3. **ON RRP (Overnight Reverse Repurchase Facility)**:
   - Tempat parkir kas berlebih bagi reksa dana pasar uang (Money Market Funds - MMF).
   - Penurunan saldo RRP mengembalikan kas ke pasar keuangan untuk menyerap penerbitan surat utang negara (T-Bills).

---

## 2. Indikator Tekanan Pasar Pendanaan (Repo Market Stress)

1. **SOFR vs. IORB Spread**:
   - SOFR: Secured Overnight Financing Rate.
   - IORB: Interest on Reserve Balances.
   - Jika SOFR diperdagangkan $5 - 15\text{ bps}$ di atas IORB $\rightarrow$ Sinyal kekurangan likuiditas di pasar uang antarbank.
2. **Standing Repo Facility (SRF)**:
   - Penggunaan fasilitas SRF yang meningkat tajam menandakan bank enggan saling meminjamkan kas di pasar terbuka.
