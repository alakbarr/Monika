# AI Cost & Performance Analysis v5 — Claude AI Trading Agent

## 0. Ringkasan Perubahan dari v4

- Provider baru: Groq (5 model free tier)
- 22 key Gemini gratis -> Flash 440 RPD, Flash-Lite 11000 RPD
- 7 key Groq gratis (compound 1750 RPD, gpt-oss-*/qwen 7000 RPD)
- 32 task (naik dari 19), sesuai settings.yaml Agustus 2026
- Budget Range Analysis: min viable / optimal knee / premium / max quality

## 1. Parameter Global

- Budget: $100.00/bulan
- Gemini: 22 key gratis (Flash 440 RPD/110 RPM, Flash-Lite 11000 RPD/330 RPM)
- Gemini paid key (Pro): Ya
- Groq: 7 key gratis
- Prescreen pass rate: 45%
- CANDIDATE_POOL: 28 model

## 2. Inventaris Task (32 task)

| Task | Jenis | Runs/hari | Calls/hari | Reasoning | fin_weight | LatSens | Status |
|---|---|---|---|---|---|---|---|
| stage1_shadow_check | single | 4 | 4 | Low | 0.15 | Tidak | Aktif |
| stage1_fundamental | agentic | 4 | 36 | High | 0.35 | Tidak | Aktif |
| stage1_escalation | agentic | 1 | 10 | High | 0.35 | Tidak | Aktif |
| stage2_per_asset_primary | agentic | 11 | 33 | High | 0.45 | Tidak | Aktif |
| stage2_per_asset_secondary | agentic | 4 | 8 | Medium-High | 0.40 | Ya | Aktif |
| stage2_session_trigger | agentic | 3 | 6 | Medium-High | 0.40 | Ya | Aktif |
| stage2_prescreen | single | 32 | 32 | Low | 0.05 | Ya | Aktif |
| stage2_adjudicator | single | 11 | 11 | Medium | 0.30 | Tidak | Aktif |
| specialist_technical | single | 11 | 11 | Medium | 0.15 | Tidak | Aktif |
| specialist_sentiment | single | 11 | 11 | Medium | 0.35 | Tidak | Aktif |
| specialist_macro | single | 11 | 11 | Medium | 0.40 | Tidak | Aktif |
| debate_bull | single | 4 | 4 | Medium | 0.25 | Ya | Aktif |
| debate_bear | single | 4 | 4 | Medium | 0.25 | Ya | Aktif |
| debate_judge | single | 4 | 4 | Medium-High | 0.35 | Ya | Aktif |
| portfolio_synthesis | single | 3 | 3 | Medium-High | 0.35 | Ya | Aktif |
| news_classification | single | 12 | 12 | Low | 0.10 | Tidak | Aktif |
| news_classification_escalation | single | 4 | 4 | Low-Medium | 0.20 | Tidak | Aktif |
| news_classification_verifier | single | 8 | 8 | Low | 0.10 | Tidak | Aktif |
| news_digest | single | 48 | 48 | Low-Medium | 0.20 | Tidak | Aktif |
| news_digest_macro_overview | single | 4 | 4 | Medium | 0.25 | Tidak | Aktif |
| news_digest_verifier | single | 12 | 12 | Low | 0.10 | Tidak | Aktif |
| fundamental_verifier | single | 4 | 4 | Low | 0.25 | Tidak | Aktif |
| cot_precompute | single | 7 | 7 | Low | 0.20 | Tidak | Aktif |
| chat_telegram | agentic | 7 | 14 | Low | 0.05 | Ya | Aktif |
| chat_telegram_medium | agentic | 10 | 20 | Medium | 0.15 | Ya | Aktif |
| chat_telegram_complex | agentic | 13 | 39 | Medium-High | 0.25 | Ya | Aktif |
| trade_reflection | single | 5 | 5 | Low | 0.20 | Tidak | Aktif |
| risk_gate_conservative | single | 0 | 0 | Medium | 0.30 | Ya | Deterministik/Legacy |
| risk_gate_aggressive | single | 0 | 0 | Medium | 0.30 | Ya | Deterministik/Legacy |
| risk_gate_neutral | single | 0 | 0 | Medium | 0.30 | Ya | Deterministik/Legacy |
| portfolio_manager_per_trade | single | 0 | 0 | Low | 0.20 | Tidak | Deterministik/Legacy |
| adversarial_check | single | 0 | 0 | Low | 0.00 | Tidak | Deterministik/Legacy |

**stage1_shadow_check** — Pra-cek sebelum Stage 1

**stage1_fundamental** — Fundamental Brief

**stage1_escalation** — Resolusi ambiguitas makro

**stage2_per_asset_primary** — Analisis terjadwal per aset

**stage2_per_asset_secondary** — Second-opinion reaktif per aset

**stage2_session_trigger** — Analisis reaktif pergantian sesi

**stage2_prescreen** — Gerbang penyaring pra-analisis

**stage2_adjudicator** — SSVP Adjudicator

**specialist_technical** — Konsultan teknikal

**specialist_sentiment** — Konsultan sentimen

**specialist_macro** — Konsultan korelasi makro

**debate_bull** — Bull Advocate

**debate_bear** — Bear Advocate

**debate_judge** — Hakim debat

**portfolio_synthesis** — Manajer Portofolio

**news_classification** — Klasifikasi berita

**news_classification_escalation** — Re-verifikasi berita

**news_classification_verifier** — Verifikasi batas berita

**news_digest** — Intisari berita per mata uang

**news_digest_macro_overview** — Overview makro harian

**news_digest_verifier** — Verifikasi output news digest

**fundamental_verifier** — Verifikasi konsistensi Fundamental Brief

**cot_precompute** — Kalkulator sinyal COT mingguan

**chat_telegram** — Agen Telegram tier dasar

**chat_telegram_medium** — Agen Telegram tier menengah

**chat_telegram_complex** — Agen Telegram tier kompleks

**trade_reflection** — Retrospeksi post-mortem

**risk_gate_conservative** — DETERMINISTIK (runs=0)

**risk_gate_aggressive** — DETERMINISTIK (runs=0)

**risk_gate_neutral** — DETERMINISTIK (runs=0)

**portfolio_manager_per_trade** — DETERMINISTIK (runs=0)

**adversarial_check** — LEGACY (runs=0)

## 3. Budget Range Analysis (UTAMA)

| Tier | Est. Budget/bln | Biaya Terpakai | Skor Kualitas | Deskripsi |
|---|---|---|---|---|
| **Minimum Viable** | ~$20 | $20.09 | 8.31 | Semua floor terpenuhi; model terhemat |
| **Optimal (knee)** | ~$125 | $125.20 | 9.30 | Efisiensi terbaik; delta kualitas/$10 mulai landai |
| **Premium** | ~$250 | $249.88 | 9.61 | Lonjakan kualitas signifikan (+0.3) di atas knee |
| **Max Quality** | ~$300 | $298.75 | 9.66 | Kualitas tertinggi, abaikan biaya |

> **Range budget optimal: $125–$250/bulan** (kualitas 9.30–9.61/10).

## 4. Perbandingan Skenario

| Skenario | Biaya/bln | Skor Kualitas |
|---|---|---|
| Current settings.yaml | $109.85 | 7.60 |
| Termurah lolos floor | $10.96 | 7.54 |
| **Optimal @ $100** | **$99.88** | **9.16** |
| Kualitas maksimum | $474.47 | 9.78 |

## 5. Alokasi Model Optimal @ Budget $100

| Task | Model Terpilih | Kualitas | Fin. Rel | Biaya/bln | Free? |
|---|---|---|---|---|---|
| stage1_shadow_check | Claude/opus-5 | 9.82 | 9.4 | $1.17 | Tidak |
| stage1_fundamental | OpenAI/gpt-5.6-luna | 8.39 | 8.6 | $3.91 | Tidak |
| stage1_escalation | OpenAI/gpt-5.6-luna | 8.39 | 8.6 | $1.12 | Tidak |
| stage2_per_asset_primary | OpenAI/gpt-5.6-luna | 8.41 | 8.6 | $5.93 | Tidak |
| stage2_per_asset_secondary | OpenAI/gpt-5.6-luna | 8.40 | 8.6 | $1.43 | Tidak |
| stage2_session_trigger | OpenAI/gpt-5.6-luna | 8.40 | 8.6 | $0.87 | Tidak |
| stage2_prescreen | Claude/opus-5 | 9.88 | 9.4 | $9.60 | Tidak |
| stage2_adjudicator | Claude/opus-5 | 9.75 | 9.4 | $10.73 | Tidak |
| specialist_technical | Claude/opus-5 | 9.82 | 9.4 | $6.11 | Tidak |
| specialist_sentiment | Claude/opus-5 | 9.72 | 9.4 | $6.11 | Tidak |
| specialist_macro | Claude/opus-5 | 9.70 | 9.4 | $6.11 | Tidak |
| debate_bull | Claude/opus-5 | 9.78 | 9.4 | $1.47 | Tidak |
| debate_bear | Claude/opus-5 | 9.78 | 9.4 | $1.44 | Tidak |
| debate_judge | Claude/opus-5 | 9.72 | 9.4 | $1.08 | Tidak |
| portfolio_synthesis | Claude/opus-5 | 9.72 | 9.4 | $0.95 | Tidak |
| news_classification | Claude/opus-5 | 9.85 | 9.4 | $5.94 | Tidak |
| news_classification_escalation | Claude/opus-5 | 9.80 | 9.4 | $2.10 | Tidak |
| news_classification_verifier | Claude/opus-5 | 9.85 | 9.4 | $2.94 | Tidak |
| news_digest | OpenAI/gpt-5.6-terra | 8.95 | 9.2 | $21.02 | Tidak |
| news_digest_macro_overview | OpenAI/gpt-5.6-luna | 8.36 | 8.6 | $0.31 | Tidak |
| news_digest_verifier | Claude/opus-5 | 9.85 | 9.4 | $2.88 | Tidak |
| fundamental_verifier | OpenAI/gpt-5.6-luna | 8.36 | 8.6 | $0.12 | Tidak |
| cot_precompute | OpenAI/gpt-5.6-luna | 8.35 | 8.6 | $0.16 | Tidak |
| chat_telegram | OpenAI/gpt-5.6-luna | 8.31 | 8.6 | $0.89 | Tidak |
| chat_telegram_medium | OpenAI/gpt-5.6-luna | 8.34 | 8.6 | $1.31 | Tidak |
| chat_telegram_complex | OpenAI/gpt-5.6-luna | 8.36 | 8.6 | $2.61 | Tidak |
| trade_reflection | Claude/opus-5 | 9.80 | 9.4 | $1.57 | Tidak |

