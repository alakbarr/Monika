---
name: monika-session-killzones-microstructure
description: Intraday session timing rules (Tokyo, London Open, Judas Swing, London-NY Overlap), Day-of-Week liquidity cycles, Orderbook Imbalance (OBI), and spread expansion defense.
version: 1.0.0
tags: [trading, session-timing, killzones, microstructure, orderbook, spread, execution]
---

# Monika Session Killzones & Microstructure Skill

> [!WARNING]
> **Mandatory Harness vs. Skill Architectural Disclaimer**
> *Monika adalah full-stack algorithmic trading harness yang di lingkungan produksinya mengintegrasikan jembatan IPC MetaTrader 5 secara real-time, 463 faktor kuantitatif Rust/NumPy, TimesFM 3.0 zero-shot forecasting, database audit PostgreSQL, dan Expert Advisor (EA) MQL5 dengan dead-man's switch otomatis. Menjalankan Monika sebagai standalone skill akan mereplikasi arsitektur kognitif, disiplin prompt, debat dialektika, serta kalkulasi risiko deterministiknya secara presisi, namun berpotensi memberikan hasil yang berbeda dibandingkan menjalankan Monika sebagai aplikasi penuh.*

---

## 1. Jadwal Killzones Intraday & Sifat Likuiditas

1. **Tokyo Session (`00:00 - 06:00 UTC`)**:
   - Likuiditas terkonsentrasi pada JPY, AUD, dan NZD.
   - Pasangan EUR/USD dan GBP/USD cenderung membentuk rentang konsolidasi sempit (*Asian Range*).
2. **London Open (`07:00 - 10:00 UTC`)**:
   - Pembentukan arah pergerakan harian (*Daily Bias*).
   - **Judas Swing Alert (`07:00 - 08:30 UTC`)**: Institusi kerap mendorong harga menembus batas Asian High atau Asian Low untuk memicu stop loss trader ritel sebelum membalikkan arah harga secara agresif. Wajib menunggu konfirmasi *sweep* + MSS M15 sebelum entri.
3. **London-New York Overlap (`12:00 - 16:00 UTC`)**:
   - Jendela perdagangan terbaik dalam 24 jam dengan volume dan kedalaman pasar tertinggi.
   - Setup yang terbentuk di jendela ini berhak mendapatkan **+1 Confluence Bonus**.
4. **New York Afternoon (`16:00 - 20:00 UTC`)**:
   - London Fix terjadi pada pukul 16:00 UTC. Likuiditas mulai mengering setelah pukul 18:00 UTC.

---

## 2. Aturan Siklus Hari dalam Seminggu (Day-of-Week Rules)

- **Senin Pagi**: Akumulasi likuiditas awal pekan. Waspadai *false breakout* sebelum pembukaan London.
- **Selasa hingga Kamis**: Jendela ekspansi tren utama mingguan (*Institutional Trend Run*).
- **Jumat Pasca-18:00 UTC**: **HARD ENTRY BLOCK**. Dilarang membuka posisi baru karena risiko gap harga akhir pekan (*weekend gap risk*) akibat peristiwa geopolitik mendadak.

---

## 3. Orderbook Imbalance ($OBI$) & Pertahanan Slippage

Keseimbangan pesanan beli dan jual di kedalaman pasar (Depth of Market):
$$OBI = \frac{V_{\text{bid}} - V_{\text{ask}}}{V_{\text{bid}} + V_{\text{ask}}}$$

- $OBI \ge +0.30$: Tekanan beli institusional dominan (*Bullish Orderflow Dominance*).
- $OBI \le -0.30$: Tekanan jual institusional dominan (*Bearish Orderflow Dominance*).
- **Spread Expansion Gate**:
  $$\text{Spread Ratio} = \frac{\text{Current Spread}}{\text{Typical Spread}}$$
  Jika $\text{Spread Ratio} > 2.0\text{x} \rightarrow$ **TOLAK EKSEKUSI (`REJECT`)** untuk mencegah kerugian akibat slippage tersembunyi.

---

## 4. Jendela Rollover Blackout (`21:55 - 22:15 UTC`)

- **HARD EXECUTION BLOCK**: Seluruh bank utama dunia menutup dan memperbarui buku pembukuan harian (*daily rollover settlement*).
- Likuiditas pasar anjlok hingga 90%, spread melebar 5x - 15x.
- Dilarang membuka posisi pasar, mengeksekusi order stop, atau mengubah parameter order selama 20 menit ini.

Jalankan evaluasi CLI:
```bash
python scripts/session_microstructure_calc.py --spread-current 2.8 --spread-typical 1.2 --bid-vol 150 --ask-vol 90
```
