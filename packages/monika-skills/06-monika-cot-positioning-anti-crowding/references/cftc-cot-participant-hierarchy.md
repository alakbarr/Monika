# Reference: CFTC COT Participant Dynamics & Interpretation

Dokumen ini memuat panduan komparatif perilaku antar kelompok partisipan pasar berjangka CFTC COT.

---

## 1. Komparasi Kelompok Partisipan COT

| Kelompok Partisipan | Sifat Pemosisian | Siklus Respon Pasar | Peran Analitis |
|---|---|---|---|
| **Commercial Hedgers** | Kontrarian / Nilai Wajar | Mengakumulasi saat harga tertekan, melepas saat harga reli | Jangkar fundamental / dasar harga institusional |
| **Non-Commercial Speculators** | Pengikut Tren (Momentum) | Memperbesar posisi seiring kenaikan tren | Indikator dorongan likuiditas / rawan squeeze di pucuk |
| **Non-Reportable Retail** | Reaktif / Sering Terjebak | Masuk terlambat di akhir siklus pergerakan | Indikator kontrarian murni di level persentil ekstrem |

---

## 2. Peringatan Crowding Berbasis Persentil 52-Minggu

$$\text{COT 52-Week Percentile} = \frac{\text{Net Pos} - \min_{52\text{W}}(\text{Net Pos})}{\max_{52\text{W}}(\text{Net Pos}) - \min_{52\text{W}}(\text{Net Pos})} \times 100\%$$

- **Percentile $\ge 85\%$**: *Crowded Long Alert*. Spekulan besar memegang posisi beli mendekati rekor tahunan. Peluang kenaikan terbatas, risiko koreksi mendadak tinggi.
- **Percentile $\le 15\%$**: *Crowded Short Alert*. Spekulan besar memegang posisi jual mendekati rekor tahunan. Waspadai *short covering rally*.
- **Percentile $40\% - 60\%$**: *Uncrowded Zone*. Aliran likuiditas memiliki ruang pertumbuhan yang sehat tanpa risiko likuidasi paksa.