**Total: $99.88/bln** (kualitas: 9.16/10)

## 6. Current Settings.yaml — Breakdown Biaya

| Task | Provider/Model | Runs/hari | Biaya/bln | Tipe |
|---|---|---|---|---|
| stage1_shadow_check | Gemini/gemini-3.5-flash | 4 | $0.00 | Free (Gemini) |
| stage1_fundamental | Claude/sonnet-5 | 4 | $18.39 | Berbayar |
| stage1_escalation | Claude/opus-5 | 1 | $13.38 | Berbayar |
| stage2_per_asset_primary | Claude/sonnet-5 | 11 | $39.22 | Berbayar |
| stage2_per_asset_secondary | DeepSeek/deepseek-v4-pro | 4 | $4.40 | Berbayar |
| stage2_session_trigger | Claude/sonnet-5 | 3 | $6.73 | Berbayar |
| stage2_prescreen | Gemini/gemini-3.5-flash-lite | 32 | $0.00 | Free (Gemini) |
| stage2_adjudicator | Gemini/gemini-3.5-flash | 11 | $0.00 | Free (Gemini) |
| specialist_technical | Groq/groq-gpt-oss-120b | 11 | $0.00 | Free (Groq) |
| specialist_sentiment | Gemini/gemini-3.6-flash | 11 | $0.00 | Free (Gemini) |
| specialist_macro | Groq/groq-gpt-oss-120b | 11 | $0.00 | Free (Groq) |
| debate_bull | DeepSeek/deepseek-v4-pro | 4 | $0.15 | Berbayar |
| debate_bear | OpenAI/gpt-5.6-terra | 4 | $0.65 | Berbayar |
| debate_judge | Claude/sonnet-5 | 4 | $0.43 | Berbayar |
| portfolio_synthesis | Claude/sonnet-5 | 3 | $0.38 | Berbayar |
| news_classification | Gemini/gemini-3.5-flash-lite | 12 | $0.00 | Free (Gemini) |
| news_classification_escalation | Groq/groq-gpt-oss-120b | 4 | $0.00 | Free (Groq) |
| news_classification_verifier | Groq/groq-gpt-oss-120b | 8 | $0.00 | Free (Groq) |
| news_digest | DeepSeek/deepseek-v4-pro | 48 | $4.66 | Berbayar |
| news_digest_macro_overview | Claude/sonnet-5 | 4 | $2.76 | Berbayar |
| news_digest_verifier | Gemini/gemini-3.5-flash-lite | 12 | $0.00 | Free (Gemini) |
| fundamental_verifier | Gemini/gemini-3.5-flash | 4 | $0.00 | Free (Gemini) |
| cot_precompute | Gemini/gemini-3.5-flash-lite | 7 | $0.00 | Free (Gemini) |
| chat_telegram | Gemini/gemini-3.5-flash-lite | 7 | $0.00 | Free (Gemini) |
| chat_telegram_medium | Groq/groq-gpt-oss-120b | 10 | $0.00 | Free (Groq) |
| chat_telegram_complex | Claude/sonnet-5 | 13 | $18.06 | Berbayar |
| trade_reflection | Claude/sonnet-5 | 5 | $0.63 | Berbayar |
| risk_gate_conservative | Gemini/gemini-3.5-flash-lite | 0 | $0.00 | Free (Gemini) |
| risk_gate_aggressive | Gemini/gemini-3.5-flash-lite | 0 | $0.00 | Free (Gemini) |
| risk_gate_neutral | Gemini/gemini-3.5-flash-lite | 0 | $0.00 | Free (Gemini) |
| portfolio_manager_per_trade | Gemini/gemini-3.5-flash | 0 | $0.00 | Free (Gemini) |
| adversarial_check | Claude/sonnet-5 | 0 | $0.00 | Deterministik |

**Total current: $109.85/bln** (kualitas: 7.60/10)

## 7. Pemakaian Kuota Free Tier

### Gemini
```
Gemini free tier (22 key):
  flash       :   440/   440 RPD (100.0%)
  flash_lite  :   228/ 11000 RPD (  2.1%)
```

### Groq (per model)
```
Groq free tier (7 key, per model):
  groq-compound         :   226/  1750 RPD ( 12.9%)
  groq-compound-mini    :   150/  1750 RPD (  8.6%)
  groq-gpt-oss-120b     :   226/  7000 RPD (  3.2%) [TPD max 1,400,000]
  groq-gpt-oss-20b      :   150/  7000 RPD (  2.1%) [TPD max 1,400,000]
  groq-qwen3-27b        :   150/  7000 RPD (  2.1%) [TPD max 1,400,000]
```

## 8. Kandidat Model per Task

Floor minimum: High=8.0, Medium-High=7.0, Medium=6.0, Low-Medium=4.5, Low=4.0

### stage1_shadow_check
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.82 | 9.9 | 9.4 | $1.17 | Tidak |
| OpenAI/gpt-5.6-sol | 9.64 | 9.6 | 9.9 | $1.26 | Tidak |
| OpenAI/gpt-5.5-pro | 9.64 | 9.6 | 9.9 | $7.56 | Tidak |
| Claude/fable-5 | 9.63 | 9.7 | 9.2 | $2.34 | Tidak |
| OpenAI/gpt-5.4-pro | 9.44 | 9.4 | 9.7 | $7.56 | Tidak |
| Claude/opus-4.8 | 9.03 | 9.1 | 8.6 | $1.17 | Tidak |
| OpenAI/gpt-5.6-terra | 8.94 | 8.9 | 9.2 | $0.50 | Tidak |
| OpenAI/gpt-5.5 | 8.94 | 8.9 | 9.2 | $1.26 | Tidak |
| Claude/sonnet-5 | 8.83 | 8.9 | 8.5 | $0.47 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.47 | 8.6 | 7.7 | $0.13 | Tidak |
| OpenAI/gpt-5.4 | 8.44 | 8.4 | 8.7 | $0.63 | Tidak |
| OpenAI/gpt-5.6-luna | 8.34 | 8.3 | 8.6 | $0.05 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.98 | 8.1 | 7.3 | $0.04 | Tidak |
| Gemini/gemini-3.6-flash | 7.83 | 8.1 | 6.3 | $0.35 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.83 | 8.1 | 6.3 | $0.38 | Ya (flash) |
| Claude/sonnet-4.6 | 7.54 | 7.6 | 7.2 | $0.70 | Tidak |
| Gemini/gemini-3.1-pro | 7.54 | 7.8 | 6.1 | $0.50 | Tidak |
| Groq/groq-compound | 6.86 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.53 | 6.5 | 6.7 | $0.19 | Tidak |
| Groq/groq-gpt-oss-120b | 6.37 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.23 | 6.2 | 6.4 | $0.05 | Tidak |
| Gemini/gemini-3.0-flash-preview | 6.00 | 6.2 | 4.8 | $0.13 | Ya (flash) |
| Gemini/gemini-3.5-flash-lite | 5.80 | 6.0 | 4.7 | $0.09 | Ya (flash_lite) |
| Groq/groq-qwen3-27b | 5.59 | 5.7 | 5.0 | $0.00 | Ya (Groq) |
| Groq/groq-compound-mini | 5.20 | 5.3 | 4.6 | $0.00 | Ya (Groq) |
| Claude/haiku-4.5 | 4.86 | 4.9 | 4.7 | $0.23 | Tidak |
| Groq/groq-gpt-oss-20b | 4.71 | 4.8 | 4.2 | $0.00 | Ya (Groq) |

### stage1_fundamental
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.72 | 9.9 | 9.4 | $45.97 | Tidak |
| OpenAI/gpt-5.6-sol | 9.70 | 9.6 | 9.9 | $97.74 | Tidak |
| OpenAI/gpt-5.5-pro | 9.70 | 9.6 | 9.9 | $586.44 | Tidak |
| Claude/fable-5 | 9.53 | 9.7 | 9.2 | $91.94 | Tidak |
| OpenAI/gpt-5.4-pro | 9.50 | 9.4 | 9.7 | $586.44 | Tidak |
| OpenAI/gpt-5.6-terra | 8.99 | 8.9 | 9.2 | $39.10 | Tidak |
| OpenAI/gpt-5.5 | 8.99 | 8.9 | 9.2 | $97.74 | Tidak |
| Claude/opus-4.8 | 8.94 | 9.1 | 8.6 | $45.97 | Tidak |
| Claude/sonnet-5 | 8.75 | 8.9 | 8.5 | $18.39 | Tidak |
| OpenAI/gpt-5.4 | 8.49 | 8.4 | 8.7 | $48.87 | Tidak |
| OpenAI/gpt-5.6-luna | 8.39 | 8.3 | 8.6 | $3.91 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.30 | 8.6 | 7.7 | $12.22 | Tidak |

### stage1_escalation
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.72 | 9.9 | 9.4 | $13.38 | Tidak |
| OpenAI/gpt-5.6-sol | 9.70 | 9.6 | 9.9 | $27.98 | Tidak |
| OpenAI/gpt-5.5-pro | 9.70 | 9.6 | 9.9 | $167.85 | Tidak |
| Claude/fable-5 | 9.53 | 9.7 | 9.2 | $26.76 | Tidak |
| OpenAI/gpt-5.4-pro | 9.50 | 9.4 | 9.7 | $167.85 | Tidak |
| OpenAI/gpt-5.6-terra | 8.99 | 8.9 | 9.2 | $11.19 | Tidak |
| OpenAI/gpt-5.5 | 8.99 | 8.9 | 9.2 | $27.98 | Tidak |
| Claude/opus-4.8 | 8.94 | 9.1 | 8.6 | $13.38 | Tidak |
| Claude/sonnet-5 | 8.75 | 8.9 | 8.5 | $5.35 | Tidak |
| OpenAI/gpt-5.4 | 8.49 | 8.4 | 8.7 | $13.99 | Tidak |
| OpenAI/gpt-5.6-luna | 8.39 | 8.3 | 8.6 | $1.12 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.30 | 8.6 | 7.7 | $3.51 | Tidak |

