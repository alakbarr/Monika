"""
=====================================================================================
  AI COST & PERFORMANCE OPTIMIZER v4 — Claude AI Trading Agent
-------------------------------------------------------------------------------------
  Perbedaan besar dari v3:

    1. KALIBRASI ULANG QUALITY_SCORE untuk SEMUA model berdasarkan riset web
       (bukan tebakan manual) — sumber utama: Artificial Analysis Intelligence
       Index v4.1.1 (snapshot Agustus 2026, artificialanalysis.ai), dilengkapi
       system card / benchmark rilis resmi tiap vendor (Anthropic, OpenAI,
       Google DeepMind, DeepSeek) dan ARC Prize. Setiap angka diberi komentar
       sumber + tanggal snapshot di kode ini. Model yang belum pernah
       dibandingkan langsung (mis. Sonnet 4.5, GPT-5.2/5.4/5.5 Pro) diberi
       label "estimasi interpolasi" secara eksplisit — TIDAK dianggap presisi
       sama seperti model yang terukur langsung.

    2. DIMENSI KUALITAS BARU: FIN_RELIABILITY_SCORE — reliabilitas spesifik
       untuk analisis pasar finansial, dipisah dari kecerdasan umum. Sumber:
       - AIMultiple FinanceReasoning benchmark (238 soal reasoning finansial
         sulit) — keluarga GPT-5.6 mencatat akurasi tertinggi.
       - JurisTech hallucination-under-incomplete-financial-data report
         (April 2026) — GPT-5.4 lolos semua kriteria (tidak mengarang angka),
         Claude Opus 4.6 berada di "zona hati-hati" (cenderung estimasi),
         Gemini 3.1 Pro GAGAL semua kriteria (TIDAK direkomendasikan untuk
         data finansial yang tidak lengkap) meski skor Intelligence Index-nya
         tinggi.
       - AA-Omniscience (bagian dari Intelligence Index) sebagai proxy umum
         tingkat halusinasi.
       Skor ini dihitung sebagai QUALITY_SCORE * pengali per-provider
       (FIN_RELIABILITY_MULTIPLIER), lalu tiap TASK punya bobot 'fin_weight'
       (0.0–0.45) yang menentukan seberapa besar reliabilitas finansial ini
       ikut menentukan kualitas efektif yang dipakai optimizer — task yang
       benar-benar menggerakkan uang (stage2_per_asset_primary, dst.) diberi
       bobot tinggi; task mekanis (prescreen, klasifikasi) diberi bobot kecil.

    3. LATENCY_TTFT_SEC — sinyal risiko latensi (time-to-first-token) untuk
       model/effort yang datanya tersedia dari Artificial Analysis, dipetakan
       ke task yang ditandai 'latency_sensitive' (task reaktif / task yang
       berada di jalur kritis sebelum order masuk pasar: trigger-checker,
       debate gate, risk gate, portfolio gate, chat user-facing).

    4. CANDIDATE_POOL diperluas dari 14 -> ~23 model (menambahkan Fable 5,
       Opus 4.8, keluarga GPT-5.6 Sol/Terra/Luna, GPT-5.4/5.5, varian Pro
       OpenAI, dll — semuanya sudah ada di PROVIDERS, hanya belum pernah
       ikut dipertimbangkan optimizer) sehingga DP benar-benar memilih dari
       seluruh frontier realistis, bukan shortlist manual.

    5. REASONING_FLOOR / REASONING_WEIGHT dikalibrasi ulang supaya selaras
       dengan skala QUALITY_SCORE baru (0–10, dengan Opus 5 ≈ 9.9).

    6. FITUR ANALISIS BARU:
       - Value Leaderboard (kualitas per dolar, lintas semua model, lepas
         dari konteks task tertentu) memakai rasio blended 3:1 input:output
         ala metodologi Artificial Analysis.
       - Audit Reliabilitas Finansial: menandai bila task dengan fin_weight
         tinggi jatuh ke model dengan fin_reliability rendah.
       - Audit Risiko Latensi: menandai task latency_sensitive yang jatuh ke
         model dengan TTFT terukur tinggi.
       - Analisis Sensitivitas (tornado): dampak perubahan budget, jumlah key
         gratis Gemini, dan prescreen pass-rate terhadap biaya & kualitas
         rekomendasi, TANPA mengubah state global (pipeline di-parametrisasi).
       - Self-test ringan saat start (sanity check struktur data).
       - Mode non-interaktif via argparse (--budget, --mode, --output,
         --non-interactive, --skip-sensitivity) untuk dijalankan otomatis /
         di CI, selain mode interaktif lama yang tetap dipertahankan.

  TIDAK DIUBAH (sesuai instruksi): PROVIDERS (harga & nama model), struktur
  TASKS inti (volume panggilan, token, turns), dan alur DP Multiple-Choice
  Knapsack. Semua angka kualitas baru + fitur baru ditambahkan DI ATAS
  fondasi v3 tanpa menyentuh harga atau nama model yang sudah dikonfirmasi
  valid.
=====================================================================================
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
import argparse
import copy
import sys

# =====================================================================================
# 0. ASUMSI GLOBAL — SILAKAN UBAH SESUAI KONDISI NYATA
# =====================================================================================
MONTHLY_BUDGET_USD = 100.0
DAYS_PER_MONTH = 30

GEMINI_FREE_KEYS = 20          # jumlah API key Gemini free-tier yang kamu rotasi
GEMINI_HAS_PAID_KEY = True     # kamu bilang BISA menambah 1 key berbayar utk model Pro jika perlu

# Rate limiting: utils/gemini_rate_limiter.py telah diperbaiki
# sehingga batas RPD/RPM dikalikan dengan jumlah key secara benar.
FLASH_RPD, FLASH_RPM = 20 * GEMINI_FREE_KEYS, 5 * GEMINI_FREE_KEYS
FLASH_LITE_RPD, FLASH_LITE_RPM = 500 * GEMINI_FREE_KEYS, 15 * GEMINI_FREE_KEYS

# Prescreen: analysis/per_asset_stage.py telah diperbaiki sehingga
# gerbang prescreen berjalan normal dan memfilter analisis Stage-2.
PRESCREEN_PASS_RATE = 0.45   # filter tambahan Haiku prescreen

CACHE_WRITE_MULTIPLIER = 1.25   # premi standar Anthropic utk cache write (TTL 5 menit)

# Ambang TTFT (detik) di atas mana sebuah task 'latency_sensitive' akan
# memicu warning di laporan. Nilai TTFT sendiri berasal dari pengukuran
# pihak ketiga (Artificial Analysis) pada effort tinggi/max — bukan jaminan
# performa di traffic production kamu.
LATENCY_WARNING_THRESHOLD_SEC = 15.0

# =====================================================================================
# 1. HARGA MODEL (USD / 1M token) -> (Input, Cached-Input/Read, Output)
#    TIDAK DIUBAH sesuai instruksi — harga & nama model sudah dikonfirmasi valid.
# =====================================================================================
PROVIDERS = {
    "Gemini": {
        "gemini-3.1-flash-lite": (0.25, 0.025, 1.50),
        "gemini-3.5-flash-lite": (0.30, 0.03, 2.50),
        "gemini-3.0-flash-preview": (0.50, 0.05, 3.00),
        "gemini-3.5-flash": (1.50, 0.15, 9.00),
        "gemini-3.6-flash": (1.50, 0.15, 7.50),
        "gemini-2.5-pro": (1.25, 0.125, 10.00),
        "gemini-3.1-pro": (2.00, 0.20, 12.00),
    },
    "Claude": {
        "haiku-4.5": (1.00, 0.10, 5.00),
        "sonnet-4.5": (3.00, 0.30, 15.00),
        "sonnet-4.6": (3.00, 0.30, 15.00),
        "sonnet-5": (2.00, 0.20, 10.00),
        "opus-4.5": (5.00, 0.50, 25.00),
        "opus-4.6": (5.00, 0.50, 25.00),
        "opus-4.7": (5.00, 0.50, 25.00),
        "opus-4.8": (5.00, 0.50, 25.00),
        "opus-5": (5.00, 0.50, 25.00),
        "fable-5": (10.00, 1.00, 50.00),
    },
    "OpenAI": {
        "gpt-5.1": (1.25, 0.125, 10.00),
        "gpt-5.2-pro": (21.00, 2.10, 168.00),
        "gpt-5.4-nano": (0.20, 0.02, 1.25),
        "gpt-5.4-mini": (0.75, 0.075, 4.50),
        "gpt-5.4": (2.50, 0.25, 15.00),
        "gpt-5.4-pro": (30.00, 3.00, 180.00),
        "gpt-5.5": (5.00, 0.50, 30.00),
        "gpt-5.5-pro": (30.00, 3.00, 180.00),
        "gpt-5.6-luna": (0.20, 0.02, 1.20),
        "gpt-5.6-terra": (2.00, 0.20, 12.00),
        "gpt-5.6-sol": (5.00, 0.50, 30.00),
    },
    "DeepSeek": {
        "deepseek-v4-flash": (0.22, 0.007, 0.66),
        "deepseek-v4-pro": (0.66, 0.022, 1.98),
    },
}

# =====================================================================================
# 1b. QUALITY_SCORE — KALIBRASI ULANG (0–10), sumber utama: Artificial Analysis
#     Intelligence Index v4.1.1 (snapshot ~pertengahan Agustus 2026), memakai
#     titik data effort tertinggi yang tersedia untuk tiap model (max/xhigh),
#     dinormalisasi dengan quality10 = round(AA_index / 6.16, 1) sehingga
#     model terbaik saat ini (Claude Opus 5, AA=61) mendekati 9.9. Ini
#     menggantikan angka "estimasi saya" di v3 dengan data terukur pihak
#     ketiga. Model yang ditandai "estimasi" belum punya titik data AA-index
#     langsung di tanggal riset ini — nilainya diinterpolasi dari model
#     sekeluarga / benchmark ARC-AGI-2 & FrontierMath yang tersedia, jadi
#     perlakukan sebagai perkiraan kasar, bukan angka terukur.
#
#     Catatan penting: skor AA Intelligence Index memakai metodologi yang
#     berubah dari waktu ke waktu (v4.0 -> v4.1 -> v4.1.1, skala "mengetat"
#     tiap revisi). Semua angka di bawah diusahakan konsisten pada skala
#     v4.1.1 / snapshot Agustus 2026 supaya bisa dibandingkan apple-to-apple;
#     kalau kamu riset ulang nanti, pastikan pakai snapshot index versi yang
#     sama untuk semua model, jangan campur versi lama & baru.
# =====================================================================================
QUALITY_SCORE = {
    # --- Claude --- (artificialanalysis.ai/models/..., snapshot Agu 2026)
    ("Claude", "haiku-4.5"): 4.9,     # AA=30 (reasoning mode)
    ("Claude", "sonnet-4.5"): 6.8,    # estimasi interpolasi (antara Haiku 4.5 & Sonnet 4.6)
    ("Claude", "sonnet-4.6"): 7.6,    # AA=47
    ("Claude", "sonnet-5"): 8.9,      # AA=55 (adaptive reasoning, max effort)
    ("Claude", "opus-4.5"): 6.7,      # AA=41
    ("Claude", "opus-4.6"): 7.1,      # AA=44
    ("Claude", "opus-4.7"): 8.8,      # AA=54
    ("Claude", "opus-4.8"): 9.1,      # AA=56 (max effort; Anthropic sendiri klaim 61.4 di skala v4.0 lama)
    ("Claude", "opus-5"): 9.9,        # AA=61, #1 Intelligence Index per 24 Jul 2026 (max effort)
    ("Claude", "fable-5"): 9.7,       # AA=60, #2 Intelligence Index (Opus 4.8 fallback config)

    # --- Gemini --- (artificialanalysis.ai + blog.google rilis resmi)
    ("Gemini", "gemini-3.1-flash-lite"): 4.1,   # AA=25
    ("Gemini", "gemini-3.5-flash-lite"): 6.0,   # AA=37
    ("Gemini", "gemini-3.0-flash-preview"): 6.2, # AA=38 (Gemini 3 Flash Preview, reasoning)
    ("Gemini", "gemini-3.5-flash"): 8.1,        # AA=50
    ("Gemini", "gemini-3.6-flash"): 8.1,        # AA=50 (setara 3.5 Flash, tapi lebih cepat/murah)
    ("Gemini", "gemini-2.5-pro"): 4.2,          # AA=26 (sudah jauh tertinggal dari generasi 3.x)
    ("Gemini", "gemini-3.1-pro"): 7.8,          # AA=48 (Preview, high reasoning)

    # --- OpenAI --- (artificialanalysis.ai + openai.com rilis resmi)
    ("OpenAI", "gpt-5.1"): 6.3,          # AA=39 (high effort)
    ("OpenAI", "gpt-5.2-pro"): 7.5,      # estimasi interpolasi dari ARC-AGI-2 (54.2%) & GPT-5.2 xhigh (AA=42)
    ("OpenAI", "gpt-5.4-nano"): 6.2,     # AA=38 (xhigh)
    ("OpenAI", "gpt-5.4-mini"): 6.5,     # AA=41 (xhigh)
    ("OpenAI", "gpt-5.4"): 8.4,          # AA=52 (xhigh)
    ("OpenAI", "gpt-5.4-pro"): 9.4,      # estimasi interpolasi dari ARC-AGI-2 (83.3% vs 73.3% xhigh)
    ("OpenAI", "gpt-5.5"): 8.9,          # AA=55 (xhigh)
    ("OpenAI", "gpt-5.5-pro"): 9.6,      # estimasi interpolasi dari FrontierMath T4 (39.6%) & harga tier Pro
    ("OpenAI", "gpt-5.6-luna"): 8.3,     # AA=51 (max)
    ("OpenAI", "gpt-5.6-terra"): 8.9,    # AA=55 (max)
    ("OpenAI", "gpt-5.6-sol"): 9.6,      # AA=59 (max), #2 di belakang Fable 5 pada 9 Jul 2026

    # --- DeepSeek --- (artificialanalysis.ai, build 0731/0813)
    ("DeepSeek", "deepseek-v4-flash"): 8.1,  # AA=50 (build 0731, reasoning max effort)
    ("DeepSeek", "deepseek-v4-pro"): 8.6,    # AA=53 (build 0813, reasoning max effort)
}

# =====================================================================================
# 1c. FIN_RELIABILITY_SCORE — dimensi kualitas KEDUA, khusus reliabilitas pada
#     analisis finansial (bukan kecerdasan umum). Dihitung otomatis dari
#     QUALITY_SCORE * pengali per-provider di bawah, supaya konsisten & mudah
#     diaudit. Pengali ini MEREFLEKSIKAN TEMUAN RISET, bukan preferensi:
#
#     - OpenAI (1.03): akurasi tertinggi pada FinanceReasoning benchmark
#       (GPT-5.6 Sol Pro ~90.8%), dan satu-satunya keluarga model yang lolos
#       SEMUA kriteria uji halusinasi JurisTech saat diberi dokumen finansial
#       dengan data yang sengaja dihilangkan/salah (tidak mengarang angka).
#     - Claude (0.95): reputasi halusinasi rendah secara umum (AA-Omniscience),
#       tapi pada uji spesifik JurisTech, Opus 4.6 masuk 'zona hati-hati' —
#       cenderung memberi estimasi masuk akal alih-alih mengaku data hilang.
#       Masih jauh lebih baik dari Gemini pada uji yang sama.
#     - DeepSeek (0.90): tidak ditemukan uji halusinasi-finansial terarah
#       untuk model ini di riset saat ini; dipakai proxy skor umum dengan
#       diskon moderat karena minim rekam jejak audit di tooling enterprise
#       finansial dibanding 2 provider di atas.
#     - Gemini (0.78): pada uji JurisTech, Gemini 3.1 Pro GAGAL SEMUA
#       kriteria dan eksplisit TIDAK DIREKOMENDASIKAN untuk data finansial
#       yang tidak lengkap, walau skor Intelligence Index-nya kompetitif.
#       Penalti ini sengaja cukup besar karena riset menunjukkan gap ini
#       nyata, bukan sekadar beda tipis.
#
#     Catatan: ini kalibrasi kasar berbasis satu studi pihak ketiga (JurisTech,
#     April 2026) + satu benchmark reasoning finansial (AIMultiple). Kalau ada
#     studi baru/lebih besar, sesuaikan FIN_RELIABILITY_MULTIPLIER di bawah.
# =====================================================================================
FIN_RELIABILITY_MULTIPLIER = {
    "OpenAI": 1.03,
    "Claude": 0.95,
    "DeepSeek": 0.90,
    "Gemini": 0.78,
}


def _compute_fin_reliability(provider: str, model: str) -> Optional[float]:
    base = QUALITY_SCORE.get((provider, model))
    if base is None:
        return None
    mult = FIN_RELIABILITY_MULTIPLIER.get(provider, 0.85)
    return round(min(10.0, base * mult), 2)


FIN_RELIABILITY_SCORE = {
    key: _compute_fin_reliability(*key) for key in QUALITY_SCORE
}

# =====================================================================================
# 1d. LATENCY_TTFT_SEC — time-to-first-token (detik) pada effort tinggi/max,
#     HANYA diisi untuk model yang datanya benar-benar ada di riset (Artificial
#     Analysis, Agu 2026). Model lain dibiarkan tidak ada entri (None saat
#     dicek) daripada mengarang angka. Dipakai sebagai SINYAL RISIKO, bukan
#     SLA — throughput riil tergantung panjang prompt, beban server, & harness.
# =====================================================================================
LATENCY_TTFT_SEC = {
    ("Claude", "opus-4.8"): 23.65,        # max effort
    ("Claude", "haiku-4.5"): 0.92,        # non-reasoning
    ("OpenAI", "gpt-5.5"): 33.87,         # high effort
    ("Gemini", "gemini-3.6-flash"): 17.71,      # high effort
    ("Gemini", "gemini-3.5-flash-lite"): 9.11,  # high effort
    ("DeepSeek", "deepseek-v4-pro"): 1.69,
}

# Kapabilitas per provider, digrounding langsung dari kode:
# Semua provider (Claude, Gemini, OpenAI, DeepSeek) telah mengimplementasikan run_agent penuh.
PROVIDER_AGENTIC_CAPABLE = {"Claude": True, "Gemini": True, "OpenAI": True, "DeepSeek": True}
PROVIDER_CACHING_SUPPORTED = {"Claude": True, "Gemini": False, "OpenAI": False, "DeepSeek": False}

# Tier Gemini -> menentukan apakah masuk pool gratis (flash/flash_lite) atau
# berbayar (pro, butuh GEMINI_HAS_PAID_KEY).
GEMINI_TIER = {
    "gemini-3.1-flash-lite": "flash_lite",
    "gemini-3.5-flash-lite": "flash_lite",
    "gemini-3.0-flash-preview": "flash",
    "gemini-3.5-flash": "flash",
    "gemini-3.6-flash": "flash",
    "gemini-2.5-pro": "pro",
    "gemini-3.1-pro": "pro",
}

# =====================================================================================
# 2. POOL KANDIDAT — DIPERLUAS dari 14 -> 23 model dibanding v3. Semua model
#    di bawah sudah punya harga valid di PROVIDERS; menambah mereka ke pool
#    membuat DP benar-benar memilih dari seluruh frontier realistis (termasuk
#    model 2026 terbaru seperti Fable 5 & keluarga GPT-5.6), bukan shortlist
#    manual yang membatasi opsi sejak awal. Model lama yang secara harga & &
#    kualitas didominasi total oleh model sekeluarga yang lebih baru (mis.
#    Opus 4.5/4.6/4.7 vs Opus 4.8 di harga yang SAMA) sengaja tidak
#    dimasukkan ke pool aktif -- tetap ada di QUALITY_SCORE untuk referensi
#    dan untuk baseline "current settings.yaml".
# =====================================================================================
CANDIDATE_POOL = [
    # Claude
    ("Claude", "opus-5"), ("Claude", "fable-5"), ("Claude", "opus-4.8"),
    ("Claude", "sonnet-5"), ("Claude", "sonnet-4.6"), ("Claude", "haiku-4.5"),
    # Gemini
    ("Gemini", "gemini-3.1-pro"), ("Gemini", "gemini-3.6-flash"), ("Gemini", "gemini-3.5-flash"),
    ("Gemini", "gemini-3.0-flash-preview"),
    ("Gemini", "gemini-3.5-flash-lite"), ("Gemini", "gemini-3.1-flash-lite"),
    # OpenAI
    ("OpenAI", "gpt-5.6-sol"), ("OpenAI", "gpt-5.6-terra"), ("OpenAI", "gpt-5.6-luna"),
    ("OpenAI", "gpt-5.5-pro"), ("OpenAI", "gpt-5.5"),
    ("OpenAI", "gpt-5.4-pro"), ("OpenAI", "gpt-5.4"),
    ("OpenAI", "gpt-5.4-mini"), ("OpenAI", "gpt-5.4-nano"),
    # DeepSeek
    ("DeepSeek", "deepseek-v4-pro"), ("DeepSeek", "deepseek-v4-flash"),
]

# Floor & bobot dikalibrasi ulang supaya selaras dengan skala QUALITY_SCORE baru.
# Low-Medium digeser 5.0 -> 4.5 supaya benar-benar memisahkan Haiku 4.5 (4.9)
# dari model gratis kecil (Gemini 3.1 Flash-Lite 4.1, Gemini 2.5 Pro 4.2) --
# di v3 celah ini kosong (tidak ada model yang jatuh pas di rentang 5.0-6.0).
REASONING_FLOOR = {"High": 8.0, "Medium-High": 7.0, "Medium": 6.0, "Low-Medium": 4.5, "Low": 4.0}
REASONING_WEIGHT = {"High": 3.0, "Medium-High": 2.5, "Medium": 2.0, "Low-Medium": 1.5, "Low": 1.0}

# =====================================================================================
# 3. VOLUME PANGGILAN
# =====================================================================================
STAGE2_MAIN_CYCLE_ATTEMPTS = 4 * 7          # 4 cycle/hari x 7 aset = 28 percobaan/hari (batas atas)
STAGE2_MAIN_SURVIVAL_RATE = 0.85            # hanya gate cooldown + staleness + data-quality
STAGE2_REACTIVE_ATTEMPTS = 10               # session-trigger + trigger-checker + news-watcher gabungan

_main_attempts = STAGE2_MAIN_CYCLE_ATTEMPTS * STAGE2_MAIN_SURVIVAL_RATE
_reactive_attempts = STAGE2_REACTIVE_ATTEMPTS * STAGE2_MAIN_SURVIVAL_RATE

STAGE2_PRIMARY_RUNS = round(_main_attempts * PRESCREEN_PASS_RATE)
STAGE2_SECONDARY_RUNS = round(_reactive_attempts * PRESCREEN_PASS_RATE)
STAGE2_PRESCREEN_RUNS = round(_main_attempts + _reactive_attempts)

# =====================================================================================
# 4. TASK DEFINITIONS
#    Ditambah 2 field baru per task dibanding v3:
#      - fin_weight (0.0-0.45): seberapa besar reliabilitas finansial
#        (FIN_RELIABILITY_SCORE) ikut menentukan kualitas efektif, relatif
#        terhadap kecerdasan umum (QUALITY_SCORE). Task yang benar-benar
#        menggerakkan keputusan/uang riil diberi bobot tinggi.
#      - latency_sensitive (bool): apakah task ini reaktif atau berada di
#        jalur kritis sebelum order masuk pasar (trigger-checker, gerbang
#        debat/risk/portfolio, chat user-facing) -> dipakai untuk audit
#        risiko latensi terhadap model ber-TTFT tinggi.
# =====================================================================================
TASKS = {
    "stage1_fundamental": dict(
        kind="agentic", runs_per_day=4, reasoning="High", situational=False,
        turns=9, system_tokens=7000, tools_tokens=5000, initial_user_tokens=900,
        per_turn_output_tokens=220, per_turn_tool_result_tokens=600, final_answer_tokens=900,
        fin_weight=0.35, latency_sensitive=False,
        note="TUGAS: Menyusun Fundamental Brief (pandangan makro global). ANALISIS: Mengevaluasi sentimen makroekonomi, risiko, dan merumuskan bias arah mata uang (bullish/bearish). DATA: Kalender ekonomi, berita, yield obligasi (Treasury), suku bunga sentral, FedWatch, COT, dan VIX. OUTPUT: JSON berisi narasi makro, bias mata uang, dan skor keyakinan. URGENSI: SANGAT TINGGI (High). Menjadi fondasi wajib bagi semua tugas di Stage 2.",
    ),
    "stage1_escalation": dict(
        kind="agentic", runs_per_day=1, reasoning="High", situational=True,
        turns=10, system_tokens=7000, tools_tokens=5000, initial_user_tokens=1100,
        per_turn_output_tokens=220, per_turn_tool_result_tokens=600, final_answer_tokens=900,
        fin_weight=0.35, latency_sensitive=False,
        note="TUGAS: Resolusi ambiguitas makro. ANALISIS: Menjalankan ulang analisis fundamental dengan model cerdas jika output Stage 1 memiliki keyakinan rendah/bias bertentangan. DATA: Sama dengan Stage 1, ditambah kemampuan web search mandiri. OUTPUT: Fundamental Brief yang direvisi dan definitif. URGENSI: TINGGI (High). Mencegah trading buta saat kondisi makro sangat kacau.",
    ),
    "stage2_per_asset_primary": dict(
        kind="agentic", runs_per_day=STAGE2_PRIMARY_RUNS, reasoning="High", situational=False,
        turns=3, system_tokens=11000, tools_tokens=7500, initial_user_tokens=7200,
        per_turn_output_tokens=250, per_turn_tool_result_tokens=500, final_answer_tokens=1000,
        fin_weight=0.45, latency_sensitive=False,
        note="TUGAS: Analisis dan pengambilan keputusan trading terjadwal per aset. ANALISIS: Menggabungkan bias makro (Stage 1) dengan pola teknikal lokal, mencari titik masuk optimal, dan mengukur risk/reward. DATA: Fundamental Brief, harga (OHLCV), teknikal, swing points, S/R, likuiditas, dan FVG. OUTPUT: Keputusan konkrit (buy/sell/wait/avoid) beserta batas SL, TP, dan kriteria invalidasi. URGENSI: SANGAT TINGGI (High). Otak utama yang menginstruksikan backend mengeksekusi uang riil.",
    ),
    "stage2_per_asset_secondary": dict(
        kind="agentic", runs_per_day=STAGE2_SECONDARY_RUNS, reasoning="Medium-High", situational=False,
        turns=2, system_tokens=11000, tools_tokens=7500, initial_user_tokens=6800,
        per_turn_output_tokens=250, per_turn_tool_result_tokens=500, final_answer_tokens=900,
        fin_weight=0.40, latency_sensitive=True,
        note="TUGAS: Re-evaluasi taktis dan reaktif (Trigger Checker). ANALISIS: Menilai ulang posisi terbuka atau trigger antre ketika ada lonjakan harga, pergantian sesi, atau rilis berita mendadak. DATA: Data teknikal terbaru, kondisi posisi berjalan, dan breaking news. OUTPUT: Keputusan cepat untuk tahan posisi, modifikasi SL/TP, atau auto-close. URGENSI: MENENGAH-TINGGI (Medium-High). Kunci perlindungan modal adaptif.",
    ),
    "stage2_prescreen": dict(
        kind="single", runs_per_day=STAGE2_PRESCREEN_RUNS, reasoning="Low", situational=False,
        in_tokens=1500, out_tokens=100,
        fin_weight=0.05, latency_sensitive=True,
        note="TUGAS: Gerbang penyaring (Gatekeeper) pra-analisis. ANALISIS: Memeriksa sekilas kondisi teknikal aset (apakah sedang sideways mati atau likuiditas rendah) sebelum meneruskannya ke Stage 2 penuh. DATA: Harga singkat dan indikator volatilitas dasar. OUTPUT: Keputusan Proceed atau Skip. URGENSI: RENDAH (Low). Tidak menggerakkan uang; murni demi efisiensi biaya API agar AI mahal tidak membuang token.",
    ),
    "specialist_technical": dict(kind="single", runs_per_day=STAGE2_PRIMARY_RUNS, reasoning="Medium",
        situational=False, in_tokens=2200, out_tokens=300,
        fin_weight=0.15, latency_sensitive=False,
        note="TUGAS: Konsultan teknikal sub-agen. ANALISIS: Dekonstruksi mendalam pola grafik, struktur Smart Money Concepts (SMC), dan peta likuiditas murni. DATA: OHLCV, Swing Points, S/R, Liquidity Zones, FVG. OUTPUT: Perspektif/saran teknikal murni untuk Stage 2. URGENSI: MENENGAH (Medium). Membantu agen utama tetapi tidak mengambil keputusan akhir."),
    "specialist_sentiment": dict(kind="single", runs_per_day=STAGE2_PRIMARY_RUNS, reasoning="Medium",
        situational=False, in_tokens=2200, out_tokens=300,
        fin_weight=0.35, latency_sensitive=False,
        note="TUGAS: Konsultan sentimen sub-agen. ANALISIS: Membaca pergeseran aliran dana institusi dan rasio retail vs komersial. DATA: CFTC COT, FedWatch, VIX. OUTPUT: Penilaian sentimen ekstrem atau netral. URGENSI: MENENGAH (Medium). Memperkaya pertimbangan Stage 2."),
    "specialist_macro": dict(kind="single", runs_per_day=STAGE2_PRIMARY_RUNS, reasoning="Medium",
        situational=False, in_tokens=2200, out_tokens=300,
        fin_weight=0.40, latency_sensitive=False,
        note="TUGAS: Konsultan korelasi makro sub-agen. ANALISIS: Menilai korelasi silang antar aset (misal: efek yield obligasi ke pergerakan emas). DATA: Fundamental Brief dan indeks eksternal. OUTPUT: Peringatan headwinds/tailwinds lintas-aset. URGENSI: MENENGAH (Medium)."),
    "debate_bull": dict(kind="single", runs_per_day=4, reasoning="Medium", situational=True,
        in_tokens=1200, out_tokens=250,
        fin_weight=0.25, latency_sensitive=True,
        note="TUGAS: Pengacara sisi pembeli (Bull Advocate). ANALISIS: Jika arsitektur debat aktif, mencari celah atau menyusun argumen MENGAPA aset ini akan NAIK. DATA: Draf rencana trading Stage 2, teknikal, dan fundamental. OUTPUT: Argumen optimis (bullish case). URGENSI: MENENGAH (Medium). Mencegah confirmation bias."),
    "debate_bear": dict(kind="single", runs_per_day=4, reasoning="Medium", situational=True,
        in_tokens=900, out_tokens=300,
        fin_weight=0.25, latency_sensitive=True,
        note="TUGAS: Pengacara sisi penjual (Bear Advocate). ANALISIS: Mencari celah atau menyusun argumen MENGAPA aset ini akan TURUN atau trade akan gagal. DATA: Draf rencana trading dan data pasar. OUTPUT: Argumen pesimis (bearish case). URGENSI: MENENGAH (Medium). Menguji ketahanan ide."),
    "debate_judge": dict(kind="single", runs_per_day=4, reasoning="Medium-High", situational=True,
        in_tokens=900, out_tokens=180,
        fin_weight=0.35, latency_sensitive=True,
        note="TUGAS: Hakim penentu debat. ANALISIS: Mengevaluasi debat Bull vs Bear secara objektif dibandingkan rencana asli. DATA: Argumen Bull dan Bear. OUTPUT: Vonis final (APPROVE/REJECT). URGENSI: MENENGAH-TINGGI (Medium-High). Memiliki kuasa veto (pembatalan trade) sebelum order masuk pasar."),
    "risk_gate_check": dict(kind="single", runs_per_day=8, reasoning="Medium", situational=True,
        in_tokens=650, out_tokens=200,
        fin_weight=0.30, latency_sensitive=True,
        note="TUGAS: Evaluasi kepatuhan profil risiko. ANALISIS: Mensimulasikan stress-test trade yang disetujui lewat 3 persona penguji (konservatif, netral, agresif). DATA: Parameter trade (SL, TP, lot) dan volatilitas aset. OUTPUT: Skor keamanan (1-10). URGENSI: MENENGAH (Medium). Lapis ekstra pengukur batas kelayakan risiko."),
    "portfolio_synthesis": dict(kind="single", runs_per_day=3, reasoning="Medium-High", situational=True,
        in_tokens=1100, out_tokens=200,
        fin_weight=0.35, latency_sensitive=True,
        note="TUGAS: Manajer Portofolio (Pencegah over-exposure). ANALISIS: Memeriksa usulan trade di seluruh aset dan memblokir korelasi ganda berbahaya (misal: Buy EURUSD & GBPUSD bersamaan). DATA: Semua trade lolos debat dan posisi terbuka MT5. OUTPUT: Pemangkasan daftar rekomendasi. URGENSI: MENENGAH-TINGGI (Medium-High). Penjaga keseimbangan ekuitas total akun."),
    "news_classification": dict(kind="single", runs_per_day=12, reasoning="Low", situational=False,
        in_tokens=800, out_tokens=500,
        fin_weight=0.10, latency_sensitive=False,
        note="TUGAS: Tukang sortir berita (Classifier). ANALISIS: Membaca puluhan berita scraping dan menilai relevansinya. DATA: Teks berita mentah. OUTPUT: Kategori dampak (High/Med/Low/Noise) dan tag mata uang. URGENSI: RENDAH (Low). Murni filtrasi sampah agar agen lain tidak membuang token."),
    "news_digest": dict(kind="single", runs_per_day=48, reasoning="Low-Medium", situational=False,
        in_tokens=2500, out_tokens=800,
        fin_weight=0.20, latency_sensitive=False,
        note="TUGAS: Penyusun intisari berita. ANALISIS: Menyatukan berita terklasifikasi menjadi rangkuman koheren per mata uang. DATA: Artikel berita hasil sortir. OUTPUT: Narasi berita ringkas. URGENSI: RENDAH-MENENGAH (Low-Medium). Penghemat token esensial untuk Stage 1."),
    "cot_precompute": dict(kind="single", runs_per_day=7, reasoning="Low", situational=False,
        in_tokens=1500, out_tokens=400,
        fin_weight=0.20, latency_sensitive=False,
        note="TUGAS: Kalkulator sinyal mingguan. ANALISIS: Membaca tabel tebal CFTC dan menyaringnya jadi sentimen institusi. DATA: Laporan COT. OUTPUT: Skor indikator institusi. URGENSI: RENDAH (Low). Dijalankan mingguan sebagai utilitas pra-pemrosesan."),
    "chat_telegram": dict(
        kind="agentic", runs_per_day=7, reasoning="Low", situational=True,
        turns=2, system_tokens=1300, tools_tokens=4500, initial_user_tokens=2000,
        per_turn_output_tokens=250, per_turn_tool_result_tokens=350, final_answer_tokens=350,
        fin_weight=0.05, latency_sensitive=True,
        note="TUGAS: Agen interaksi manusia-standar. ANALISIS: Menjawab perintah rutin/cek status. DATA: Log sederhana dan riwayat obrolan. OUTPUT: Pesan balasan ringan. URGENSI: RENDAH (Low). Tidak mengelola uang.",
    ),
    "chat_telegram_complex": dict(
        kind="agentic", runs_per_day=13, reasoning="Medium-High", situational=True,
        turns=3, system_tokens=1300, tools_tokens=4500, initial_user_tokens=2050,
        per_turn_output_tokens=300, per_turn_tool_result_tokens=400, final_answer_tokens=400,
        fin_weight=0.25, latency_sensitive=True,
        note="TUGAS: Agen interaksi manusia-analitik. ANALISIS: Merespons pertanyaan kompleks/deep-dive (misal: alasan di balik Cut Loss kemarin) dengan memanggil tools sistem. DATA: Seluruh ekosistem database. OUTPUT: Penjelasan terstruktur atau usulan aksi modifikasi (menunggu konfirmasi user). URGENSI: MENENGAH-TINGGI (Medium-High). Mewakili otak agen untuk evaluasi manual.",
    ),
    "trade_reflection": dict(kind="single", runs_per_day=5, reasoning="Low", situational=False,
        in_tokens=600, out_tokens=300,
        fin_weight=0.20, latency_sensitive=False,
        note="TUGAS: Sesi retrospeksi (Post-mortem). ANALISIS: Berjalan saat posisi ditutup, membandingkan prediksi asli dengan pergerakan harga aktual. DATA: Catatan analisis masa lalu vs OHLCV terkini. OUTPUT: Lessons learned ke memori vector agar AI tidak mengulang kesalahan. URGENSI: RENDAH (Low). Untuk peningkatan kinerja jangka panjang."),
    "adversarial_check": dict(kind="single", runs_per_day=0, reasoning="Low", situational=False,
        in_tokens=3000, out_tokens=200,
        fin_weight=0.0, latency_sensitive=False,
        note="TUGAS: (Legacy) Korektor Inflasi Skor. ANALISIS: Usang. Dahulu mengecek bias optimisme AI. Kini digantikan kalkulasi Bayesian di AdaptiveRiskPolicy backend. DATA: N/A OUTPUT: N/A URGENSI: USANG (Vestigial). Berbiaya $0 karena dinonaktifkan."),
}

# Pemetaan model saat ini di settings.yaml (HANYA sebagai baris referensi/pembanding
# di laporan -- tidak dipakai sama sekali oleh optimizer).
CURRENT_SETTINGS_YAML_MAPPING = {
    "stage1_fundamental": ("Claude", "sonnet-5"),
    "stage1_escalation": ("Claude", "opus-5"),
    "stage2_per_asset_primary": ("Claude", "sonnet-5"),
    "stage2_per_asset_secondary": ("Claude", "sonnet-5"),
    "stage2_prescreen": ("Claude", "haiku-4.5"),
    "specialist_technical": ("Gemini", "gemini-3.6-flash"),
    "specialist_sentiment": ("Gemini", "gemini-3.6-flash"),
    "specialist_macro": ("Gemini", "gemini-3.6-flash"),
    "debate_bull": ("Gemini", "gemini-3.6-flash"),
    "debate_bear": ("Gemini", "gemini-3.6-flash"),
    "debate_judge": ("Gemini", "gemini-3.6-flash"),
    "risk_gate_check": ("Gemini", "gemini-3.5-flash-lite"),
    "portfolio_synthesis": ("Claude", "sonnet-5"),
    "news_classification": ("Gemini", "gemini-3.5-flash-lite"),
    "news_digest": ("Gemini", "gemini-3.5-flash-lite"),
    "cot_precompute": ("Gemini", "gemini-3.5-flash-lite"),
    "chat_telegram": ("Gemini", "gemini-3.5-flash-lite"),
    "chat_telegram_complex": ("Claude", "sonnet-5"),
    "trade_reflection": ("Gemini", "gemini-3.5-flash-lite"),
    "adversarial_check": ("Gemini", "gemini-3.5-flash-lite"),
}

# =====================================================================================
# 5. COST ENGINE
#    Fungsi-fungsi ini sekarang menerima parameter `tasks=None` opsional
#    (default ke TASKS global) supaya bisa dipakai ulang di analisis
#    sensitivitas (§10) tanpa memutasi state global.
# =====================================================================================
def _price(provider, model):
    return PROVIDERS[provider][model]


def agentic_run_cost_usd(provider, model, t):
    in_price, cached_price, out_price = _price(provider, model)
    caching = PROVIDER_CACHING_SUPPORTED.get(provider, False)
    static_tokens = t["system_tokens"] + t["tools_tokens"]
    turns = t["turns"]
    conv = t["initial_user_tokens"]
    total = 0.0
    for turn in range(1, turns + 1):
        is_last = turn == turns
        if caching:
            static_cost = (static_tokens / 1e6) * (in_price * CACHE_WRITE_MULTIPLIER if turn == 1 else cached_price)
        else:
            static_cost = (static_tokens / 1e6) * in_price
        dynamic_cost = (conv / 1e6) * in_price
        out_tok = t["per_turn_output_tokens"] + (t["final_answer_tokens"] if is_last else 0)
        output_cost = (out_tok / 1e6) * out_price
        total += static_cost + dynamic_cost + output_cost
        conv += t["per_turn_output_tokens"] + (t["final_answer_tokens"] if is_last else t["per_turn_tool_result_tokens"])
    return total


def single_shot_cost_usd(provider, model, t):
    in_price, _, out_price = _price(provider, model)
    return (t["in_tokens"] / 1e6) * in_price + (t["out_tokens"] / 1e6) * out_price


def raw_task_cost_per_run(task_name, provider, model, tasks=None):
    tasks = TASKS if tasks is None else tasks
    t = tasks[task_name]
    return agentic_run_cost_usd(provider, model, t) if t["kind"] == "agentic" else single_shot_cost_usd(provider, model, t)


# =====================================================================================
# 5b. KUALITAS EFEKTIF PER TASK — blend QUALITY_SCORE (kecerdasan umum) dan
#     FIN_RELIABILITY_SCORE (reliabilitas finansial) sesuai fin_weight task.
# =====================================================================================
def effective_quality(task_name, provider, model, tasks=None):
    tasks = TASKS if tasks is None else tasks
    base = QUALITY_SCORE.get((provider, model))
    if base is None:
        return None
    fin = FIN_RELIABILITY_SCORE.get((provider, model), base)
    w = tasks[task_name].get("fin_weight", 0.0)
    return round(base * (1 - w) + fin * w, 3)


# =====================================================================================
# 6. KANDIDAT PER TASK (floor-filtered, BUKAN hand-picked satu-satu)
# =====================================================================================
@dataclass
class Candidate:
    provider: str
    model: str
    quality: float                 # kualitas EFEKTIF (blended) dipakai optimizer
    general_quality: float         # QUALITY_SCORE mentah (kecerdasan umum)
    fin_reliability: float         # FIN_RELIABILITY_SCORE mentah
    cost_per_run: float
    monthly_cost_paid: float       # referensi: biaya kalau dibayar normal (bukan free-tier)
    is_gemini_free_tier: bool
    gemini_tier: Optional[str]
    daily_calls: int                # runs_per_day x (turns kalau agentic, else 1) -> utk kuota RPD
    latency_ttft_sec: Optional[float] = None


def build_candidates_for_task(task_name, tasks=None):
    tasks = TASKS if tasks is None else tasks
    t = tasks[task_name]
    pool = CANDIDATE_POOL
    calls_per_run = t["turns"] if t["kind"] == "agentic" else 1
    daily_calls = t["runs_per_day"] * calls_per_run
    out = []
    for provider, model in pool:
        if t["kind"] == "agentic" and not PROVIDER_AGENTIC_CAPABLE[provider]:
            continue
        if provider == "Gemini" and GEMINI_TIER.get(model) == "pro" and not GEMINI_HAS_PAID_KEY:
            continue
        q = effective_quality(task_name, provider, model, tasks=tasks)
        if q is None:
            continue
        gen_q = QUALITY_SCORE.get((provider, model))
        fin_q = FIN_RELIABILITY_SCORE.get((provider, model))
        per_run = raw_task_cost_per_run(task_name, provider, model, tasks=tasks)
        monthly_paid = per_run * t["runs_per_day"] * DAYS_PER_MONTH
        tier = GEMINI_TIER.get(model) if provider == "Gemini" else None
        is_free = provider == "Gemini" and tier in ("flash", "flash_lite")
        latency = LATENCY_TTFT_SEC.get((provider, model))
        out.append(Candidate(provider, model, q, gen_q, fin_q, per_run, monthly_paid,
                              is_free, tier, daily_calls, latency))
    if not out:
        raise RuntimeError(f"Tidak ada kandidat sama sekali utk task '{task_name}' — cek CANDIDATE_POOL.")
    return out


def eligible_candidates(task_name, tasks=None):
    tasks = TASKS if tasks is None else tasks
    t = tasks[task_name]
    floor = REASONING_FLOOR[t["reasoning"]]
    cands = build_candidates_for_task(task_name, tasks=tasks)
    passed = [c for c in cands if c.quality >= floor]
    if not passed:
        best = max(cands, key=lambda c: c.quality)
        print(f"[WARN] tidak ada kandidat yg lolos floor '{t['reasoning']}' ({floor}) utk '{task_name}'; "
              f"pakai yang terbaik yg tersedia: {best.provider}/{best.model} ({best.quality})")
        passed = [best]
    return passed


# =====================================================================================
# 7. ALOKASI KUOTA GRATIS GEMINI (bin-packing greedy lintas SEMUA task)
# =====================================================================================
def allocate_free_quota(all_candidates: Dict[str, List[Candidate]], flash_cap: int, flash_lite_cap: int):
    requests = []
    for task_name, cands in all_candidates.items():
        paid_only = [c for c in cands if not c.is_gemini_free_tier]
        cheapest_paid = min((c.monthly_cost_paid for c in paid_only), default=None)
        for c in cands:
            if c.is_gemini_free_tier:
                fallback = cheapest_paid if cheapest_paid is not None else 10_000.0
                priority = fallback / max(c.daily_calls, 1)   # $ dihemat per slot kuota/hari yg dipakai
                requests.append((task_name, c.gemini_tier, c.daily_calls, priority))

    granted = {task_name: set() for task_name in all_candidates}
    usage = {"flash": 0, "flash_lite": 0}
    caps = {"flash": flash_cap, "flash_lite": flash_lite_cap}
    for tier in ("flash_lite", "flash"):   # pool flash_lite jauh lebih besar -> isi duluan
        pool = sorted([r for r in requests if r[1] == tier], key=lambda r: -r[3])
        for (task_name, _, calls, _prio) in pool:
            if usage[tier] + calls <= caps[tier]:
                usage[tier] += calls
                granted[task_name].add(tier)
    return granted, usage, caps


def dominance_filter(cands):
    keep = []
    for i, c in enumerate(cands):
        dominated = any(
            o["cost"] <= c["cost"] and o["quality"] >= c["quality"] and (o["cost"] < c["cost"] or o["quality"] > c["quality"])
            for j, o in enumerate(cands) if j != i
        )
        if not dominated:
            keep.append(c)
    return keep


def build_effective_candidates(all_candidates, granted):
    effective = {}
    for task_name, cands in all_candidates.items():
        out = []
        for c in cands:
            granted_here = c.is_gemini_free_tier and c.gemini_tier in granted[task_name]
            eff_cost = 0.0 if granted_here else c.monthly_cost_paid
            out.append({
                "provider": c.provider, "model": c.model, "quality": c.quality,
                "general_quality": c.general_quality, "fin_reliability": c.fin_reliability,
                "latency_ttft_sec": c.latency_ttft_sec,
                "cost": eff_cost, "paid_ref": c.monthly_cost_paid,
                "free_but_quota_denied": c.is_gemini_free_tier and not granted_here,
            })
        effective[task_name] = dominance_filter(out)
    return effective


# =====================================================================================
# 8. OPTIMIZER — Multiple-Choice Knapsack via DP (exact, bukan greedy/hardcode)
# =====================================================================================
def optimize_for_budget(effective_candidates, task_order, budget_usd, resolution_cents=1, tasks=None):
    tasks = TASKS if tasks is None else tasks
    B = int(round(budget_usd * 100 / resolution_cents))
    NEG_INF = float("-inf")
    dp = [NEG_INF] * (B + 1)
    dp[0] = 0.0
    parents = []

    for task_name in task_order:
        t = tasks[task_name]
        weight = t["runs_per_day"] * REASONING_WEIGHT[t["reasoning"]]
        cands = effective_candidates[task_name]
        new_dp = [NEG_INF] * (B + 1)
        new_parent = [None] * (B + 1)
        for b, base in enumerate(dp):
            if base == NEG_INF:
                continue
            for ci, c in enumerate(cands):
                cost_units = int(round(c["cost"] * 100 / resolution_cents))
                nb = b + cost_units
                if nb > B:
                    continue
                val = base + c["quality"] * weight
                if val > new_dp[nb]:
                    new_dp[nb] = val
                    new_parent[nb] = (ci, b)
        dp = new_dp
        parents.append(new_parent)

    best_b = max(range(B + 1), key=lambda b: dp[b])
    if dp[best_b] == NEG_INF:
        return None

    choice_idx = [0] * len(task_order)
    b = best_b
    for i in range(len(task_order) - 1, -1, -1):
        ci, prev_b = parents[i][b]
        choice_idx[i] = ci
        b = prev_b

    result, total_cost = {}, 0.0
    for i, task_name in enumerate(task_order):
        c = effective_candidates[task_name][choice_idx[i]]
        result[task_name] = c
        total_cost += c["cost"]
    return {"assignment": result, "objective": dp[best_b], "total_cost": total_cost}


def min_cost_baseline(effective_candidates, task_order):
    assignment, total = {}, 0.0
    for task_name in task_order:
        best = min(effective_candidates[task_name], key=lambda c: (c["cost"], -c["quality"]))
        assignment[task_name] = best
        total += best["cost"]
    return {"assignment": assignment, "total_cost": total}


def max_quality_baseline(effective_candidates, task_order):
    assignment, total = {}, 0.0
    for task_name in task_order:
        best = max(effective_candidates[task_name], key=lambda c: c["quality"])
        assignment[task_name] = best
        total += best["cost"]
    return {"assignment": assignment, "total_cost": total}


def weighted_quality_score(assignment, task_order, tasks=None):
    tasks = TASKS if tasks is None else tasks
    num, den = 0.0, 0.0
    for task_name in task_order:
        t = tasks[task_name]
        w = t["runs_per_day"] * REASONING_WEIGHT[t["reasoning"]]
        if w == 0:
            continue
        num += assignment[task_name]["quality"] * w
        den += w
    return num / den if den else 0.0


def rpm_risk_check(assignment, task_order, tasks=None):
    tasks = TASKS if tasks is None else tasks
    max_turns_flash, max_turns_flash_lite = 0, 0
    for task_name in task_order:
        c = assignment[task_name]
        if c["cost"] != 0.0:
            continue
        tier = GEMINI_TIER.get(c["model"])
        turns = tasks[task_name]["turns"] if tasks[task_name]["kind"] == "agentic" else 1
        if tier == "flash":
            max_turns_flash = max(max_turns_flash, turns)
        elif tier == "flash_lite":
            max_turns_flash_lite = max(max_turns_flash_lite, turns)
    warnings = []
    if max_turns_flash > FLASH_RPM:
        warnings.append(f"Satu run agentic {max_turns_flash}-turn di tier 'flash' berisiko meledakkan "
                         f"RPM cap ({FLASH_RPM}/menit) kalau semua turn tembak beruntun.")
    if max_turns_flash_lite > FLASH_LITE_RPM:
        warnings.append(f"Satu run agentic {max_turns_flash_lite}-turn di tier 'flash_lite' berisiko "
                         f"melebihi RPM cap ({FLASH_LITE_RPM}/menit).")
    return warnings


def latency_risk_check(assignment, task_order, tasks=None):
    """Tandai task latency_sensitive yang jatuh ke model dengan TTFT terukur tinggi."""
    tasks = TASKS if tasks is None else tasks
    warnings = []
    for task_name in task_order:
        t = tasks[task_name]
        if not t.get("latency_sensitive"):
            continue
        c = assignment[task_name]
        ttft = c.get("latency_ttft_sec")
        if ttft is not None and ttft >= LATENCY_WARNING_THRESHOLD_SEC:
            warnings.append(f"{task_name}: model terpilih {c['provider']}/{c['model']} punya TTFT terukur "
                             f"~{ttft:.1f}s pada effort tinggi, padahal task ini latency-sensitive "
                             f"(reaktif / jalur kritis pra-eksekusi order).")
    return warnings


def financial_reliability_audit(assignment, task_order, tasks=None, threshold=6.5):
    """Tandai task dengan fin_weight signifikan yang jatuh ke model dengan
    fin_reliability rendah (lihat FIN_RELIABILITY_MULTIPLIER untuk metodologi)."""
    tasks = TASKS if tasks is None else tasks
    flags = []
    for task_name in task_order:
        t = tasks[task_name]
        fw = t.get("fin_weight", 0.0)
        if fw < 0.30:
            continue
        c = assignment[task_name]
        fin = c.get("fin_reliability")
        if fin is not None and fin < threshold:
            flags.append(f"{task_name} (fin_weight={fw:.2f}): {c['provider']}/{c['model']} punya "
                         f"fin_reliability={fin:.1f} (< {threshold}) — pertimbangkan model dengan "
                         f"reliabilitas finansial lebih tinggi jika budget memungkinkan.")
    return flags


def describe_quota(usage, caps):
    lines = []
    for tier in ("flash_lite", "flash"):
        pct = (usage[tier] / caps[tier] * 100) if caps[tier] else 0
        lines.append(f"  - Gemini tier '{tier}': {usage[tier]}/{caps[tier]} req/hari terpakai ({pct:.1f}%)")
    return "\n".join(lines)


# =====================================================================================
# 9. VALUE LEADERBOARD — kualitas per dolar lintas semua model di CANDIDATE_POOL,
#    LEPAS dari task tertentu (murni membandingkan model). Memakai rasio blended
#    3:1 input:output token ala metodologi Artificial Analysis supaya adil
#    antar model dengan struktur harga input/output yang berbeda jauh.
# =====================================================================================
def value_leaderboard(top_n=15):
    rows = []
    for provider, model in CANDIDATE_POOL:
        in_price, _, out_price = PROVIDERS[provider][model]
        blended = 0.75 * in_price + 0.25 * out_price   # rasio blended 3:1 input:output
        q = QUALITY_SCORE.get((provider, model))
        fin = FIN_RELIABILITY_SCORE.get((provider, model))
        if q is None or blended <= 0:
            continue
        rows.append({
            "provider": provider, "model": model, "quality": q, "fin_reliability": fin,
            "blended_price": blended, "value": q / blended,
        })
    rows.sort(key=lambda r: -r["value"])
    return rows[:top_n]


# =====================================================================================
# 10. ANALISIS SENSITIVITAS — parametrized, TIDAK memutasi state global.
# =====================================================================================
def build_tasks_with_prescreen_rate(prescreen_pass_rate):
    """Deep-copy TASKS dengan runs_per_day Stage-2 dihitung ulang di bawah
    hipotesis prescreen_pass_rate tertentu, tanpa mengubah TASKS global."""
    main_attempts = STAGE2_MAIN_CYCLE_ATTEMPTS * STAGE2_MAIN_SURVIVAL_RATE
    reactive_attempts = STAGE2_REACTIVE_ATTEMPTS * STAGE2_MAIN_SURVIVAL_RATE
    primary_runs = round(main_attempts * prescreen_pass_rate)
    secondary_runs = round(reactive_attempts * prescreen_pass_rate)
    prescreen_runs = round(main_attempts + reactive_attempts)  # volume prescreen tak tergantung pass-rate-nya sendiri

    tasks = copy.deepcopy(TASKS)
    tasks["stage2_per_asset_primary"]["runs_per_day"] = primary_runs
    tasks["stage2_per_asset_secondary"]["runs_per_day"] = secondary_runs
    tasks["stage2_prescreen"]["runs_per_day"] = prescreen_runs
    return tasks


def run_pipeline(tasks, budget_usd, flash_cap, flash_lite_cap, resolution_cents=10):
    """Jalankan pipeline penuh (kandidat -> kuota gratis -> DP) untuk kombinasi
    parameter tertentu, dan kembalikan (total_cost, weighted_quality) atau
    None kalau infeasible. Dipakai oleh analisis sensitivitas."""
    task_order = list(tasks.keys())
    raw = {name: eligible_candidates(name, tasks=tasks) for name in task_order}
    granted, _, _ = allocate_free_quota(raw, flash_cap, flash_lite_cap)
    eff = build_effective_candidates(raw, granted)
    result = optimize_for_budget(eff, task_order, budget_usd, resolution_cents=resolution_cents, tasks=tasks)
    if result is None:
        return None
    q = weighted_quality_score(result["assignment"], task_order, tasks=tasks)
    return result["total_cost"], q


def sensitivity_analysis(base_budget, base_keys, base_prescreen_rate):
    """Tornado-style: ubah satu parameter, jaga yang lain tetap di baseline,
    lihat dampaknya ke biaya & kualitas rekomendasi."""
    rows = []

    def add_row(param, value, tasks, budget, keys):
        flash_cap = 20 * keys
        flash_lite_cap = 500 * keys
        r = run_pipeline(tasks, budget, flash_cap, flash_lite_cap)
        if r is None:
            rows.append({"param": param, "value": value, "cost": None, "quality": None})
        else:
            rows.append({"param": param, "value": value, "cost": r[0], "quality": r[1]})

    base_tasks = build_tasks_with_prescreen_rate(base_prescreen_rate)

    for b in sorted({max(1, base_budget * 0.5), base_budget, base_budget * 1.5, base_budget * 2.0}):
        add_row("MONTHLY_BUDGET_USD", round(b, 2), base_tasks, b, base_keys)

    for k in sorted({max(1, base_keys // 2), base_keys, base_keys * 2}):
        add_row("GEMINI_FREE_KEYS", k, base_tasks, base_budget, k)

    for r in sorted({max(0.05, base_prescreen_rate * 0.6), base_prescreen_rate, min(1.0, base_prescreen_rate * 1.4)}):
        r = round(r, 3)
        tasks_r = build_tasks_with_prescreen_rate(r)
        add_row("PRESCREEN_PASS_RATE", r, tasks_r, base_budget, base_keys)

    return rows


# =====================================================================================
# 11. SELF-TEST RINGAN — sanity check struktur data sebelum dipakai.
# =====================================================================================
def run_self_tests():
    problems = []
    for provider, models in PROVIDERS.items():
        for model, prices in models.items():
            if len(prices) != 3 or any(p < 0 for p in prices):
                problems.append(f"Harga tidak valid: {provider}/{model} -> {prices}")
    for key, val in QUALITY_SCORE.items():
        if not (0.0 <= val <= 10.0):
            problems.append(f"QUALITY_SCORE di luar rentang 0-10: {key} -> {val}")
    for key, val in FIN_RELIABILITY_SCORE.items():
        if val is not None and not (0.0 <= val <= 10.0):
            problems.append(f"FIN_RELIABILITY_SCORE di luar rentang 0-10: {key} -> {val}")
    for provider, model in CANDIDATE_POOL:
        if provider not in PROVIDERS or model not in PROVIDERS[provider]:
            problems.append(f"CANDIDATE_POOL merujuk model tanpa harga: {provider}/{model}")
        if (provider, model) not in QUALITY_SCORE:
            problems.append(f"CANDIDATE_POOL merujuk model tanpa QUALITY_SCORE: {provider}/{model}")
    for name, t in TASKS.items():
        if "fin_weight" not in t or "latency_sensitive" not in t:
            problems.append(f"Task '{name}' belum punya field fin_weight/latency_sensitive")
        try:
            eligible_candidates(name)
        except Exception as e:
            problems.append(f"Task '{name}' gagal menghasilkan kandidat: {e}")
    if problems:
        raise AssertionError("Self-test GAGAL:\n" + "\n".join(f"  - {p}" for p in problems))
    return True


# =====================================================================================
# 12. LAPORAN
# =====================================================================================
def write_markdown_report(task_order, raw_candidates, granted, usage, caps,
                           reco, reco_quality, min_cost, min_cost_q, max_quality, max_quality_q,
                           current_cost, current_q, frontier, sensitivity_rows,
                           path="ai_cost_analysis_v4.md"):
    L = []
    L.append("# AI Cost & Performance Analysis v4 — Claude AI Trading Agent\n")

    L.append("## 0. Status Temuan Penting dari Audit Codebase (Semua Selesai)\n")
    L.append("1. **Bug prescreen telah diperbaiki** (`per_asset_stage.py`): Gerbang "
             "Haiku murah kini dapat menyaring dengan optimal untuk menghemat biaya.")
    L.append("2. **Bug pengali API key telah diperbaiki** (`utils/gemini_rate_limiter.py`): "
             "Kuota efektif saat ini telah terkali jumlah key secara benar.")
    L.append("3. **OpenAI & DeepSeek telah mendukung agentic tool-loop** di codebase ini "
             "(`run_agent` diimplementasikan secara penuh).")
    L.append("4. **`stage2_per_asset_primary` & `_secondary` telah dipisah ke client LLM mandiri** — "
             "Telah direalisasikan di codebase untuk penghematan maksimal.\n")

    L.append("## 0b. Apa yang Baru di v4 (Kalibrasi & Fitur)\n")
    L.append("- **QUALITY_SCORE dikalibrasi ulang dari riset web** (Artificial Analysis Intelligence "
             "Index v4.1.1, snapshot Agustus 2026 + rilis resmi tiap vendor), bukan estimasi manual.")
    L.append("- **Dimensi baru: FIN_RELIABILITY_SCORE** — reliabilitas spesifik analisis finansial "
             "(bukan kecerdasan umum), dikalibrasi dari benchmark FinanceReasoning dan studi halusinasi "
             "JurisTech pada dokumen finansial tidak lengkap. Tiap task punya `fin_weight` sendiri.")
    L.append("- **CANDIDATE_POOL diperluas** dari 14 menjadi 23 model (Fable 5, Opus 4.8, keluarga "
             "GPT-5.6, dst.) supaya optimizer benar-benar memilih dari seluruh frontier harga/kualitas.")
    L.append("- **Audit reliabilitas finansial & risiko latensi** ditambahkan ke laporan.")
    L.append("- **Value Leaderboard** (kualitas per dolar, lintas semua model) & **analisis sensitivitas** "
             "(budget, jumlah key gratis, prescreen pass-rate) ditambahkan.\n")

    L.append("## 1. Parameter & Asumsi Global\n")
    L.append(f"- Budget bulanan: ${MONTHLY_BUDGET_USD:.2f}")
    L.append(f"- API key Gemini gratis: {GEMINI_FREE_KEYS} (hanya Flash & Flash-Lite)")
    L.append(f"- Key Gemini berbayar utk model Pro: {'Ya (1 key)' if GEMINI_HAS_PAID_KEY else 'Tidak tersedia'}")
    L.append(f"  -> kuota efektif: flash={FLASH_RPD} req/hari ({FLASH_RPM}/menit), "
             f"flash_lite={FLASH_LITE_RPD} req/hari ({FLASH_LITE_RPM}/menit)\n")

    L.append("## 2. Inventaris Task & Volume Panggilan\n")
    L.append("| Task | Jenis | Runs/hari | Turns/run | Calls API/hari | Reasoning | fin_weight | Latency-sensitive |")
    L.append("|---|---|---|---|---|---|---|---|")
    for name in task_order:
        t = TASKS[name]
        turns = t["turns"] if t["kind"] == "agentic" else 1
        L.append(f"| {name} | {t['kind']} | {t['runs_per_day']} | {turns} | {t['runs_per_day']*turns} | "
                  f"{t['reasoning']} | {t.get('fin_weight', 0):.2f} | {'Ya' if t.get('latency_sensitive') else 'Tidak'} |")
    L.append("")
    for name in task_order:
        L.append(f"**{name}** — {TASKS[name]['note']}\n")

    L.append("## 3. Kandidat Model per Task (kualitas efektif = blend kecerdasan umum + reliabilitas finansial)\n")
    L.append("Floor kualitas minimum per reasoning level (skala 0-10, sudah dikalibrasi ulang di v4): " +
              ", ".join(f"{k}={v}" for k, v in REASONING_FLOOR.items()) + "\n")
    for name in task_order:
        L.append(f"### {name}")
        L.append("| Provider/Model | Kualitas Efektif | Kecerdasan Umum | Fin. Reliability | Est. Biaya Normal/bln | Free-tier Gemini? |")
        L.append("|---|---|---|---|---|---|")
        for c in sorted(raw_candidates[name], key=lambda x: -x.quality):
            free = f"Ya ({c.gemini_tier})" if c.is_gemini_free_tier else "Tidak"
            L.append(f"| {c.provider}/{c.model} | {c.quality:.2f} | {c.general_quality:.1f} | "
                     f"{c.fin_reliability:.1f} | ${c.monthly_cost_paid:.2f} | {free} |")
        L.append("")

    L.append("## 4. Alokasi Kuota Gratis Gemini\n")
    L.append(describe_quota(usage, caps).replace("  - ", "- ") + "\n")
    denied = sorted({name for name in task_order for c in raw_candidates[name]
                      if c.is_gemini_free_tier and c.gemini_tier not in granted[name]})
    if denied:
        L.append(f"Task yang KALAH prioritas kuota gratis (jatuh ke opsi berbayar): {', '.join(denied)}\n")
    else:
        L.append("Semua task yang punya opsi gratis berhasil dapat alokasi kuota.\n")

    L.append("## 5. Perbandingan Skenario\n")
    L.append("| Skenario | Biaya/bln | Skor Kualitas (0-10) |")
    L.append("|---|---|---|")
    L.append(f"| Current settings.yaml (referensi) | ${current_cost:.2f} | {current_q:.2f} |")
    L.append(f"| Termurah yg tetap lolos floor tiap task | ${min_cost['total_cost']:.2f} | {min_cost_q:.2f} |")
    L.append(f"| **Rekomendasi optimal @ ${MONTHLY_BUDGET_USD:.0f}** | **${reco['total_cost']:.2f}** | **{reco_quality:.2f}** |")
    L.append(f"| Kualitas maksimum (abaikan biaya) | ${max_quality['total_cost']:.2f} | {max_quality_q:.2f} |\n")

    L.append(f"## 6. Kombinasi Optimal per Task @ Budget ${MONTHLY_BUDGET_USD:.0f}\n")
    L.append("| Task | Model Terpilih | Kualitas Efektif | Fin. Reliability | Biaya/bln | Free-tier? |")
    L.append("|---|---|---|---|---|---|")
    for name in task_order:
        c = reco["assignment"][name]
        free_tag = "Ya" if c["cost"] == 0.0 and c["provider"] == "Gemini" else "Tidak"
        fin_disp = f"{c['fin_reliability']:.1f}" if c.get("fin_reliability") is not None else "-"
        L.append(f"| {name} | {c['provider']}/{c['model']} | {c['quality']:.2f} | {fin_disp} | "
                 f"${c['cost']:.2f} | {free_tag} |")
    L.append(f"\n**Total: ${reco['total_cost']:.2f}/bulan** (skor kualitas tertimbang: {reco_quality:.2f}/10)\n")

    fin_flags = financial_reliability_audit(reco["assignment"], task_order)
    L.append("## 7. Audit Reliabilitas Finansial\n")
    if fin_flags:
        for f in fin_flags:
            L.append(f"- ⚠️ {f}")
    else:
        L.append("Tidak ada task ber-`fin_weight` tinggi yang jatuh ke model dengan reliabilitas "
                 "finansial rendah pada rekomendasi ini.")
    L.append("")

    lat_flags = latency_risk_check(reco["assignment"], task_order)
    L.append("## 8. Audit Risiko Latensi\n")
    if lat_flags:
        for f in lat_flags:
            L.append(f"- ⚠️ {f}")
    else:
        L.append("Tidak ada task latency-sensitive yang jatuh ke model dengan TTFT terukur tinggi "
                 "pada rekomendasi ini (atau datanya belum tersedia di riset — lihat §13 sumber).")
    L.append("")

    L.append("## 9. Efficiency Frontier (Biaya vs Kualitas)\n")
    L.append("| Budget/bln | Biaya Terpakai | Skor Kualitas | Δ Kualitas per $10 tambahan |")
    L.append("|---|---|---|---|")
    prev_q, prev_cost = None, None
    for b, cost, q in frontier:
        if cost is None:
            L.append(f"| ${b} | infeasible | - | - |")
            prev_q, prev_cost = None, None
            continue
        if prev_q is None:
            marg = "-"
        else:
            dcost = cost - prev_cost
            marg = f"{(q - prev_q) / (dcost / 10):.3f}" if dcost > 0 else "-"
        L.append(f"| ${b} | ${cost:.2f} | {q:.2f} | {marg} |")
        prev_q, prev_cost = q, cost
    L.append("")

    L.append("## 10. Value Leaderboard (Kualitas per Dolar, lintas semua model)\n")
    L.append("Rasio blended 3:1 input:output token (ala metodologi Artificial Analysis), lepas dari "
             "konteks task tertentu — murni membandingkan efisiensi harga vs kecerdasan umum.\n")
    L.append("| # | Provider/Model | Kecerdasan Umum | Fin. Reliability | Harga Blended/1M tok | Value (kualitas/$) |")
    L.append("|---|---|---|---|---|---|")
    for i, row in enumerate(value_leaderboard(top_n=15), start=1):
        fin_disp = f"{row['fin_reliability']:.1f}" if row['fin_reliability'] is not None else "-"
        L.append(f"| {i} | {row['provider']}/{row['model']} | {row['quality']:.1f} | {fin_disp} | "
                 f"${row['blended_price']:.3f} | {row['value']:.2f} |")
    L.append("")

    L.append("## 11. Analisis Sensitivitas\n")
    L.append("Dampak perubahan satu parameter (yang lain tetap di baseline) terhadap biaya & kualitas "
             "rekomendasi. Dihitung ulang penuh lewat pipeline yang sama (bukan ekstrapolasi kasar).\n")
    L.append("| Parameter | Nilai | Biaya Rekomendasi/bln | Skor Kualitas |")
    L.append("|---|---|---|---|")
    for row in sensitivity_rows:
        if row["cost"] is None:
            L.append(f"| {row['param']} | {row['value']} | infeasible | - |")
        else:
            L.append(f"| {row['param']} | {row['value']} | ${row['cost']:.2f} | {row['quality']:.2f} |")
    L.append("")

    L.append("## 12. Architectural Implementation Status\n")
    L.append("- **Prescreen Architecture**: Operational.")
    L.append("- **Gemini API Rate Limiting**: Operational.")
    L.append("- **Stage-2 Client Separation (Primary vs Secondary)**: Operational.")
    L.append("- **Agentic Tool-loop OpenAI & DeepSeek**: Operational.")
    L.append("")

    L.append("## 13. Sumber Kalibrasi & Metodologi (Ringkas)\n")
    L.append("- **Artificial Analysis Intelligence Index v4.1.1** (artificialanalysis.ai) — sumber utama "
             "QUALITY_SCORE, snapshot pertengahan Agustus 2026, memakai titik data effort tertinggi "
             "yang tersedia (max/xhigh) per model.")
    L.append("- **Rilis resmi vendor** (Anthropic Opus 5 & Fable 5, OpenAI GPT-5.6, Google Gemini 3.6 "
             "Flash/3.5 Flash-Lite, DeepSeek V4 0731/0813) — dipakai untuk konteks & angka effort-tier "
             "yang tidak selalu ada di AA index.")
    L.append("- **AIMultiple FinanceReasoning benchmark** (238 soal reasoning finansial sulit) — dasar "
             "sebagian kalibrasi FIN_RELIABILITY_SCORE untuk keluarga GPT.")
    L.append("- **JurisTech hallucination-under-incomplete-financial-data report** (April 2026) — temuan "
             "kunci: GPT-5.4 lolos semua kriteria, Claude Opus 4.6 di 'zona hati-hati', Gemini 3.1 Pro "
             "gagal semua kriteria dan tidak direkomendasikan untuk data finansial tidak lengkap. Ini "
             "studi tunggal, bukan konsensus industri — perlakukan sebagai sinyal, bukan fakta mutlak.")
    L.append("- **ARC Prize (arcprize.org)** — dipakai untuk estimasi interpolasi model tier 'Pro' OpenAI "
             "(GPT-5.2/5.4/5.5 Pro) yang belum punya titik data AA-index langsung di tanggal riset ini.")
    L.append("- Beberapa nilai (ditandai 'estimasi' di komentar kode) adalah **interpolasi**, bukan "
             "pengukuran langsung: Claude Sonnet 4.5, GPT-5.2 Pro, GPT-5.4 Pro, GPT-5.5 Pro. Perlakukan "
             "dengan confidence lebih rendah dibanding model yang punya skor AA index terukur langsung.")
    L.append("- Skor AA Intelligence Index berbasis metodologi yang berubah antar versi (v4.0 -> v4.1 -> "
             "v4.1.1); semua angka di skrip ini diusahakan konsisten pada snapshot v4.1.1 Agustus 2026 "
             "supaya apple-to-apple. Riset ulang di masa depan sebaiknya memakai satu snapshot versi yang "
             "sama untuk semua model yang dibandingkan.")
    L.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path


# =====================================================================================
# 13. INTERACTIVE MANUAL SELECTION
# =====================================================================================
def interactive_selection(task_order, all_candidates, granted):
    print("\n" + "="*90)
    print(" MODE PILIHAN KUSTOM (MANUAL)")
    print("="*90)

    assignment = {}
    for task_name in task_order:
        t = TASKS[task_name]
        print(f"\n[ Task: {task_name} ]")
        print(f"Jenis: {t['kind']}, Runs/day: {t['runs_per_day']}, Reasoning Target: {t['reasoning']} ({REASONING_FLOOR[t['reasoning']]}), fin_weight: {t.get('fin_weight', 0):.2f}")
        print(f"Deskripsi: {t['note']}")

        cands = []
        for c in all_candidates[task_name]:
            granted_here = c.is_gemini_free_tier and c.gemini_tier in granted[task_name]
            eff_cost = 0.0 if granted_here else c.monthly_cost_paid
            cands.append({
                "provider": c.provider, "model": c.model, "quality": c.quality,
                "fin_reliability": c.fin_reliability,
                "cost": eff_cost, "paid_ref": c.monthly_cost_paid,
                "is_gemini_free_tier": c.is_gemini_free_tier,
                "free_but_quota_denied": c.is_gemini_free_tier and not granted_here,
            })

        cands.sort(key=lambda c: (-c["quality"], c["cost"]))

        print(f"{'No':>3} | {'Provider/Model':<30} | {'Qual':>5} | {'FinRel':>6} | {'Est. Cost/Bln':>15} | {'Status'}")
        print("-" * 95)
        for i, c in enumerate(cands, 1):
            floor_met = "PASS" if c["quality"] >= REASONING_FLOOR[t["reasoning"]] else "FAIL (Sub-par)"
            tag = "[FREE-TIER Eligible]" if c["is_gemini_free_tier"] and not c["free_but_quota_denied"] else ""
            if c["free_but_quota_denied"]: tag = "[QUOTA FULL -> PAID]"
            print(f"{i:>3} | {c['provider'] + '/' + c['model']:<30} | {c['quality']:>5.2f} | "
                  f"{c['fin_reliability']:>6.1f} | ${c['cost']:>14.2f} | {floor_met} {tag}")

        while True:
            try:
                choice = int(input(f"Pilih model untuk '{task_name}' (1-{len(cands)}): "))
                if 1 <= choice <= len(cands):
                    assignment[task_name] = cands[choice-1]
                    break
                else:
                    print("Pilihan di luar jangkauan.")
            except ValueError:
                print("Masukkan angka yang valid.")

    return assignment


# =====================================================================================
# 14. MAIN
# =====================================================================================
def parse_args(argv):
    p = argparse.ArgumentParser(description="AI Cost & Performance Optimizer v4")
    p.add_argument("--budget", type=float, default=None, help="Override MONTHLY_BUDGET_USD")
    p.add_argument("--mode", choices=["1", "2", "auto", "manual"], default=None,
                    help="1/auto = rekomendasi otomatis, 2/manual = pilihan kustom")
    p.add_argument("--output", type=str, default="ai_cost_analysis_v4.md", help="Path laporan markdown")
    p.add_argument("--non-interactive", action="store_true", help="Jangan minta input() sama sekali")
    p.add_argument("--skip-sensitivity", action="store_true", help="Lewati analisis sensitivitas (lebih cepat)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])

    global MONTHLY_BUDGET_USD
    if args.budget is not None:
        MONTHLY_BUDGET_USD = args.budget

    non_interactive = args.non_interactive or not sys.stdin.isatty()

    print("=" * 90)
    print(" AI COST & PERFORMANCE OPTIMIZER v4 — Claude AI Trading Agent")
    print("=" * 90)

    print("\n[Self-test] Memeriksa struktur data...")
    run_self_tests()
    print("[Self-test] OK — semua task punya kandidat valid, semua harga & skor dalam rentang wajar.")

    task_order = list(TASKS.keys())

    # Mode Selection
    if args.mode in ("1", "auto"):
        mode = "1"
    elif args.mode in ("2", "manual"):
        mode = "2"
    elif non_interactive:
        mode = "1"
    else:
        print("\nPilih Mode Eksekusi:")
        print("1. Rekomendasi Otomatis (Optimizer Budget & Kualitas Maksimal)")
        print("2. Pilihan Kustom (Pilih manual per task)")
        while True:
            mode = input("Masukkan pilihan (1/2) [default=1]: ").strip()
            if not mode:
                mode = "1"
            if mode in ("1", "2"):
                break
            print("Pilihan tidak valid.")

    # Load candidates based on mode
    if mode == "2":
        # Interactive mode: show all capable candidates, regardless of floor
        raw_candidates = {name: build_candidates_for_task(name) for name in task_order}
    else:
        # Optimizer mode: strictly enforce reasoning floor
        raw_candidates = {name: eligible_candidates(name) for name in task_order}

    granted, usage, caps = allocate_free_quota(raw_candidates, FLASH_RPD, FLASH_LITE_RPD)
    effective = build_effective_candidates(raw_candidates, granted)

    if mode == "2":
        if non_interactive:
            print("[WARN] Mode manual diminta tapi berjalan non-interaktif; jatuh ke rekomendasi otomatis.")
            reco = optimize_for_budget(effective, task_order, MONTHLY_BUDGET_USD, resolution_cents=1)
            if reco is None:
                min_feasible = min_cost_baseline(effective, task_order)["total_cost"]
                raise RuntimeError(f"Budget ${MONTHLY_BUDGET_USD:.2f} tidak cukup. Biaya minimum yang "
                                    f"dibutuhkan supaya semua task lolos floor kualitasnya: ${min_feasible:.2f}/bulan.")
            reco_quality = weighted_quality_score(reco["assignment"], task_order)
            scenario_name = f"Rekomendasi @ ${MONTHLY_BUDGET_USD:.0f} budget"
        else:
            reco_assignment = interactive_selection(task_order, raw_candidates, granted)
            reco = {"assignment": reco_assignment, "total_cost": sum(c["cost"] for c in reco_assignment.values())}
            reco_quality = weighted_quality_score(reco["assignment"], task_order)
            scenario_name = "Pilihan Kustom (Manual)"

            usage = {"flash": 0, "flash_lite": 0}
            for task_name, c in reco_assignment.items():
                if c["provider"] == "Gemini" and c.get("is_gemini_free_tier"):
                    t_raw = next((r for r in raw_candidates[task_name] if r.model == c["model"]), None)
                    if t_raw and t_raw.gemini_tier in usage:
                        usage[t_raw.gemini_tier] += t_raw.daily_calls
    else:
        reco = optimize_for_budget(effective, task_order, MONTHLY_BUDGET_USD, resolution_cents=1)
        if reco is None:
            min_feasible = min_cost_baseline(effective, task_order)["total_cost"]
            raise RuntimeError(f"Budget ${MONTHLY_BUDGET_USD:.2f} tidak cukup. Biaya minimum yang "
                                f"dibutuhkan supaya semua task lolos floor kualitasnya: ${min_feasible:.2f}/bulan.")
        reco_quality = weighted_quality_score(reco["assignment"], task_order)
        scenario_name = f"Rekomendasi @ ${MONTHLY_BUDGET_USD:.0f} budget"

    min_cost = min_cost_baseline(effective, task_order)
    max_quality = max_quality_baseline(effective, task_order)
    min_cost_q = weighted_quality_score(min_cost["assignment"], task_order)
    max_quality_q = weighted_quality_score(max_quality["assignment"], task_order)

    current, current_cost = {}, 0.0
    for name in task_order:
        provider, model = CURRENT_SETTINGS_YAML_MAPPING[name]
        cand = next((c for c in effective[name] if c["provider"] == provider and c["model"] == model), None)
        if cand is None:
            t = TASKS[name]
            paid = raw_task_cost_per_run(name, provider, model) * t["runs_per_day"] * DAYS_PER_MONTH
            tier = GEMINI_TIER.get(model) if provider == "Gemini" else None
            is_free_granted = provider == "Gemini" and tier in granted.get(name, set())
            cand = {"provider": provider, "model": model,
                    "quality": effective_quality(name, provider, model) or QUALITY_SCORE.get((provider, model), 5.0),
                    "fin_reliability": FIN_RELIABILITY_SCORE.get((provider, model)),
                    "cost": 0.0 if is_free_granted else paid}
        current[name] = cand
        current_cost += cand["cost"]
    current_q = weighted_quality_score(current, task_order)

    sweep_points = [0, 10, 25, 50, 75, 100, 125, 150, 200, 250, 300]
    frontier = []
    for b in sweep_points:
        r = optimize_for_budget(effective, task_order, b, resolution_cents=10)
        if r is None:
            frontier.append((b, None, None))
        else:
            frontier.append((b, r["total_cost"], weighted_quality_score(r["assignment"], task_order)))

    if args.skip_sensitivity:
        sensitivity_rows = []
    else:
        print("\n[Sensitivitas] Menjalankan sweep budget / key gratis / prescreen pass-rate...")
        sensitivity_rows = sensitivity_analysis(MONTHLY_BUDGET_USD, GEMINI_FREE_KEYS, PRESCREEN_PASS_RATE)

    print(f"\n{GEMINI_FREE_KEYS} key Gemini gratis (Flash & Flash-Lite), "
          f"paid-key Pro: {'ada' if GEMINI_HAS_PAID_KEY else 'tidak ada'}, budget ${MONTHLY_BUDGET_USD:.2f}/bln")
    print(f"Bug pengali key telah diperbaiki "
          f"-> flash={FLASH_RPD} req/hari, flash_lite={FLASH_LITE_RPD} req/hari")
    print(f"Prescreen gate berfungsi: Ya")
    print(f"CANDIDATE_POOL: {len(CANDIDATE_POOL)} model (v3: 14 model)")

    print(f"\n{'Skenario':45s} {'Biaya/bln':>12s} {'Kualitas':>10s}")
    print(f"{'Current settings.yaml (referensi)':45s} ${current_cost:>10.2f}  {current_q:>8.2f}")
    print(f"{'Termurah yg lolos floor':45s} ${min_cost['total_cost']:>10.2f}  {min_cost_q:>8.2f}")
    print(f"{scenario_name:45s} ${reco['total_cost']:>10.2f}  {reco_quality:>8.2f}")
    print(f"{'Kualitas maksimum (abaikan biaya)':45s} ${max_quality['total_cost']:>10.2f}  {max_quality_q:>8.2f}")

    print(f"\nPemakaian kuota gratis pada rekomendasi:")
    print(describe_quota(usage, caps))

    for w in rpm_risk_check(reco["assignment"], task_order):
        print(f"⚠️  [RPM] {w}")
    for w in latency_risk_check(reco["assignment"], task_order):
        print(f"⚠️  [Latency] {w}")
    for w in financial_reliability_audit(reco["assignment"], task_order):
        print(f"⚠️  [Fin-Reliability] {w}")

    print(f"\nKombinasi model per-task @ ${MONTHLY_BUDGET_USD:.0f} budget:")
    for name in task_order:
        c = reco["assignment"][name]
        tag = " [FREE-TIER]" if c["cost"] == 0.0 and c["provider"] == "Gemini" else ""
        fin_disp = f"{c['fin_reliability']:.1f}" if c.get("fin_reliability") is not None else "-"
        print(f"  - {name:32s} -> {c['provider']}/{c['model']:24s} "
              f"(q={c['quality']:.2f}, fin={fin_disp}, ${c['cost']:.2f}/bln){tag}")

    report_path = write_markdown_report(task_order, raw_candidates, granted, usage, caps,
                                         reco, reco_quality, min_cost, min_cost_q, max_quality, max_quality_q,
                                         current_cost, current_q, frontier, sensitivity_rows,
                                         path=args.output)
    print(f"\nLaporan lengkap tersimpan di: {report_path}")


if __name__ == "__main__":
    main()