---
name: beginner-trading-curriculum
description: Onboarding curriculum and step-by-step guidance for beginner traders.
version: 1.0.0
category: ONBOARDING_EDUCATION
---

# Kurikulum Trader Pemula Monika (Beginner Trading Curriculum)

Kurikulum ini dirancang khusus untuk memandu pengguna yang baru memulai perjalanan trading mereka bersama Monika, memastikan pemahaman risiko mendasar sebelum mengeksekusi modal riil.

---

## Modul 1: Fondasi Matematika & Money Management
* **Prinsip Utama**: *"Survival first, capital preservation always."*
* **Aturan Risiko 1%**: Jangan pernah merisikokan lebih dari 1.0% total ekuitas dalam satu trade tunggal.
* **Akun Cent (USC)**:
  * Bagi pemula dengan modal di bawah $500, gunakan akun cent.
  * Monika secara otomatis menormalkan saldo akun cent (`balance / 100.0`) agar ukuran lot tidak over-leveraged.
* **Risk-to-Reward Ratio (RRR)**:
  * Minimal RRR yang diizinkan sistem adalah 1:1.5. Target take-profit harus selalu lebih besar dari jarak stop-loss.

---

## Modul 2: Siklus Sesi Pasar & Jam Trading Utama
Pasar forex bergerak dalam 3 sesi global:
1. **Sesi Asia (00:00 – 08:00 UTC / Tokyo & Sydney)**:
   * Volatilitas rendah, membentuk batas atas (*Asian High*) dan batas bawah (*Asian Low*).
2. **Sesi London (07:00 – 16:00 UTC)**:
   * Sering memicu **Judas Swing** (pembobolan palsu range Asia pada 08:00 UTC untuk menjebak retail sebelum harga berbalik ke arah tren sebenarnya).
3. **Sesi New York (12:00 – 21:00 UTC)**:
   * *Overlap* London–New York (13:00 – 16:00 UTC) memiliki likuiditas tertinggi di dunia. Rilis berita berdampak tinggi AS (CPI, NFP, FOMC) terjadi di sesi ini.

---

## Modul 3: Membaca Laporan Ekonomi Makro Tanpa Panik
* **Angka Headline vs Fakta Sebenarnya**:
  * Angka kalender yang memerah/menghijau seringkali menipu (*fakeout*).
  * Gunakan tool `inspect_economic_report` untuk membedah apakah lonjakan disebabkan oleh komponen volatil musiman (*transitory noise* seperti tiket pesawat atau bensin) atau tekanan inflasi persisten (*sticky core* seperti sewa rumah dan upah).
* **FOMC & Suku Bunga**:
  * Gunakan tool `diff_central_bank_documents` untuk membaca naskah The Fed dan melihat apakah The Fed benar-benar bersikap hawkish atau dovish.

---

## Modul 4: Konsep Price Action & Smart Money (SMC)
* **Fair Value Gap (FVG)**: Ketidakseimbangan harga 3-candle di mana likuiditas melonjak cepat. Harga cenderung kembali menutup area ini sebelum melanjutkan tren.
* **Order Block (OB)**: Area konsolidasi institusi sebelum pergerakan impulsif besar.
* **Liquidity Sweep**: Pembersihan stop loss di atas Swing High atau di bawah Swing Low oleh institusi sebelum membalikkan arah.

---

## Modul 5: Benteng Psikologi & Disiplin
* **Bahaya Revenge Trading**: Keinginan membalas dendam pasar setelah terkena Stop Loss adalah penyebab 90% akun meledak (*margin call*).
* **Quarantine Cooldown**:
  * Jika mengalami 2-3 kerugian beruntun, aktifkan mode karantina pendinginan 2–4 jam via `create_behavioral_alert(action_mode="QUARANTINE")`.
  * Sistem akan mengunci eksekusi baru hingga pikiran kembali tenang dan objektif.