### stage2_per_asset_primary
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| OpenAI/gpt-5.6-sol | 9.73 | 9.6 | 9.9 | $148.25 | Tidak |
| OpenAI/gpt-5.5-pro | 9.73 | 9.6 | 9.9 | $889.51 | Tidak |
| Claude/opus-5 | 9.68 | 9.9 | 9.4 | $98.05 | Tidak |
| OpenAI/gpt-5.4-pro | 9.53 | 9.4 | 9.7 | $889.51 | Tidak |
| Claude/fable-5 | 9.48 | 9.7 | 9.2 | $196.10 | Tidak |
| OpenAI/gpt-5.6-terra | 9.02 | 8.9 | 9.2 | $59.30 | Tidak |
| OpenAI/gpt-5.5 | 9.02 | 8.9 | 9.2 | $148.25 | Tidak |
| Claude/opus-4.8 | 8.89 | 9.1 | 8.6 | $98.05 | Tidak |
| Claude/sonnet-5 | 8.70 | 8.9 | 8.5 | $39.22 | Tidak |
| OpenAI/gpt-5.4 | 8.51 | 8.4 | 8.7 | $74.13 | Tidak |
| OpenAI/gpt-5.6-luna | 8.41 | 8.3 | 8.6 | $5.93 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.21 | 8.6 | 7.7 | $18.43 | Tidak |

### stage2_per_asset_secondary
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| OpenAI/gpt-5.6-sol | 9.72 | 9.6 | 9.9 | $35.85 | Tidak |
| OpenAI/gpt-5.5-pro | 9.72 | 9.6 | 9.9 | $215.10 | Tidak |
| Claude/opus-5 | 9.70 | 9.9 | 9.4 | $27.79 | Tidak |
| OpenAI/gpt-5.4-pro | 9.51 | 9.4 | 9.7 | $215.10 | Tidak |
| Claude/fable-5 | 9.50 | 9.7 | 9.2 | $55.59 | Tidak |
| OpenAI/gpt-5.6-terra | 9.01 | 8.9 | 9.2 | $14.34 | Tidak |
| OpenAI/gpt-5.5 | 9.01 | 8.9 | 9.2 | $35.85 | Tidak |
| Claude/opus-4.8 | 8.92 | 9.1 | 8.6 | $27.79 | Tidak |
| Claude/sonnet-5 | 8.72 | 8.9 | 8.5 | $11.12 | Tidak |
| OpenAI/gpt-5.4 | 8.50 | 8.4 | 8.7 | $17.93 | Tidak |
| OpenAI/gpt-5.6-luna | 8.40 | 8.3 | 8.6 | $1.43 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.26 | 8.6 | 7.7 | $4.40 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.78 | 8.1 | 7.3 | $1.47 | Tidak |
| Claude/sonnet-4.6 | 7.45 | 7.6 | 7.2 | $16.68 | Tidak |
| Gemini/gemini-3.6-flash | 7.39 | 8.1 | 6.3 | $10.50 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.39 | 8.1 | 6.3 | $10.75 | Ya (flash) |
| Gemini/gemini-3.1-pro | 7.11 | 7.8 | 6.1 | $14.34 | Tidak |

### stage2_session_trigger
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| OpenAI/gpt-5.6-sol | 9.72 | 9.6 | 9.9 | $21.80 | Tidak |
| OpenAI/gpt-5.5-pro | 9.72 | 9.6 | 9.9 | $130.81 | Tidak |
| Claude/opus-5 | 9.70 | 9.9 | 9.4 | $16.83 | Tidak |
| OpenAI/gpt-5.4-pro | 9.51 | 9.4 | 9.7 | $130.81 | Tidak |
| Claude/fable-5 | 9.50 | 9.7 | 9.2 | $33.66 | Tidak |
| OpenAI/gpt-5.6-terra | 9.01 | 8.9 | 9.2 | $8.72 | Tidak |
| OpenAI/gpt-5.5 | 9.01 | 8.9 | 9.2 | $21.80 | Tidak |
| Claude/opus-4.8 | 8.92 | 9.1 | 8.6 | $16.83 | Tidak |
| Claude/sonnet-5 | 8.72 | 8.9 | 8.5 | $6.73 | Tidak |
| OpenAI/gpt-5.4 | 8.50 | 8.4 | 8.7 | $10.90 | Tidak |
| OpenAI/gpt-5.6-luna | 8.40 | 8.3 | 8.6 | $0.87 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.26 | 8.6 | 7.7 | $2.65 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.78 | 8.1 | 7.3 | $0.88 | Tidak |
| Claude/sonnet-4.6 | 7.45 | 7.6 | 7.2 | $10.10 | Tidak |
| Gemini/gemini-3.6-flash | 7.39 | 8.1 | 6.3 | $6.37 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.39 | 8.1 | 6.3 | $6.54 | Ya (flash) |
| Gemini/gemini-3.1-pro | 7.11 | 7.8 | 6.1 | $8.72 | Tidak |

### stage2_prescreen
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.88 | 9.9 | 9.4 | $9.60 | Tidak |
| Claude/fable-5 | 9.68 | 9.7 | 9.2 | $19.20 | Tidak |
| OpenAI/gpt-5.6-sol | 9.61 | 9.6 | 9.9 | $10.08 | Tidak |
| OpenAI/gpt-5.5-pro | 9.61 | 9.6 | 9.9 | $60.48 | Tidak |
| OpenAI/gpt-5.4-pro | 9.41 | 9.4 | 9.7 | $60.48 | Tidak |
| Claude/opus-4.8 | 9.08 | 9.1 | 8.6 | $9.60 | Tidak |
| OpenAI/gpt-5.6-terra | 8.91 | 8.9 | 9.2 | $4.03 | Tidak |
| OpenAI/gpt-5.5 | 8.91 | 8.9 | 9.2 | $10.08 | Tidak |
| Claude/sonnet-5 | 8.88 | 8.9 | 8.5 | $3.84 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.56 | 8.6 | 7.7 | $1.14 | Tidak |
| OpenAI/gpt-5.4 | 8.41 | 8.4 | 8.7 | $5.04 | Tidak |
| OpenAI/gpt-5.6-luna | 8.31 | 8.3 | 8.6 | $0.40 | Tidak |
| DeepSeek/deepseek-v4-flash | 8.06 | 8.1 | 7.3 | $0.38 | Tidak |
| Gemini/gemini-3.6-flash | 8.01 | 8.1 | 6.3 | $2.88 | Ya (flash) |
| Gemini/gemini-3.5-flash | 8.01 | 8.1 | 6.3 | $3.02 | Ya (flash) |
| Gemini/gemini-3.1-pro | 7.71 | 7.8 | 6.1 | $4.03 | Tidak |
| Claude/sonnet-4.6 | 7.58 | 7.6 | 7.2 | $5.76 | Tidak |
| Groq/groq-compound | 6.95 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.51 | 6.5 | 6.7 | $1.51 | Tidak |
| Groq/groq-gpt-oss-120b | 6.46 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.21 | 6.2 | 6.4 | $0.41 | Tidak |
| Gemini/gemini-3.0-flash-preview | 6.13 | 6.2 | 4.8 | $1.01 | Ya (flash) |
| Gemini/gemini-3.5-flash-lite | 5.93 | 6.0 | 4.7 | $0.67 | Ya (flash_lite) |
| Groq/groq-qwen3-27b | 5.66 | 5.7 | 5.0 | $0.00 | Ya (Groq) |
| Groq/groq-compound-mini | 5.26 | 5.3 | 4.6 | $0.00 | Ya (Groq) |
| Claude/haiku-4.5 | 4.89 | 4.9 | 4.7 | $1.92 | Tidak |
| Groq/groq-gpt-oss-20b | 4.77 | 4.8 | 4.2 | $0.00 | Ya (Groq) |
| Gemini/gemini-3.1-flash-lite | 4.05 | 4.1 | 3.2 | $0.50 | Ya (flash_lite) |

### stage2_adjudicator
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.75 | 9.9 | 9.4 | $10.73 | Tidak |
| OpenAI/gpt-5.6-sol | 9.69 | 9.6 | 9.9 | $11.72 | Tidak |
| OpenAI/gpt-5.5-pro | 9.69 | 9.6 | 9.9 | $70.29 | Tidak |
| Claude/fable-5 | 9.55 | 9.7 | 9.2 | $21.45 | Tidak |
| OpenAI/gpt-5.4-pro | 9.48 | 9.4 | 9.7 | $70.29 | Tidak |
| OpenAI/gpt-5.6-terra | 8.98 | 8.9 | 9.2 | $4.69 | Tidak |
| OpenAI/gpt-5.5 | 8.98 | 8.9 | 9.2 | $11.72 | Tidak |
| Claude/opus-4.8 | 8.96 | 9.1 | 8.6 | $10.73 | Tidak |
| Claude/sonnet-5 | 8.77 | 8.9 | 8.5 | $4.29 | Tidak |
| OpenAI/gpt-5.4 | 8.47 | 8.4 | 8.7 | $5.86 | Tidak |
| OpenAI/gpt-5.6-luna | 8.38 | 8.3 | 8.6 | $0.47 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.34 | 8.6 | 7.7 | $1.15 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.86 | 8.1 | 7.3 | $0.38 | Tidak |
| Gemini/gemini-3.6-flash | 7.57 | 8.1 | 6.3 | $3.22 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.57 | 8.1 | 6.3 | $3.51 | Ya (flash) |
| Claude/sonnet-4.6 | 7.49 | 7.6 | 7.2 | $6.43 | Tidak |
| Gemini/gemini-3.1-pro | 7.28 | 7.8 | 6.1 | $4.69 | Tidak |
| Groq/groq-compound | 6.73 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.56 | 6.5 | 6.7 | $1.76 | Tidak |
| OpenAI/gpt-5.4-nano | 6.26 | 6.2 | 6.4 | $0.48 | Tidak |
| Groq/groq-gpt-oss-120b | 6.25 | 6.5 | 5.7 | $0.00 | Ya (Groq) |

