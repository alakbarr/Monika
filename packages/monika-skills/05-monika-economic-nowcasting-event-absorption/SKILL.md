---
name: monika-economic-nowcasting-event-absorption
description: Economic indicator nowcasting across 4 pillars (Inflation, Labor, Growth, Credit), Net Surprise calculation with prior revisions, Canonical 4-Method Priced-In scoring, and 3-Phase post-event orderflow absorption.
version: 1.0.0
tags: [trading, macro, economic-indicators, nowcasting, news-trading, priced-in, orderflow]
---

# Monika Economic Nowcasting & Post-Event Absorption Skill

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## 1. 4 Pilar Nowcasting & Formula Net Surprise

Setiap indikator ekonomi Tier-1 dipetakan ke dalam 4 pilar makro:
1. **Pilar Inflasi**: Core PCE, CPI, PPI, Import Price Index.
2. **Pilar Pasar Tenaga Kerja**: Non-Farm Payrolls (NFP), Tingkat Pengangguran (U-3), JOLTS, Initial Jobless Claims.
3. **Pilar Pertumbuhan & Aktivitas**: PDB (GDP), ISM Manufacturing & Services PMI, Penjualan Ritel (Retail Sales).
4. **Pilar Perumahan & Pasar Kredit**: Building Permits, Housing Starts, Senior Loan Officer Opinion Survey (SLOOS).

### Formula Net Surprise (Wajib Menyertakan Revisi Periode Sebelumnya):
Pergerakan harga pasar sering kali dipengaruhi oleh revisi angka bulan sebelumnya yang terabaikan oleh trader ritel:
$$\text{Net Surprise} = (\text{Actual} - \text{Consensus}) + \text{Prior Revision}$$

*Contoh NFP*:
- Konsensus: $+180\text{k}$ | Aktual: $+210\text{k}$ (tampak beat $+30\text{k}$)
- Namun angka bulan lalu direvisi turun: $-45\text{k}$
- $\text{Net Surprise} = (210 - 180) + (-45) = -15\text{k}$ $\rightarrow$ **Net Miss! USD Melemah**.

---

## 2. Skor Priced-In Kanonikal 4-Metode (1 - 10)

Untuk mengetahui apakah berita baik akan memicu kenaikan atau justru memicu *Sell-the-Fact*, hitung skor Priced-In (rata-rata 4 metode):
1. **FedWatch Implied Rate Convergence (1 - 10)**: Apakah probabilitas pasar berjangka sudah $>85\%$ memperhitungkan langkah Fed?
2. **COT Speculative Crowding (1 - 10)**: Apakah persentil posisi spekulan berada di ekstrem ($>85\%$ atau $<15\%$)?
3. **Multi-Week Technical Exhaustion (1 - 10)**: Apakah harga sudah naik/turun selama 3-4 minggu berturut-turut menjelang rilis berita?
4. **Historical Sell-the-Fact Frequency (1 - 10)**: Seberapa sering instrumen ini mengalami aksi profit taking pasca-katalis serupa?

> [!WARNING]
> **Peringatan Pembalikan Ekstrem (Priced-In Score $\ge 8.0$)**:
> Jika skor komposit $\ge 8.0$, pasar telah mendiskon habis hasil tersebut. Dilarang mengejar *breakout continuation*; utamakan setup pembalikan arah (*Sell-the-Fact Turtle Soup*).

---

## 3. Protokol 3-Fase Penyerapan Volatilitas Pasca-Berita

1. **Fase 1: Blackout Eksekusi Ketat (`0 - 15 Menit Pasca-Rilis`)**:
   - Dilarang membuka posisi baru. Biarkan algoritma HFT bertarung menyerap likuiditas awal.
2. **Fase 2: Pemetaan Event Anchor Range (`15 - 60 Menit Pasca-Rilis`)**:
   - Tandai `Event High` (puncak tertinggi candle berita) dan `Event Low` (titik terendah candle berita).
   - Hitung `Event Midpoint` ($50\%$).
3. **Fase 3: Eksekusi Acceptance vs. Sweep (`1 - 4 Jam Pasca-Rilis`)**:
   - **Structural Acceptance**: Harga menembus batas range dan candle M15 ditutup di luar range dengan retest yang tertahan $\rightarrow$ Eksekusi tren lanjutan.
   - **Liquidity Sweep & Fade**: Harga menusuk batas range dengan ekor candle panjang $>50\%$ lalu kembali ditutup di dalam range $\rightarrow$ Eksekusi pembalikan arah menuju midpoint range.

Jalankan evaluasi CLI:
```bash
python scripts/event_nowcast_calc.py --actual 210 --consensus 180 --prior-revision -45 --priced-in-fedwatch 8.5 --priced-in-cot 8.0 --priced-in-exhaustion 8.5 --priced-in-historical 7.5 --event-high 1.0890 --event-low 1.0820
```
