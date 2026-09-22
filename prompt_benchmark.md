# Spesifikasi Arsitektur High-Performance AI Trading Agent

Monika adalah AI Trading Agent Harness khusus domain quantitative trading MetaTrader 5 (MT5).
Dokumen ini mendefinisikan standar arsitektur dan peningkatan kualitas rekayasa sistem untuk mencapai keandalan, akurasi, dan efisiensi tingkat tinggi.

## Prinsip Utama:
- Akurasi pengambilan keputusan trading di atas segalanya (Accuracy > Cost > Latency).
- Pemisahan tegas antara Persepsi AI (tidak tepercaya) dan Fortress Finansial Deterministik (RiskGate, Invariant, Idempotency).
- Optimalisasi KV cache dan efisiensi konteks untuk menghemat biaya operasional secara maksimal.
- Fail-safe ganda dengan dead-man's switch dan watchdog pemulihan otomatis.
- Arsitektur modular berbasis manifest plugin yang mudah dikonfigurasi dan diekspansi.
- Kompatibilitas multi-broker (FBS dan broker MT5 lainnya) serta dukungan deployment multi-platform (Windows & Linux VPS containerized).