### specialist_technical
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.82 | 9.9 | 9.4 | $6.11 | Tidak |
| OpenAI/gpt-5.6-sol | 9.64 | 9.6 | 9.9 | $6.60 | Tidak |
| OpenAI/gpt-5.5-pro | 9.64 | 9.6 | 9.9 | $39.60 | Tidak |
| Claude/fable-5 | 9.63 | 9.7 | 9.2 | $12.21 | Tidak |
| OpenAI/gpt-5.4-pro | 9.44 | 9.4 | 9.7 | $39.60 | Tidak |
| Claude/opus-4.8 | 9.03 | 9.1 | 8.6 | $6.11 | Tidak |
| OpenAI/gpt-5.6-terra | 8.94 | 8.9 | 9.2 | $2.64 | Tidak |
| OpenAI/gpt-5.5 | 8.94 | 8.9 | 9.2 | $6.60 | Tidak |
| Claude/sonnet-5 | 8.83 | 8.9 | 8.5 | $2.44 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.47 | 8.6 | 7.7 | $0.68 | Tidak |
| OpenAI/gpt-5.4 | 8.44 | 8.4 | 8.7 | $3.30 | Tidak |
| OpenAI/gpt-5.6-luna | 8.34 | 8.3 | 8.6 | $0.26 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.98 | 8.1 | 7.3 | $0.23 | Tidak |
| Gemini/gemini-3.6-flash | 7.83 | 8.1 | 6.3 | $1.83 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.83 | 8.1 | 6.3 | $1.98 | Ya (flash) |
| Claude/sonnet-4.6 | 7.54 | 7.6 | 7.2 | $3.66 | Tidak |
| Gemini/gemini-3.1-pro | 7.54 | 7.8 | 6.1 | $2.64 | Tidak |
| Groq/groq-compound | 6.86 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.53 | 6.5 | 6.7 | $0.99 | Tidak |
| Groq/groq-gpt-oss-120b | 6.37 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.23 | 6.2 | 6.4 | $0.27 | Tidak |

### specialist_sentiment
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.72 | 9.9 | 9.4 | $6.11 | Tidak |
| OpenAI/gpt-5.6-sol | 9.70 | 9.6 | 9.9 | $6.60 | Tidak |
| OpenAI/gpt-5.5-pro | 9.70 | 9.6 | 9.9 | $39.60 | Tidak |
| Claude/fable-5 | 9.53 | 9.7 | 9.2 | $12.21 | Tidak |
| OpenAI/gpt-5.4-pro | 9.50 | 9.4 | 9.7 | $39.60 | Tidak |
| OpenAI/gpt-5.6-terra | 8.99 | 8.9 | 9.2 | $2.64 | Tidak |
| OpenAI/gpt-5.5 | 8.99 | 8.9 | 9.2 | $6.60 | Tidak |
| Claude/opus-4.8 | 8.94 | 9.1 | 8.6 | $6.11 | Tidak |
| Claude/sonnet-5 | 8.75 | 8.9 | 8.5 | $2.44 | Tidak |
| OpenAI/gpt-5.4 | 8.49 | 8.4 | 8.7 | $3.30 | Tidak |
| OpenAI/gpt-5.6-luna | 8.39 | 8.3 | 8.6 | $0.26 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.30 | 8.6 | 7.7 | $0.68 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.82 | 8.1 | 7.3 | $0.23 | Tidak |
| Gemini/gemini-3.6-flash | 7.48 | 8.1 | 6.3 | $1.83 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.48 | 8.1 | 6.3 | $1.98 | Ya (flash) |
| Claude/sonnet-4.6 | 7.47 | 7.6 | 7.2 | $3.66 | Tidak |
| Gemini/gemini-3.1-pro | 7.20 | 7.8 | 6.1 | $2.64 | Tidak |
| Groq/groq-compound | 6.68 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.57 | 6.5 | 6.7 | $0.99 | Tidak |
| OpenAI/gpt-5.4-nano | 6.27 | 6.2 | 6.4 | $0.27 | Tidak |
| Groq/groq-gpt-oss-120b | 6.21 | 6.5 | 5.7 | $0.00 | Ya (Groq) |

### specialist_macro
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| OpenAI/gpt-5.6-sol | 9.72 | 9.6 | 9.9 | $6.60 | Tidak |
| OpenAI/gpt-5.5-pro | 9.72 | 9.6 | 9.9 | $39.60 | Tidak |
| Claude/opus-5 | 9.70 | 9.9 | 9.4 | $6.11 | Tidak |
| OpenAI/gpt-5.4-pro | 9.51 | 9.4 | 9.7 | $39.60 | Tidak |
| Claude/fable-5 | 9.50 | 9.7 | 9.2 | $12.21 | Tidak |
| OpenAI/gpt-5.6-terra | 9.01 | 8.9 | 9.2 | $2.64 | Tidak |
| OpenAI/gpt-5.5 | 9.01 | 8.9 | 9.2 | $6.60 | Tidak |
| Claude/opus-4.8 | 8.92 | 9.1 | 8.6 | $6.11 | Tidak |
| Claude/sonnet-5 | 8.72 | 8.9 | 8.5 | $2.44 | Tidak |
| OpenAI/gpt-5.4 | 8.50 | 8.4 | 8.7 | $3.30 | Tidak |
| OpenAI/gpt-5.6-luna | 8.40 | 8.3 | 8.6 | $0.26 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.26 | 8.6 | 7.7 | $0.68 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.78 | 8.1 | 7.3 | $0.23 | Tidak |
| Claude/sonnet-4.6 | 7.45 | 7.6 | 7.2 | $3.66 | Tidak |
| Gemini/gemini-3.6-flash | 7.39 | 8.1 | 6.3 | $1.83 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.39 | 8.1 | 6.3 | $1.98 | Ya (flash) |
| Gemini/gemini-3.1-pro | 7.11 | 7.8 | 6.1 | $2.64 | Tidak |
| Groq/groq-compound | 6.64 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.58 | 6.5 | 6.7 | $0.99 | Tidak |
| OpenAI/gpt-5.4-nano | 6.28 | 6.2 | 6.4 | $0.27 | Tidak |
| Groq/groq-gpt-oss-120b | 6.16 | 6.5 | 5.7 | $0.00 | Ya (Groq) |

### debate_bull
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.78 | 9.9 | 9.4 | $1.47 | Tidak |
| OpenAI/gpt-5.6-sol | 9.67 | 9.6 | 9.9 | $1.62 | Tidak |
| OpenAI/gpt-5.5-pro | 9.67 | 9.6 | 9.9 | $9.72 | Tidak |
| Claude/fable-5 | 9.58 | 9.7 | 9.2 | $2.94 | Tidak |
| OpenAI/gpt-5.4-pro | 9.47 | 9.4 | 9.7 | $9.72 | Tidak |
| Claude/opus-4.8 | 8.98 | 9.1 | 8.6 | $1.47 | Tidak |
| OpenAI/gpt-5.6-terra | 8.97 | 8.9 | 9.2 | $0.65 | Tidak |
| OpenAI/gpt-5.5 | 8.97 | 8.9 | 9.2 | $1.62 | Tidak |
| Claude/sonnet-5 | 8.79 | 8.9 | 8.5 | $0.59 | Tidak |
| OpenAI/gpt-5.4 | 8.46 | 8.4 | 8.7 | $0.81 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.38 | 8.6 | 7.7 | $0.15 | Tidak |
| OpenAI/gpt-5.6-luna | 8.36 | 8.3 | 8.6 | $0.06 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.90 | 8.1 | 7.3 | $0.05 | Tidak |
| Gemini/gemini-3.6-flash | 7.66 | 8.1 | 6.3 | $0.44 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.66 | 8.1 | 6.3 | $0.49 | Ya (flash) |
| Claude/sonnet-4.6 | 7.50 | 7.6 | 7.2 | $0.88 | Tidak |
| Gemini/gemini-3.1-pro | 7.37 | 7.8 | 6.1 | $0.65 | Tidak |
| Groq/groq-compound | 6.77 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.55 | 6.5 | 6.7 | $0.24 | Tidak |
| Groq/groq-gpt-oss-120b | 6.29 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.25 | 6.2 | 6.4 | $0.07 | Tidak |

### debate_bear
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.78 | 9.9 | 9.4 | $1.44 | Tidak |
| OpenAI/gpt-5.6-sol | 9.67 | 9.6 | 9.9 | $1.62 | Tidak |
| OpenAI/gpt-5.5-pro | 9.67 | 9.6 | 9.9 | $9.72 | Tidak |
| Claude/fable-5 | 9.58 | 9.7 | 9.2 | $2.88 | Tidak |
| OpenAI/gpt-5.4-pro | 9.47 | 9.4 | 9.7 | $9.72 | Tidak |
| Claude/opus-4.8 | 8.98 | 9.1 | 8.6 | $1.44 | Tidak |
| OpenAI/gpt-5.6-terra | 8.97 | 8.9 | 9.2 | $0.65 | Tidak |
| OpenAI/gpt-5.5 | 8.97 | 8.9 | 9.2 | $1.62 | Tidak |
| Claude/sonnet-5 | 8.79 | 8.9 | 8.5 | $0.58 | Tidak |
| OpenAI/gpt-5.4 | 8.46 | 8.4 | 8.7 | $0.81 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.38 | 8.6 | 7.7 | $0.14 | Tidak |
| OpenAI/gpt-5.6-luna | 8.36 | 8.3 | 8.6 | $0.06 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.90 | 8.1 | 7.3 | $0.05 | Tidak |
| Gemini/gemini-3.6-flash | 7.66 | 8.1 | 6.3 | $0.43 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.66 | 8.1 | 6.3 | $0.49 | Ya (flash) |
| Claude/sonnet-4.6 | 7.50 | 7.6 | 7.2 | $0.86 | Tidak |
| Gemini/gemini-3.1-pro | 7.37 | 7.8 | 6.1 | $0.65 | Tidak |
| Groq/groq-compound | 6.77 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.55 | 6.5 | 6.7 | $0.24 | Tidak |
| Groq/groq-gpt-oss-120b | 6.29 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.25 | 6.2 | 6.4 | $0.07 | Tidak |

