# Data Directory (Runtime Scratch & Local Artifacts)

Direktori ini diperuntukkan secara khusus untuk penyimpanan data runtime lokal, sesi browser, dan cache sementara yang diabaikan oleh Git (`.gitignore`).

Untuk kode pipeline dan sumber data:
- **`trading-agent/data_sources/`**: Structured API fetchers (FRED, YFinance, CME, EIA, CFTC) & data freshness validation.
- **`trading-agent/scrapers/`**: Web scrapers, RSS feed parsers, dan news sentiment processors.
- **`trading-agent/indicators/`**: Formula teknikal, regime detectors, dan 900+ quantitative factors (`alpha_zoo/`).
