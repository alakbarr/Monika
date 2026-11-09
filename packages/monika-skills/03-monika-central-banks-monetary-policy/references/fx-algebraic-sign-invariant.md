# Reference: FX Algebraic Sign Invariant Mathematical Proof

Dokumen ini menjelaskan pembuktian matematis invarian aljabar dalam penentuan bias fundamental pasangan mata uang.

---

## 1. Definisi dan Aksioma

Setiap mata uang berdaulat $C_i$ memiliki nilai vektor fundamental skalar $S(C_i) \in [-10.0, +10.0]$ yang ditentukan oleh:
$$S(C_i) = w_{\text{stance}} \cdot (R_i - r^*_i) + w_{\text{inf}} \cdot (\pi_i - \pi^*_i) - w_{\text{unemp}} \cdot \Delta U_i$$
di mana:
- $R_i$: Suku bunga acuan kebijakan moneter saat ini
- $r^*_i$: Suku bunga netral jangka panjang
- $\pi_i$: Tingkat inflasi aktual
- $\pi^*_i$: Target inflasi bank sentral
- $\Delta U_i$: Perubahan tingkat pengangguran

---

## 2. Invarian Aljabar Pasangan

Untuk setiap pasangan mata uang yang diperdagangkan $P = C_{\text{base}} / C_{\text{quote}}$, bias fundamental pasangan $\text{Bias}(P)$ didefinisikan secara unik sebagai:
$$\text{Bias}(C_{\text{base}} / C_{\text{quote}}) = S(C_{\text{base}}) - S(C_{\text{quote}})$$

### Sifat-Sifat Aljabar:
1. **Antisimetri**:
   $$\text{Bias}(C_{\text{quote}} / C_{\text{base}}) = - \text{Bias}(C_{\text{base}} / C_{\text{quote}})$$
2. **Konsistensi Transitif (Cross-Rate Consistency)**:
   $$\text{Bias}(C_A / C_C) = \text{Bias}(C_A / C_B) + \text{Bias}(C_B / C_C)$$
   *Contoh*: Jika EUR/USD bias = $+2.0$ dan USD/JPY bias = $+3.0$, maka EUR/JPY bias harus bernilai $+5.0$.

Prinsip ini menjamin bahwa seluruh hipotesis perdagangan valas tidak pernah saling bertentangan di dalam portofolio institusional.