### debate_judge
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.72 | 9.9 | 9.4 | $1.08 | Tidak |
| OpenAI/gpt-5.6-sol | 9.70 | 9.6 | 9.9 | $1.19 | Tidak |
| OpenAI/gpt-5.5-pro | 9.70 | 9.6 | 9.9 | $7.13 | Tidak |
| Claude/fable-5 | 9.53 | 9.7 | 9.2 | $2.16 | Tidak |
| OpenAI/gpt-5.4-pro | 9.50 | 9.4 | 9.7 | $7.13 | Tidak |
| OpenAI/gpt-5.6-terra | 8.99 | 8.9 | 9.2 | $0.48 | Tidak |
| OpenAI/gpt-5.5 | 8.99 | 8.9 | 9.2 | $1.19 | Tidak |
| Claude/opus-4.8 | 8.94 | 9.1 | 8.6 | $1.08 | Tidak |
| Claude/sonnet-5 | 8.75 | 8.9 | 8.5 | $0.43 | Tidak |
| OpenAI/gpt-5.4 | 8.49 | 8.4 | 8.7 | $0.59 | Tidak |
| OpenAI/gpt-5.6-luna | 8.39 | 8.3 | 8.6 | $0.05 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.30 | 8.6 | 7.7 | $0.11 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.82 | 8.1 | 7.3 | $0.04 | Tidak |
| Gemini/gemini-3.6-flash | 7.48 | 8.1 | 6.3 | $0.32 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.48 | 8.1 | 6.3 | $0.36 | Ya (flash) |
| Claude/sonnet-4.6 | 7.47 | 7.6 | 7.2 | $0.65 | Tidak |
| Gemini/gemini-3.1-pro | 7.20 | 7.8 | 6.1 | $0.48 | Tidak |

### portfolio_synthesis
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.72 | 9.9 | 9.4 | $0.95 | Tidak |
| OpenAI/gpt-5.6-sol | 9.70 | 9.6 | 9.9 | $1.04 | Tidak |
| OpenAI/gpt-5.5-pro | 9.70 | 9.6 | 9.9 | $6.21 | Tidak |
| Claude/fable-5 | 9.53 | 9.7 | 9.2 | $1.89 | Tidak |
| OpenAI/gpt-5.4-pro | 9.50 | 9.4 | 9.7 | $6.21 | Tidak |
| OpenAI/gpt-5.6-terra | 8.99 | 8.9 | 9.2 | $0.41 | Tidak |
| OpenAI/gpt-5.5 | 8.99 | 8.9 | 9.2 | $1.04 | Tidak |
| Claude/opus-4.8 | 8.94 | 9.1 | 8.6 | $0.95 | Tidak |
| Claude/sonnet-5 | 8.75 | 8.9 | 8.5 | $0.38 | Tidak |
| OpenAI/gpt-5.4 | 8.49 | 8.4 | 8.7 | $0.52 | Tidak |
| OpenAI/gpt-5.6-luna | 8.39 | 8.3 | 8.6 | $0.04 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.30 | 8.6 | 7.7 | $0.10 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.82 | 8.1 | 7.3 | $0.03 | Tidak |
| Gemini/gemini-3.6-flash | 7.48 | 8.1 | 6.3 | $0.28 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.48 | 8.1 | 6.3 | $0.31 | Ya (flash) |
| Claude/sonnet-4.6 | 7.47 | 7.6 | 7.2 | $0.57 | Tidak |
| Gemini/gemini-3.1-pro | 7.20 | 7.8 | 6.1 | $0.41 | Tidak |

### news_classification
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.85 | 9.9 | 9.4 | $5.94 | Tidak |
| Claude/fable-5 | 9.65 | 9.7 | 9.2 | $11.88 | Tidak |
| OpenAI/gpt-5.6-sol | 9.63 | 9.6 | 9.9 | $6.84 | Tidak |
| OpenAI/gpt-5.5-pro | 9.63 | 9.6 | 9.9 | $41.04 | Tidak |
| OpenAI/gpt-5.4-pro | 9.43 | 9.4 | 9.7 | $41.04 | Tidak |
| Claude/opus-4.8 | 9.05 | 9.1 | 8.6 | $5.94 | Tidak |
| OpenAI/gpt-5.6-terra | 8.93 | 8.9 | 9.2 | $2.74 | Tidak |
| OpenAI/gpt-5.5 | 8.93 | 8.9 | 9.2 | $6.84 | Tidak |
| Claude/sonnet-5 | 8.86 | 8.9 | 8.5 | $2.38 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.51 | 8.6 | 7.7 | $0.55 | Tidak |
| OpenAI/gpt-5.4 | 8.43 | 8.4 | 8.7 | $3.42 | Tidak |
| OpenAI/gpt-5.6-luna | 8.32 | 8.3 | 8.6 | $0.27 | Tidak |
| DeepSeek/deepseek-v4-flash | 8.02 | 8.1 | 7.3 | $0.18 | Tidak |
| Gemini/gemini-3.6-flash | 7.92 | 8.1 | 6.3 | $1.78 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.92 | 8.1 | 6.3 | $2.05 | Ya (flash) |
| Gemini/gemini-3.1-pro | 7.63 | 7.8 | 6.1 | $2.74 | Tidak |
| Claude/sonnet-4.6 | 7.56 | 7.6 | 7.2 | $3.56 | Tidak |
| Groq/groq-compound | 6.91 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.52 | 6.5 | 6.7 | $1.03 | Tidak |
| Groq/groq-gpt-oss-120b | 6.42 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.22 | 6.2 | 6.4 | $0.28 | Tidak |
| Gemini/gemini-3.0-flash-preview | 6.06 | 6.2 | 4.8 | $0.68 | Ya (flash) |
| Gemini/gemini-3.5-flash-lite | 5.87 | 6.0 | 4.7 | $0.54 | Ya (flash_lite) |
| Groq/groq-qwen3-27b | 5.63 | 5.7 | 5.0 | $0.00 | Ya (Groq) |
| Groq/groq-compound-mini | 5.23 | 5.3 | 4.6 | $0.00 | Ya (Groq) |
| Claude/haiku-4.5 | 4.88 | 4.9 | 4.7 | $1.19 | Tidak |
| Groq/groq-gpt-oss-20b | 4.74 | 4.8 | 4.2 | $0.00 | Ya (Groq) |
| Gemini/gemini-3.1-flash-lite | 4.01 | 4.1 | 3.2 | $0.34 | Ya (flash_lite) |

### news_classification_escalation
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.80 | 9.9 | 9.4 | $2.10 | Tidak |
| OpenAI/gpt-5.6-sol | 9.66 | 9.6 | 9.9 | $2.40 | Tidak |
| OpenAI/gpt-5.5-pro | 9.66 | 9.6 | 9.9 | $14.40 | Tidak |
| Claude/fable-5 | 9.60 | 9.7 | 9.2 | $4.20 | Tidak |
| OpenAI/gpt-5.4-pro | 9.46 | 9.4 | 9.7 | $14.40 | Tidak |
| Claude/opus-4.8 | 9.01 | 9.1 | 8.6 | $2.10 | Tidak |
| OpenAI/gpt-5.6-terra | 8.95 | 8.9 | 9.2 | $0.96 | Tidak |
| OpenAI/gpt-5.5 | 8.95 | 8.9 | 9.2 | $2.40 | Tidak |
| Claude/sonnet-5 | 8.81 | 8.9 | 8.5 | $0.84 | Tidak |
| OpenAI/gpt-5.4 | 8.45 | 8.4 | 8.7 | $1.20 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.43 | 8.6 | 7.7 | $0.20 | Tidak |
| OpenAI/gpt-5.6-luna | 8.35 | 8.3 | 8.6 | $0.10 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.94 | 8.1 | 7.3 | $0.07 | Tidak |
| Gemini/gemini-3.6-flash | 7.74 | 8.1 | 6.3 | $0.63 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.74 | 8.1 | 6.3 | $0.72 | Ya (flash) |
| Claude/sonnet-4.6 | 7.52 | 7.6 | 7.2 | $1.26 | Tidak |
| Gemini/gemini-3.1-pro | 7.46 | 7.8 | 6.1 | $0.96 | Tidak |
| Groq/groq-compound | 6.82 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.54 | 6.5 | 6.7 | $0.36 | Tidak |
| Groq/groq-gpt-oss-120b | 6.33 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.24 | 6.2 | 6.4 | $0.10 | Tidak |
| Gemini/gemini-3.0-flash-preview | 5.93 | 6.2 | 4.8 | $0.24 | Ya (flash) |
| Gemini/gemini-3.5-flash-lite | 5.74 | 6.0 | 4.7 | $0.19 | Ya (flash_lite) |
| Groq/groq-qwen3-27b | 5.55 | 5.7 | 5.0 | $0.00 | Ya (Groq) |
| Groq/groq-compound-mini | 5.16 | 5.3 | 4.6 | $0.00 | Ya (Groq) |
| Claude/haiku-4.5 | 4.85 | 4.9 | 4.7 | $0.42 | Tidak |
| Groq/groq-gpt-oss-20b | 4.68 | 4.8 | 4.2 | $0.00 | Ya (Groq) |

### news_classification_verifier
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.85 | 9.9 | 9.4 | $2.94 | Tidak |
| Claude/fable-5 | 9.65 | 9.7 | 9.2 | $5.88 | Tidak |
| OpenAI/gpt-5.6-sol | 9.63 | 9.6 | 9.9 | $3.36 | Tidak |
| OpenAI/gpt-5.5-pro | 9.63 | 9.6 | 9.9 | $20.16 | Tidak |
| OpenAI/gpt-5.4-pro | 9.43 | 9.4 | 9.7 | $20.16 | Tidak |
| Claude/opus-4.8 | 9.05 | 9.1 | 8.6 | $2.94 | Tidak |
| OpenAI/gpt-5.6-terra | 8.93 | 8.9 | 9.2 | $1.34 | Tidak |
| OpenAI/gpt-5.5 | 8.93 | 8.9 | 9.2 | $3.36 | Tidak |
| Claude/sonnet-5 | 8.86 | 8.9 | 8.5 | $1.18 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.51 | 8.6 | 7.7 | $0.28 | Tidak |
| OpenAI/gpt-5.4 | 8.43 | 8.4 | 8.7 | $1.68 | Tidak |
| OpenAI/gpt-5.6-luna | 8.32 | 8.3 | 8.6 | $0.13 | Tidak |
| DeepSeek/deepseek-v4-flash | 8.02 | 8.1 | 7.3 | $0.09 | Tidak |
| Gemini/gemini-3.6-flash | 7.92 | 8.1 | 6.3 | $0.88 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.92 | 8.1 | 6.3 | $1.01 | Ya (flash) |
| Gemini/gemini-3.1-pro | 7.63 | 7.8 | 6.1 | $1.34 | Tidak |
| Claude/sonnet-4.6 | 7.56 | 7.6 | 7.2 | $1.76 | Tidak |
| Groq/groq-compound | 6.91 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.52 | 6.5 | 6.7 | $0.50 | Tidak |
| Groq/groq-gpt-oss-120b | 6.42 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.22 | 6.2 | 6.4 | $0.14 | Tidak |
| Gemini/gemini-3.0-flash-preview | 6.06 | 6.2 | 4.8 | $0.34 | Ya (flash) |
| Gemini/gemini-3.5-flash-lite | 5.87 | 6.0 | 4.7 | $0.26 | Ya (flash_lite) |
| Groq/groq-qwen3-27b | 5.63 | 5.7 | 5.0 | $0.00 | Ya (Groq) |
| Groq/groq-compound-mini | 5.23 | 5.3 | 4.6 | $0.00 | Ya (Groq) |
| Claude/haiku-4.5 | 4.88 | 4.9 | 4.7 | $0.59 | Tidak |
| Groq/groq-gpt-oss-20b | 4.74 | 4.8 | 4.2 | $0.00 | Ya (Groq) |
| Gemini/gemini-3.1-flash-lite | 4.01 | 4.1 | 3.2 | $0.17 | Ya (flash_lite) |

### news_digest
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.80 | 9.9 | 9.4 | $46.80 | Tidak |
| OpenAI/gpt-5.6-sol | 9.66 | 9.6 | 9.9 | $52.56 | Tidak |
| OpenAI/gpt-5.5-pro | 9.66 | 9.6 | 9.9 | $315.36 | Tidak |
| Claude/fable-5 | 9.60 | 9.7 | 9.2 | $93.60 | Tidak |
| OpenAI/gpt-5.4-pro | 9.46 | 9.4 | 9.7 | $315.36 | Tidak |
| Claude/opus-4.8 | 9.01 | 9.1 | 8.6 | $46.80 | Tidak |
| OpenAI/gpt-5.6-terra | 8.95 | 8.9 | 9.2 | $21.02 | Tidak |
| OpenAI/gpt-5.5 | 8.95 | 8.9 | 9.2 | $52.56 | Tidak |
| Claude/sonnet-5 | 8.81 | 8.9 | 8.5 | $18.72 | Tidak |
| OpenAI/gpt-5.4 | 8.45 | 8.4 | 8.7 | $26.28 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.43 | 8.6 | 7.7 | $4.66 | Tidak |
| OpenAI/gpt-5.6-luna | 8.35 | 8.3 | 8.6 | $2.10 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.94 | 8.1 | 7.3 | $1.55 | Tidak |
| Gemini/gemini-3.6-flash | 7.74 | 8.1 | 6.3 | $14.04 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.74 | 8.1 | 6.3 | $15.77 | Ya (flash) |
| Claude/sonnet-4.6 | 7.52 | 7.6 | 7.2 | $28.08 | Tidak |
| Gemini/gemini-3.1-pro | 7.46 | 7.8 | 6.1 | $21.02 | Tidak |
| Groq/groq-compound | 6.82 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.54 | 6.5 | 6.7 | $7.88 | Tidak |
| Groq/groq-gpt-oss-120b | 6.33 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.24 | 6.2 | 6.4 | $2.16 | Tidak |
| Gemini/gemini-3.0-flash-preview | 5.93 | 6.2 | 4.8 | $5.26 | Ya (flash) |
| Gemini/gemini-3.5-flash-lite | 5.74 | 6.0 | 4.7 | $3.96 | Ya (flash_lite) |
| Groq/groq-qwen3-27b | 5.55 | 5.7 | 5.0 | $0.00 | Ya (Groq) |
| Groq/groq-compound-mini | 5.16 | 5.3 | 4.6 | $0.00 | Ya (Groq) |
| Claude/haiku-4.5 | 4.85 | 4.9 | 4.7 | $9.36 | Tidak |
| Groq/groq-gpt-oss-20b | 4.68 | 4.8 | 4.2 | $0.00 | Ya (Groq) |

### news_digest_macro_overview
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.78 | 9.9 | 9.4 | $6.90 | Tidak |
| OpenAI/gpt-5.6-sol | 9.67 | 9.6 | 9.9 | $7.80 | Tidak |
| OpenAI/gpt-5.5-pro | 9.67 | 9.6 | 9.9 | $46.80 | Tidak |
| Claude/fable-5 | 9.58 | 9.7 | 9.2 | $13.80 | Tidak |
| OpenAI/gpt-5.4-pro | 9.47 | 9.4 | 9.7 | $46.80 | Tidak |
| Claude/opus-4.8 | 8.98 | 9.1 | 8.6 | $6.90 | Tidak |
| OpenAI/gpt-5.6-terra | 8.97 | 8.9 | 9.2 | $3.12 | Tidak |
| OpenAI/gpt-5.5 | 8.97 | 8.9 | 9.2 | $7.80 | Tidak |
| Claude/sonnet-5 | 8.79 | 8.9 | 8.5 | $2.76 | Tidak |
| OpenAI/gpt-5.4 | 8.46 | 8.4 | 8.7 | $3.90 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.38 | 8.6 | 7.7 | $0.67 | Tidak |
| OpenAI/gpt-5.6-luna | 8.36 | 8.3 | 8.6 | $0.31 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.90 | 8.1 | 7.3 | $0.22 | Tidak |
| Gemini/gemini-3.6-flash | 7.66 | 8.1 | 6.3 | $2.07 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.66 | 8.1 | 6.3 | $2.34 | Ya (flash) |
| Claude/sonnet-4.6 | 7.50 | 7.6 | 7.2 | $4.14 | Tidak |
| Gemini/gemini-3.1-pro | 7.37 | 7.8 | 6.1 | $3.12 | Tidak |
| Groq/groq-compound | 6.77 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.55 | 6.5 | 6.7 | $1.17 | Tidak |
| Groq/groq-gpt-oss-120b | 6.29 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.25 | 6.2 | 6.4 | $0.32 | Tidak |

### news_digest_verifier
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.85 | 9.9 | 9.4 | $2.88 | Tidak |
| Claude/fable-5 | 9.65 | 9.7 | 9.2 | $5.76 | Tidak |
| OpenAI/gpt-5.6-sol | 9.63 | 9.6 | 9.9 | $3.24 | Tidak |
| OpenAI/gpt-5.5-pro | 9.63 | 9.6 | 9.9 | $19.44 | Tidak |
| OpenAI/gpt-5.4-pro | 9.43 | 9.4 | 9.7 | $19.44 | Tidak |
| Claude/opus-4.8 | 9.05 | 9.1 | 8.6 | $2.88 | Tidak |
| OpenAI/gpt-5.6-terra | 8.93 | 8.9 | 9.2 | $1.30 | Tidak |
| OpenAI/gpt-5.5 | 8.93 | 8.9 | 9.2 | $3.24 | Tidak |
| Claude/sonnet-5 | 8.86 | 8.9 | 8.5 | $1.15 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.51 | 8.6 | 7.7 | $0.29 | Tidak |
| OpenAI/gpt-5.4 | 8.43 | 8.4 | 8.7 | $1.62 | Tidak |
| OpenAI/gpt-5.6-luna | 8.32 | 8.3 | 8.6 | $0.13 | Tidak |
| DeepSeek/deepseek-v4-flash | 8.02 | 8.1 | 7.3 | $0.10 | Tidak |
| Gemini/gemini-3.6-flash | 7.92 | 8.1 | 6.3 | $0.86 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.92 | 8.1 | 6.3 | $0.97 | Ya (flash) |
| Gemini/gemini-3.1-pro | 7.63 | 7.8 | 6.1 | $1.30 | Tidak |
| Claude/sonnet-4.6 | 7.56 | 7.6 | 7.2 | $1.73 | Tidak |
| Groq/groq-compound | 6.91 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.52 | 6.5 | 6.7 | $0.49 | Tidak |
| Groq/groq-gpt-oss-120b | 6.42 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.22 | 6.2 | 6.4 | $0.13 | Tidak |
| Gemini/gemini-3.0-flash-preview | 6.06 | 6.2 | 4.8 | $0.32 | Ya (flash) |
| Gemini/gemini-3.5-flash-lite | 5.87 | 6.0 | 4.7 | $0.24 | Ya (flash_lite) |
| Groq/groq-qwen3-27b | 5.63 | 5.7 | 5.0 | $0.00 | Ya (Groq) |
| Groq/groq-compound-mini | 5.23 | 5.3 | 4.6 | $0.00 | Ya (Groq) |
| Claude/haiku-4.5 | 4.88 | 4.9 | 4.7 | $0.58 | Tidak |
| Groq/groq-gpt-oss-20b | 4.74 | 4.8 | 4.2 | $0.00 | Ya (Groq) |
| Gemini/gemini-3.1-flash-lite | 4.01 | 4.1 | 3.2 | $0.16 | Ya (flash_lite) |

### fundamental_verifier
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.78 | 9.9 | 9.4 | $2.70 | Tidak |
| OpenAI/gpt-5.6-sol | 9.67 | 9.6 | 9.9 | $2.94 | Tidak |
| OpenAI/gpt-5.5-pro | 9.67 | 9.6 | 9.9 | $17.64 | Tidak |
| Claude/fable-5 | 9.58 | 9.7 | 9.2 | $5.40 | Tidak |
| OpenAI/gpt-5.4-pro | 9.47 | 9.4 | 9.7 | $17.64 | Tidak |
| Claude/opus-4.8 | 8.98 | 9.1 | 8.6 | $2.70 | Tidak |
| OpenAI/gpt-5.6-terra | 8.97 | 8.9 | 9.2 | $1.18 | Tidak |
| OpenAI/gpt-5.5 | 8.97 | 8.9 | 9.2 | $2.94 | Tidak |
| Claude/sonnet-5 | 8.79 | 8.9 | 8.5 | $1.08 | Tidak |
| OpenAI/gpt-5.4 | 8.46 | 8.4 | 8.7 | $1.47 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.38 | 8.6 | 7.7 | $0.29 | Tidak |
| OpenAI/gpt-5.6-luna | 8.36 | 8.3 | 8.6 | $0.12 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.90 | 8.1 | 7.3 | $0.10 | Tidak |
| Gemini/gemini-3.6-flash | 7.66 | 8.1 | 6.3 | $0.81 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.66 | 8.1 | 6.3 | $0.88 | Ya (flash) |
| Claude/sonnet-4.6 | 7.50 | 7.6 | 7.2 | $1.62 | Tidak |
| Gemini/gemini-3.1-pro | 7.37 | 7.8 | 6.1 | $1.18 | Tidak |
| Groq/groq-compound | 6.77 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.55 | 6.5 | 6.7 | $0.44 | Tidak |
| Groq/groq-gpt-oss-120b | 6.29 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.25 | 6.2 | 6.4 | $0.12 | Tidak |
| Gemini/gemini-3.0-flash-preview | 5.86 | 6.2 | 4.8 | $0.29 | Ya (flash) |
| Gemini/gemini-3.5-flash-lite | 5.67 | 6.0 | 4.7 | $0.21 | Ya (flash_lite) |
| Groq/groq-qwen3-27b | 5.51 | 5.7 | 5.0 | $0.00 | Ya (Groq) |
| Groq/groq-compound-mini | 5.13 | 5.3 | 4.6 | $0.00 | Ya (Groq) |
| Claude/haiku-4.5 | 4.84 | 4.9 | 4.7 | $0.54 | Tidak |
| Groq/groq-gpt-oss-20b | 4.64 | 4.8 | 4.2 | $0.00 | Ya (Groq) |

### cot_precompute
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.80 | 9.9 | 9.4 | $3.68 | Tidak |
| OpenAI/gpt-5.6-sol | 9.66 | 9.6 | 9.9 | $4.10 | Tidak |
| OpenAI/gpt-5.5-pro | 9.66 | 9.6 | 9.9 | $24.57 | Tidak |
| Claude/fable-5 | 9.60 | 9.7 | 9.2 | $7.35 | Tidak |
| OpenAI/gpt-5.4-pro | 9.46 | 9.4 | 9.7 | $24.57 | Tidak |
| Claude/opus-4.8 | 9.01 | 9.1 | 8.6 | $3.68 | Tidak |
| OpenAI/gpt-5.6-terra | 8.95 | 8.9 | 9.2 | $1.64 | Tidak |
| OpenAI/gpt-5.5 | 8.95 | 8.9 | 9.2 | $4.10 | Tidak |
| Claude/sonnet-5 | 8.81 | 8.9 | 8.5 | $1.47 | Tidak |
| OpenAI/gpt-5.4 | 8.45 | 8.4 | 8.7 | $2.05 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.43 | 8.6 | 7.7 | $0.37 | Tidak |
| OpenAI/gpt-5.6-luna | 8.35 | 8.3 | 8.6 | $0.16 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.94 | 8.1 | 7.3 | $0.12 | Tidak |
| Gemini/gemini-3.6-flash | 7.74 | 8.1 | 6.3 | $1.10 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.74 | 8.1 | 6.3 | $1.23 | Ya (flash) |
| Claude/sonnet-4.6 | 7.52 | 7.6 | 7.2 | $2.21 | Tidak |
| Gemini/gemini-3.1-pro | 7.46 | 7.8 | 6.1 | $1.64 | Tidak |
| Groq/groq-compound | 6.82 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.54 | 6.5 | 6.7 | $0.61 | Tidak |
| Groq/groq-gpt-oss-120b | 6.33 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.24 | 6.2 | 6.4 | $0.17 | Tidak |
| Gemini/gemini-3.0-flash-preview | 5.93 | 6.2 | 4.8 | $0.41 | Ya (flash) |
| Gemini/gemini-3.5-flash-lite | 5.74 | 6.0 | 4.7 | $0.30 | Ya (flash_lite) |
| Groq/groq-qwen3-27b | 5.55 | 5.7 | 5.0 | $0.00 | Ya (Groq) |
| Groq/groq-compound-mini | 5.16 | 5.3 | 4.6 | $0.00 | Ya (Groq) |
| Claude/haiku-4.5 | 4.85 | 4.9 | 4.7 | $0.73 | Tidak |
| Groq/groq-gpt-oss-20b | 4.68 | 4.8 | 4.2 | $0.00 | Ya (Groq) |

### chat_telegram
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.88 | 9.9 | 9.4 | $17.51 | Tidak |
| Claude/fable-5 | 9.68 | 9.7 | 9.2 | $35.03 | Tidak |
| OpenAI/gpt-5.6-sol | 9.61 | 9.6 | 9.9 | $22.36 | Tidak |
| OpenAI/gpt-5.5-pro | 9.61 | 9.6 | 9.9 | $134.19 | Tidak |
| OpenAI/gpt-5.4-pro | 9.41 | 9.4 | 9.7 | $134.19 | Tidak |
| Claude/opus-4.8 | 9.08 | 9.1 | 8.6 | $17.51 | Tidak |
| OpenAI/gpt-5.6-terra | 8.91 | 8.9 | 9.2 | $8.95 | Tidak |
| OpenAI/gpt-5.5 | 8.91 | 8.9 | 9.2 | $22.36 | Tidak |
| Claude/sonnet-5 | 8.88 | 8.9 | 8.5 | $7.01 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.56 | 8.6 | 7.7 | $2.60 | Tidak |
| OpenAI/gpt-5.4 | 8.41 | 8.4 | 8.7 | $11.18 | Tidak |
| OpenAI/gpt-5.6-luna | 8.31 | 8.3 | 8.6 | $0.89 | Tidak |
| DeepSeek/deepseek-v4-flash | 8.06 | 8.1 | 7.3 | $0.87 | Tidak |
| Gemini/gemini-3.6-flash | 8.01 | 8.1 | 6.3 | $6.44 | Ya (flash) |
| Gemini/gemini-3.5-flash | 8.01 | 8.1 | 6.3 | $6.71 | Ya (flash) |
| Gemini/gemini-3.1-pro | 7.71 | 7.8 | 6.1 | $8.95 | Tidak |
| Claude/sonnet-4.6 | 7.58 | 7.6 | 7.2 | $10.51 | Tidak |
| Groq/groq-compound | 6.95 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.51 | 6.5 | 6.7 | $3.35 | Tidak |
| Groq/groq-gpt-oss-120b | 6.46 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.21 | 6.2 | 6.4 | $0.90 | Tidak |
| Gemini/gemini-3.0-flash-preview | 6.13 | 6.2 | 4.8 | $2.24 | Ya (flash) |
| Gemini/gemini-3.5-flash-lite | 5.93 | 6.0 | 4.7 | $1.47 | Ya (flash_lite) |
| Groq/groq-qwen3-27b | 5.66 | 5.7 | 5.0 | $0.00 | Ya (Groq) |
| Groq/groq-compound-mini | 5.26 | 5.3 | 4.6 | $0.00 | Ya (Groq) |
| Claude/haiku-4.5 | 4.89 | 4.9 | 4.7 | $3.50 | Tidak |
| Groq/groq-gpt-oss-20b | 4.77 | 4.8 | 4.2 | $0.00 | Ya (Groq) |
| Gemini/gemini-3.1-flash-lite | 4.05 | 4.1 | 3.2 | $1.12 | Ya (flash_lite) |

### chat_telegram_medium
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.82 | 9.9 | 9.4 | $25.78 | Tidak |
| OpenAI/gpt-5.6-sol | 9.64 | 9.6 | 9.9 | $32.85 | Tidak |
| OpenAI/gpt-5.5-pro | 9.64 | 9.6 | 9.9 | $197.10 | Tidak |
| Claude/fable-5 | 9.63 | 9.7 | 9.2 | $51.57 | Tidak |
| OpenAI/gpt-5.4-pro | 9.44 | 9.4 | 9.7 | $197.10 | Tidak |
| Claude/opus-4.8 | 9.03 | 9.1 | 8.6 | $25.78 | Tidak |
| OpenAI/gpt-5.6-terra | 8.94 | 8.9 | 9.2 | $13.14 | Tidak |
| OpenAI/gpt-5.5 | 8.94 | 8.9 | 9.2 | $32.85 | Tidak |
| Claude/sonnet-5 | 8.83 | 8.9 | 8.5 | $10.31 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.47 | 8.6 | 7.7 | $3.78 | Tidak |
| OpenAI/gpt-5.4 | 8.44 | 8.4 | 8.7 | $16.42 | Tidak |
| OpenAI/gpt-5.6-luna | 8.34 | 8.3 | 8.6 | $1.31 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.98 | 8.1 | 7.3 | $1.26 | Tidak |
| Gemini/gemini-3.6-flash | 7.83 | 8.1 | 6.3 | $9.43 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.83 | 8.1 | 6.3 | $9.85 | Ya (flash) |
| Claude/sonnet-4.6 | 7.54 | 7.6 | 7.2 | $15.47 | Tidak |
| Gemini/gemini-3.1-pro | 7.54 | 7.8 | 6.1 | $13.14 | Tidak |
| Groq/groq-compound | 6.86 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.53 | 6.5 | 6.7 | $4.93 | Tidak |
| Groq/groq-gpt-oss-120b | 6.37 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.23 | 6.2 | 6.4 | $1.33 | Tidak |

### chat_telegram_complex
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.78 | 9.9 | 9.4 | $45.16 | Tidak |
| OpenAI/gpt-5.6-sol | 9.67 | 9.6 | 9.9 | $65.23 | Tidak |
| OpenAI/gpt-5.5-pro | 9.67 | 9.6 | 9.9 | $391.36 | Tidak |
| Claude/fable-5 | 9.58 | 9.7 | 9.2 | $90.32 | Tidak |
| OpenAI/gpt-5.4-pro | 9.47 | 9.4 | 9.7 | $391.36 | Tidak |
| Claude/opus-4.8 | 8.98 | 9.1 | 8.6 | $45.16 | Tidak |
| OpenAI/gpt-5.6-terra | 8.97 | 8.9 | 9.2 | $26.09 | Tidak |
| OpenAI/gpt-5.5 | 8.97 | 8.9 | 9.2 | $65.23 | Tidak |
| Claude/sonnet-5 | 8.79 | 8.9 | 8.5 | $18.06 | Tidak |
| OpenAI/gpt-5.4 | 8.46 | 8.4 | 8.7 | $32.61 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.38 | 8.6 | 7.7 | $7.61 | Tidak |
| OpenAI/gpt-5.6-luna | 8.36 | 8.3 | 8.6 | $2.61 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.90 | 8.1 | 7.3 | $2.54 | Tidak |
| Gemini/gemini-3.6-flash | 7.66 | 8.1 | 6.3 | $18.81 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.66 | 8.1 | 6.3 | $19.57 | Ya (flash) |
| Claude/sonnet-4.6 | 7.50 | 7.6 | 7.2 | $27.10 | Tidak |
| Gemini/gemini-3.1-pro | 7.37 | 7.8 | 6.1 | $26.09 | Tidak |

### trade_reflection
| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |
|---|---|---|---|---|---|
| Claude/opus-5 | 9.80 | 9.9 | 9.4 | $1.57 | Tidak |
| OpenAI/gpt-5.6-sol | 9.66 | 9.6 | 9.9 | $1.80 | Tidak |
| OpenAI/gpt-5.5-pro | 9.66 | 9.6 | 9.9 | $10.80 | Tidak |
| Claude/fable-5 | 9.60 | 9.7 | 9.2 | $3.15 | Tidak |
| OpenAI/gpt-5.4-pro | 9.46 | 9.4 | 9.7 | $10.80 | Tidak |
| Claude/opus-4.8 | 9.01 | 9.1 | 8.6 | $1.57 | Tidak |
| OpenAI/gpt-5.6-terra | 8.95 | 8.9 | 9.2 | $0.72 | Tidak |
| OpenAI/gpt-5.5 | 8.95 | 8.9 | 9.2 | $1.80 | Tidak |
| Claude/sonnet-5 | 8.81 | 8.9 | 8.5 | $0.63 | Tidak |
| OpenAI/gpt-5.4 | 8.45 | 8.4 | 8.7 | $0.90 | Tidak |
| DeepSeek/deepseek-v4-pro | 8.43 | 8.6 | 7.7 | $0.15 | Tidak |
| OpenAI/gpt-5.6-luna | 8.35 | 8.3 | 8.6 | $0.07 | Tidak |
| DeepSeek/deepseek-v4-flash | 7.94 | 8.1 | 7.3 | $0.05 | Tidak |
| Gemini/gemini-3.6-flash | 7.74 | 8.1 | 6.3 | $0.47 | Ya (flash) |
| Gemini/gemini-3.5-flash | 7.74 | 8.1 | 6.3 | $0.54 | Ya (flash) |
| Claude/sonnet-4.6 | 7.52 | 7.6 | 7.2 | $0.95 | Tidak |
| Gemini/gemini-3.1-pro | 7.46 | 7.8 | 6.1 | $0.72 | Tidak |
| Groq/groq-compound | 6.82 | 7.0 | 6.1 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-mini | 6.54 | 6.5 | 6.7 | $0.27 | Tidak |
| Groq/groq-gpt-oss-120b | 6.33 | 6.5 | 5.7 | $0.00 | Ya (Groq) |
| OpenAI/gpt-5.4-nano | 6.24 | 6.2 | 6.4 | $0.07 | Tidak |
| Gemini/gemini-3.0-flash-preview | 5.93 | 6.2 | 4.8 | $0.18 | Ya (flash) |
| Gemini/gemini-3.5-flash-lite | 5.74 | 6.0 | 4.7 | $0.14 | Ya (flash_lite) |
| Groq/groq-qwen3-27b | 5.55 | 5.7 | 5.0 | $0.00 | Ya (Groq) |
| Groq/groq-compound-mini | 5.16 | 5.3 | 4.6 | $0.00 | Ya (Groq) |
| Claude/haiku-4.5 | 4.85 | 4.9 | 4.7 | $0.31 | Tidak |
| Groq/groq-gpt-oss-20b | 4.68 | 4.8 | 4.2 | $0.00 | Ya (Groq) |

## 9. Audit Reliabilitas Finansial

Tidak ada peringatan fin_reliability.

## 10. Audit Risiko Latensi

Tidak ada peringatan TTFT.

## 11. Efficiency Frontier

| Budget/bln | Biaya Terpakai | Skor Kualitas | Delta Kualitas per $10 |
|---|---|---|---|
| $0 | infeasible | - | - |
| $5 | infeasible | - | - |
| $10 | infeasible | - | - |
| $20 | $20.09 | 8.31 | - |
| $30 | $30.11 | 8.52 | 0.209 |
| $40 | $40.27 | 8.65 | 0.135 |
| $50 | $50.12 | 8.77 | 0.121 |
| $60 | $60.08 | 8.89 | 0.115 |
| $75 | $75.13 | 9.01 | 0.084 |
| $100 | $100.09 | 9.16 | 0.058 |
| $125 | $125.20 | 9.30 | 0.055 |
| $150 | $150.16 | 9.40 | 0.041 |
| $200 | $200.06 | 9.53 | 0.026 |
| $250 | $249.88 | 9.61 | 0.017 |
| $300 | $298.75 | 9.66 | 0.010 |

## 12. Value Leaderboard

### Model Berbayar

| # | Provider/Model | Kecerdasan | Fin. Rel | Harga Blended/1M | Value |
|---|---|---|---|---|---|
| 1 | DeepSeek/deepseek-v4-flash | 8.1 | 7.3 | $0.330 | 24.55 |
| 2 | OpenAI/gpt-5.6-luna | 8.3 | 8.6 | $0.450 | 18.44 |
| 3 | OpenAI/gpt-5.4-nano | 6.2 | 6.4 | $0.463 | 13.41 |
| 4 | DeepSeek/deepseek-v4-pro | 8.6 | 7.7 | $0.990 | 8.69 |
| 5 | Gemini/gemini-3.1-flash-lite | 4.1 | 3.2 | $0.562 | 7.29 |
| 6 | Gemini/gemini-3.5-flash-lite | 6.0 | 4.7 | $0.850 | 7.06 |
| 7 | Gemini/gemini-3.0-flash-preview | 6.2 | 4.8 | $1.125 | 5.51 |
| 8 | OpenAI/gpt-5.4-mini | 6.5 | 6.7 | $1.688 | 3.85 |
| 9 | Gemini/gemini-3.6-flash | 8.1 | 6.3 | $3.000 | 2.70 |
| 10 | Claude/haiku-4.5 | 4.9 | 4.7 | $2.000 | 2.45 |
| 11 | Gemini/gemini-3.5-flash | 8.1 | 6.3 | $3.375 | 2.40 |
| 12 | Claude/sonnet-5 | 8.9 | 8.5 | $4.000 | 2.23 |
| 13 | OpenAI/gpt-5.6-terra | 8.9 | 9.2 | $4.500 | 1.98 |
| 14 | Gemini/gemini-3.1-pro | 7.8 | 6.1 | $4.500 | 1.73 |
| 15 | OpenAI/gpt-5.4 | 8.4 | 8.7 | $5.625 | 1.49 |

### Model Free Tier — Groq

| Provider/Model | Kecerdasan | Fin. Rel | Quota Efektif |
|---|---|---|---|
| Groq/groq-compound | 7.0 | 6.1 | 1750 RPD/hari |
| Groq/groq-gpt-oss-120b | 6.5 | 5.7 | 7000 RPD/hari |
| Groq/groq-qwen3-27b | 5.7 | 5.0 | 7000 RPD/hari |
| Groq/groq-compound-mini | 5.3 | 4.6 | 1750 RPD/hari |
| Groq/groq-gpt-oss-20b | 4.8 | 4.2 | 7000 RPD/hari |

## 13. Analisis Sensitivitas

| Parameter | Nilai | Biaya/bln | Skor Kualitas |
|---|---|---|---|
| MONTHLY_BUDGET_USD | 50.0 | $50.12 | 8.77 |
| MONTHLY_BUDGET_USD | 100.0 | $100.09 | 9.16 |
| MONTHLY_BUDGET_USD | 150.0 | $150.16 | 9.40 |
| MONTHLY_BUDGET_USD | 200.0 | $200.06 | 9.53 |
| GEMINI_FREE_KEYS | 11 | $100.09 | 9.16 |
| GEMINI_FREE_KEYS | 22 | $100.09 | 9.16 |
| GEMINI_FREE_KEYS | 44 | $100.09 | 9.16 |
| GROQ_FREE_KEYS | 3 | $100.09 | 9.16 |
| GROQ_FREE_KEYS | 7 | $100.09 | 9.16 |
| GROQ_FREE_KEYS | 14 | $100.09 | 9.16 |
| PRESCREEN_PASS_RATE | 0.27 | $100.08 | 9.23 |
| PRESCREEN_PASS_RATE | 0.45 | $100.09 | 9.16 |
| PRESCREEN_PASS_RATE | 0.63 | $100.13 | 9.11 |

## 14. Sumber Kalibrasi

- **AA Intelligence Index v4.1.1** (Agustus 2026)
- **AIMultiple FinanceReasoning + JurisTech (Apr 2026)**
- **Catatan**: Semua QUALITY_SCORE Groq = estimasi interpolasi.
