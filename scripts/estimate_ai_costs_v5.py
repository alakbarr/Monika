"""
======================================================================================
  AI COST & PERFORMANCE OPTIMIZER v5 — Claude AI Trading Agent
  Perbedaan dari v4:

    1. PROVIDER BARU: Groq (5 model free tier: groq-compound, groq-compound-mini,
       groq-gpt-oss-120b, groq-gpt-oss-20b, groq-qwen3-27b) — diintegrasikan ke
       seluruh pipeline: quota allocator, kandidat builder, optimizer, dan laporan.
       Harga Groq = $0 (free tier), dibatasi quota RPD/TPM/TPD per model per key.

    2. KEY ASSUMPTIONS DIPERBARUI:
       - Gemini free tier: 22 key (bukan 20 di v4) -> Flash=440 RPD, Flash-Lite=11000 RPD
       - Groq free tier: 7 key (compound 1750 RPD/model, gpt-oss-*/qwen 7000 RPD/model)
       - 1 key Gemini Paid untuk model Pro tetap ada

    3. TASK INVENTORY: 32 task (dari 19 di v4), diselaraskan settings.yaml Aug 2026.
       Task baru: stage1_shadow_check, stage2_session_trigger, stage2_adjudicator,
       news_classification_escalation, news_classification_verifier,
       news_digest_macro_overview, news_digest_verifier, fundamental_verifier,
       chat_telegram_medium, portfolio_manager_per_trade.
       Deterministik (runs=0): risk_gate_*, portfolio_manager_per_trade, adversarial_check.

    4. CURRENT_SETTINGS_YAML_MAPPING diperbarui ke settings.yaml aktual Agustus 2026,
       termasuk Groq sebagai primary untuk specialist_technical, specialist_macro,
       news_classification_escalation, news_classification_verifier, chat_telegram_medium.

    5. FITUR BARU: Budget Range Analysis — min viable / optimal knee / premium / max quality.

    6. SENSITIVITY ANALYSIS diperluas: tambah variasi GROQ_FREE_KEYS.

  TIDAK DIUBAH: PROVIDERS harga & nama model non-Groq, QUALITY_SCORE model non-Groq,
  FIN_RELIABILITY_MULTIPLIER non-Groq, LATENCY_TTFT_SEC, alur DP Knapsack.
======================================================================================
"""

from dataclasses import dataclass
from typing import Optional, List, Dict
import argparse
import copy
import sys

# ==================================================================================
# 0. ASUMSI GLOBAL
# ==================================================================================
MONTHLY_BUDGET_USD = 100.0
DAYS_PER_MONTH = 30

# Gemini Free Tier
GEMINI_FREE_KEYS    = 22
GEMINI_HAS_PAID_KEY = True

FLASH_RPD_PER_KEY      = 20
FLASH_RPM_PER_KEY      = 5
FLASH_LITE_RPD_PER_KEY = 500
FLASH_LITE_RPM_PER_KEY = 15

FLASH_RPD      = FLASH_RPD_PER_KEY      * GEMINI_FREE_KEYS   # 440
FLASH_RPM      = FLASH_RPM_PER_KEY      * GEMINI_FREE_KEYS   # 110
FLASH_LITE_RPD = FLASH_LITE_RPD_PER_KEY * GEMINI_FREE_KEYS   # 11000
FLASH_LITE_RPM = FLASH_LITE_RPM_PER_KEY * GEMINI_FREE_KEYS   # 330

GEMINI_TPM_PER_KEY = 250_000
GEMINI_TPM_EFFECTIVE = GEMINI_TPM_PER_KEY * GEMINI_FREE_KEYS

# Groq Free Tier
GROQ_FREE_KEYS = 7
GROQ_QUOTA_PER_KEY = {
    "groq-compound":      {"rpd": 250,  "tpm": 70000},
    "groq-compound-mini": {"rpd": 250,  "tpm": 70000},
    "groq-gpt-oss-120b":  {"rpd": 1000, "tpm": 8000, "tpd": 200000},
    "groq-gpt-oss-20b":   {"rpd": 1000, "tpm": 8000, "tpd": 200000},
    "groq-qwen3-27b":     {"rpd": 1000, "tpm": 8000, "tpd": 200000},
}
GROQ_QUOTA_EFFECTIVE = {
    model: {k: v * GROQ_FREE_KEYS for k, v in q.items()}
    for model, q in GROQ_QUOTA_PER_KEY.items()
}

PRESCREEN_PASS_RATE            = 0.45
CACHE_WRITE_MULTIPLIER         = 1.25
LATENCY_WARNING_THRESHOLD_SEC  = 15.0
FIN_RELIABILITY_WARNING_WEIGHT = 0.30
FIN_RELIABILITY_MODEL_FLOOR    = 5.5

# ==================================================================================
# 1. HARGA MODEL (USD / 1M token)
# ==================================================================================
PROVIDERS = {
    "Gemini": {
        "gemini-3.1-flash-lite":    (0.25, 0.025,  1.50),
        "gemini-3.5-flash-lite":    (0.30, 0.030,  2.50),
        "gemini-3.0-flash-preview": (0.50, 0.050,  3.00),
        "gemini-3.5-flash":         (1.50, 0.150,  9.00),
        "gemini-3.6-flash":         (1.50, 0.150,  7.50),
        "gemini-2.5-pro":           (1.25, 0.125, 10.00),
        "gemini-3.1-pro":           (2.00, 0.200, 12.00),
    },
    "Claude": {
        "haiku-4.5":  (1.00, 0.10,  5.00),
        "sonnet-4.5": (3.00, 0.30, 15.00),
        "sonnet-4.6": (3.00, 0.30, 15.00),
        "sonnet-5":   (2.00, 0.20, 10.00),
        "opus-4.5":   (5.00, 0.50, 25.00),
        "opus-4.6":   (5.00, 0.50, 25.00),
        "opus-4.7":   (5.00, 0.50, 25.00),
        "opus-4.8":   (5.00, 0.50, 25.00),
        "opus-5":     (5.00, 0.50, 25.00),
        "fable-5":   (10.00, 1.00, 50.00),
    },
    "OpenAI": {
        "gpt-5.1":       (1.25, 0.125, 10.00),
        "gpt-5.2-pro":  (21.00, 2.100,168.00),
        "gpt-5.4-nano":  (0.20, 0.020,  1.25),
        "gpt-5.4-mini":  (0.75, 0.075,  4.50),
        "gpt-5.4":       (2.50, 0.250, 15.00),
        "gpt-5.4-pro":  (30.00, 3.000,180.00),
        "gpt-5.5":       (5.00, 0.500, 30.00),
        "gpt-5.5-pro":  (30.00, 3.000,180.00),
        "gpt-5.6-luna":  (0.20, 0.020,  1.20),
        "gpt-5.6-terra": (2.00, 0.200, 12.00),
        "gpt-5.6-sol":   (5.00, 0.500, 30.00),
    },
    "DeepSeek": {
        "deepseek-v4-flash": (0.22, 0.007, 0.66),
        "deepseek-v4-pro":   (0.66, 0.022, 1.98),
    },
    "Groq": {
        "groq-compound":      (0.0, 0.0, 0.0),
        "groq-compound-mini": (0.0, 0.0, 0.0),
        "groq-gpt-oss-120b":  (0.0, 0.0, 0.0),
        "groq-gpt-oss-20b":   (0.0, 0.0, 0.0),
        "groq-qwen3-27b":     (0.0, 0.0, 0.0),
    },
}

QUALITY_SCORE = {
    ("Claude", "haiku-4.5"):   4.9,
    ("Claude", "sonnet-4.5"):  6.8,
    ("Claude", "sonnet-4.6"):  7.6,
    ("Claude", "sonnet-5"):    8.9,
    ("Claude", "opus-4.5"):    6.7,
    ("Claude", "opus-4.6"):    7.1,
    ("Claude", "opus-4.7"):    8.8,
    ("Claude", "opus-4.8"):    9.1,
    ("Claude", "opus-5"):      9.9,
    ("Claude", "fable-5"):     9.7,
    ("Gemini", "gemini-3.1-flash-lite"):    4.1,
    ("Gemini", "gemini-3.5-flash-lite"):    6.0,
    ("Gemini", "gemini-3.0-flash-preview"): 6.2,
    ("Gemini", "gemini-3.5-flash"):         8.1,
    ("Gemini", "gemini-3.6-flash"):         8.1,
    ("Gemini", "gemini-2.5-pro"):           4.2,
    ("Gemini", "gemini-3.1-pro"):           7.8,
    ("OpenAI", "gpt-5.1"):       6.3,
    ("OpenAI", "gpt-5.2-pro"):   7.5,
    ("OpenAI", "gpt-5.4-nano"):  6.2,
    ("OpenAI", "gpt-5.4-mini"):  6.5,
    ("OpenAI", "gpt-5.4"):       8.4,
    ("OpenAI", "gpt-5.4-pro"):   9.4,
    ("OpenAI", "gpt-5.5"):       8.9,
    ("OpenAI", "gpt-5.5-pro"):   9.6,
    ("OpenAI", "gpt-5.6-luna"):  8.3,
    ("OpenAI", "gpt-5.6-terra"): 8.9,
    ("OpenAI", "gpt-5.6-sol"):   9.6,
    ("DeepSeek", "deepseek-v4-flash"): 8.1,
    ("DeepSeek", "deepseek-v4-pro"):   8.6,
    ("Groq", "groq-compound"):      7.0,
    ("Groq", "groq-compound-mini"): 5.3,
    ("Groq", "groq-gpt-oss-120b"):  6.5,
    ("Groq", "groq-gpt-oss-20b"):   4.8,
    ("Groq", "groq-qwen3-27b"):     5.7,
}

FIN_RELIABILITY_MULTIPLIER = {
    "OpenAI":   1.03,
    "Claude":   0.95,
    "DeepSeek": 0.90,
    "Groq":     0.87,
    "Gemini":   0.78,
}

def _compute_fin_reliability(provider: str, model: str):
    base = QUALITY_SCORE.get((provider, model))
    if base is None: return None
    return round(min(10.0, base * FIN_RELIABILITY_MULTIPLIER.get(provider, 0.85)), 2)

FIN_RELIABILITY_SCORE = {k: _compute_fin_reliability(*k) for k in QUALITY_SCORE}

LATENCY_TTFT_SEC = {
    ("Claude", "opus-4.8"):              23.65,
    ("Claude", "haiku-4.5"):              0.92,
    ("OpenAI", "gpt-5.5"):               33.87,
    ("Gemini", "gemini-3.6-flash"):      17.71,
    ("Gemini", "gemini-3.5-flash-lite"):  9.11,
    ("DeepSeek", "deepseek-v4-pro"):      1.69,
}

PROVIDER_AGENTIC_CAPABLE = {
    "Claude": True, "Gemini": True, "OpenAI": True, "DeepSeek": True, "Groq": True,
}
PROVIDER_CACHING_SUPPORTED = {
    "Claude": True, "Gemini": False, "OpenAI": False, "DeepSeek": False, "Groq": False,
}
GEMINI_TIER = {
    "gemini-3.1-flash-lite": "flash_lite", "gemini-3.5-flash-lite": "flash_lite",
    "gemini-3.0-flash-preview": "flash", "gemini-3.5-flash": "flash",
    "gemini-3.6-flash": "flash", "gemini-2.5-pro": "pro", "gemini-3.1-pro": "pro",
}
GROQ_MODELS = set(PROVIDERS["Groq"].keys())

CANDIDATE_POOL = [
    ("Claude", "opus-5"),    ("Claude", "fable-5"),    ("Claude", "opus-4.8"),
    ("Claude", "sonnet-5"),  ("Claude", "sonnet-4.6"), ("Claude", "haiku-4.5"),
    ("Gemini", "gemini-3.1-pro"),       ("Gemini", "gemini-3.6-flash"),
    ("Gemini", "gemini-3.5-flash"),     ("Gemini", "gemini-3.0-flash-preview"),
    ("Gemini", "gemini-3.5-flash-lite"),("Gemini", "gemini-3.1-flash-lite"),
    ("OpenAI", "gpt-5.6-sol"),   ("OpenAI", "gpt-5.6-terra"), ("OpenAI", "gpt-5.6-luna"),
    ("OpenAI", "gpt-5.5-pro"),   ("OpenAI", "gpt-5.5"),
    ("OpenAI", "gpt-5.4-pro"),   ("OpenAI", "gpt-5.4"),
    ("OpenAI", "gpt-5.4-mini"),  ("OpenAI", "gpt-5.4-nano"),
    ("DeepSeek", "deepseek-v4-pro"), ("DeepSeek", "deepseek-v4-flash"),
    ("Groq", "groq-compound"),      ("Groq", "groq-compound-mini"),
    ("Groq", "groq-gpt-oss-120b"),  ("Groq", "groq-gpt-oss-20b"),
    ("Groq", "groq-qwen3-27b"),
]

REASONING_FLOOR  = {"High": 8.0, "Medium-High": 7.0, "Medium": 6.0, "Low-Medium": 4.5, "Low": 4.0}
REASONING_WEIGHT = {"High": 3.0, "Medium-High": 2.5, "Medium": 2.0, "Low-Medium": 1.5, "Low": 1.0}

STAGE2_MAIN_CYCLE_ATTEMPTS = 4 * 7
STAGE2_MAIN_SURVIVAL_RATE  = 0.85
STAGE2_REACTIVE_ATTEMPTS   = 10
_main_attempts     = STAGE2_MAIN_CYCLE_ATTEMPTS * STAGE2_MAIN_SURVIVAL_RATE
_reactive_attempts = STAGE2_REACTIVE_ATTEMPTS   * STAGE2_MAIN_SURVIVAL_RATE
STAGE2_PRIMARY_RUNS   = round(_main_attempts     * PRESCREEN_PASS_RATE)
STAGE2_SECONDARY_RUNS = round(_reactive_attempts * PRESCREEN_PASS_RATE)
STAGE2_PRESCREEN_RUNS = round(_main_attempts + _reactive_attempts)
STAGE2_SESSION_TRIGGER_RUNS = 2
STAGE2_ALL_RUNS = STAGE2_PRIMARY_RUNS + STAGE2_SECONDARY_RUNS + STAGE2_SESSION_TRIGGER_RUNS

TASKS = {
    "stage1_shadow_check": dict(kind="single", runs_per_day=4, reasoning="Low", situational=False, in_tokens=1200, out_tokens=150, fin_weight=0.15, latency_sensitive=False, note="Pra-cek sebelum Stage 1"),
    "stage1_fundamental": dict(kind="agentic", runs_per_day=4, reasoning="High", situational=False, turns=9, system_tokens=7000, tools_tokens=5000, initial_user_tokens=900, per_turn_output_tokens=220, per_turn_tool_result_tokens=600, final_answer_tokens=900, fin_weight=0.35, latency_sensitive=False, note="Fundamental Brief"),
    "stage1_escalation": dict(kind="agentic", runs_per_day=1, reasoning="High", situational=True, turns=10, system_tokens=7000, tools_tokens=5000, initial_user_tokens=1100, per_turn_output_tokens=220, per_turn_tool_result_tokens=600, final_answer_tokens=900, fin_weight=0.35, latency_sensitive=False, note="Resolusi ambiguitas makro", constraint="Sebaiknya menggunakan model yang lebih KUAT/TINGGI dari stage1_fundamental"),
    "stage2_per_asset_primary": dict(kind="agentic", runs_per_day=STAGE2_PRIMARY_RUNS, reasoning="High", situational=False, turns=3, system_tokens=11000, tools_tokens=7500, initial_user_tokens=7200, per_turn_output_tokens=250, per_turn_tool_result_tokens=500, final_answer_tokens=1000, fin_weight=0.45, latency_sensitive=False, note="Analisis terjadwal per aset"),
    "stage2_per_asset_secondary": dict(kind="agentic", runs_per_day=STAGE2_SECONDARY_RUNS, reasoning="Medium-High", situational=False, turns=2, system_tokens=11000, tools_tokens=7500, initial_user_tokens=6800, per_turn_output_tokens=250, per_turn_tool_result_tokens=500, final_answer_tokens=900, fin_weight=0.40, latency_sensitive=True, note="Second-opinion reaktif per aset", constraint="WAJIB BERBEDA model/provider dari stage2_per_asset_primary (Second Opinion)"),
    "stage2_session_trigger": dict(kind="agentic", runs_per_day=STAGE2_SESSION_TRIGGER_RUNS, reasoning="Medium-High", situational=True, turns=2, system_tokens=9000, tools_tokens=6000, initial_user_tokens=5000, per_turn_output_tokens=250, per_turn_tool_result_tokens=400, final_answer_tokens=800, fin_weight=0.40, latency_sensitive=True, note="Analisis reaktif pergantian sesi"),
    "stage2_prescreen": dict(kind="single", runs_per_day=STAGE2_PRESCREEN_RUNS, reasoning="Low", situational=False, in_tokens=1500, out_tokens=100, fin_weight=0.05, latency_sensitive=True, note="Gerbang penyaring pra-analisis"),
    "stage2_adjudicator": dict(kind="single", runs_per_day=STAGE2_ALL_RUNS, reasoning="Medium", situational=False, in_tokens=3500, out_tokens=600, fin_weight=0.30, latency_sensitive=False, note="SSVP Adjudicator", constraint="Sebaiknya netral atau BERBEDA dari primary dan secondary"),
    "specialist_technical": dict(kind="single", runs_per_day=STAGE2_ALL_RUNS, reasoning="Medium", situational=False, in_tokens=2200, out_tokens=300, fin_weight=0.15, latency_sensitive=False, note="Konsultan teknikal"),
    "specialist_sentiment": dict(kind="single", runs_per_day=STAGE2_ALL_RUNS, reasoning="Medium", situational=False, in_tokens=2200, out_tokens=300, fin_weight=0.35, latency_sensitive=False, note="Konsultan sentimen"),
    "specialist_macro": dict(kind="single", runs_per_day=STAGE2_ALL_RUNS, reasoning="Medium", situational=False, in_tokens=2200, out_tokens=300, fin_weight=0.40, latency_sensitive=False, note="Konsultan korelasi makro"),
    "debate_bull": dict(kind="single", runs_per_day=4, reasoning="Medium", situational=True, in_tokens=1200, out_tokens=250, fin_weight=0.25, latency_sensitive=True, note="Bull Advocate"),
    "debate_bear": dict(kind="single", runs_per_day=4, reasoning="Medium", situational=True, in_tokens=900, out_tokens=300, fin_weight=0.25, latency_sensitive=True, note="Bear Advocate"),
    "debate_judge": dict(kind="single", runs_per_day=4, reasoning="Medium-High", situational=True, in_tokens=900, out_tokens=180, fin_weight=0.35, latency_sensitive=True, note="Hakim debat", constraint="Harus lebih KUAT dari debate_bull dan debate_bear"),
    "risk_gate_conservative": dict(kind="single", runs_per_day=0, reasoning="Medium", situational=True, in_tokens=650, out_tokens=200, fin_weight=0.30, latency_sensitive=True, note="DETERMINISTIK (runs=0)"),
    "risk_gate_aggressive": dict(kind="single", runs_per_day=0, reasoning="Medium", situational=True, in_tokens=650, out_tokens=200, fin_weight=0.30, latency_sensitive=True, note="DETERMINISTIK (runs=0)"),
    "risk_gate_neutral": dict(kind="single", runs_per_day=0, reasoning="Medium", situational=True, in_tokens=650, out_tokens=200, fin_weight=0.30, latency_sensitive=True, note="DETERMINISTIK (runs=0)"),
    "portfolio_synthesis": dict(kind="single", runs_per_day=3, reasoning="Medium-High", situational=True, in_tokens=1100, out_tokens=200, fin_weight=0.35, latency_sensitive=True, note="Manajer Portofolio"),
    "portfolio_manager_per_trade": dict(kind="single", runs_per_day=0, reasoning="Low", situational=True, in_tokens=500, out_tokens=150, fin_weight=0.20, latency_sensitive=False, note="DETERMINISTIK (runs=0)"),
    "news_classification": dict(kind="single", runs_per_day=12, reasoning="Low", situational=False, in_tokens=800, out_tokens=500, fin_weight=0.10, latency_sensitive=False, note="Klasifikasi berita"),
    "news_classification_escalation": dict(kind="single", runs_per_day=4, reasoning="Low-Medium", situational=False, in_tokens=1000, out_tokens=500, fin_weight=0.20, latency_sensitive=False, note="Re-verifikasi berita", constraint="Sebaiknya menggunakan model yang lebih KUAT dari news_classification"),
    "news_classification_verifier": dict(kind="single", runs_per_day=8, reasoning="Low", situational=False, in_tokens=700, out_tokens=350, fin_weight=0.10, latency_sensitive=False, note="Verifikasi batas berita", constraint="WAJIB BERBEDA model/provider dari news_classification"),
    "news_digest": dict(kind="single", runs_per_day=12, reasoning="Low-Medium", situational=False, in_tokens=2500, out_tokens=800, fin_weight=0.20, latency_sensitive=False, note="Intisari berita per mata uang"),
    "news_digest_macro_overview": dict(kind="single", runs_per_day=4, reasoning="Medium", situational=False, in_tokens=4000, out_tokens=1500, fin_weight=0.25, latency_sensitive=False, note="Overview makro harian"),
    "news_digest_verifier": dict(kind="single", runs_per_day=12, reasoning="Low", situational=False, in_tokens=600, out_tokens=200, fin_weight=0.10, latency_sensitive=False, note="Verifikasi output news digest", constraint="WAJIB BERBEDA model/provider dari news_digest"),
    "fundamental_verifier": dict(kind="single", runs_per_day=4, reasoning="Low", situational=False, in_tokens=2500, out_tokens=400, fin_weight=0.25, latency_sensitive=False, note="Verifikasi konsistensi Fundamental Brief", constraint="WAJIB BERBEDA model/provider dari stage1_fundamental"),
    "cot_precompute": dict(kind="single", runs_per_day=7, reasoning="Low", situational=False, in_tokens=1500, out_tokens=400, fin_weight=0.20, latency_sensitive=False, note="Kalkulator sinyal COT mingguan"),
    "chat_telegram": dict(kind="agentic", runs_per_day=7, reasoning="Low", situational=True, turns=2, system_tokens=1300, tools_tokens=4500, initial_user_tokens=2000, per_turn_output_tokens=250, per_turn_tool_result_tokens=350, final_answer_tokens=350, fin_weight=0.05, latency_sensitive=True, note="Agen Telegram tier dasar"),
    "chat_telegram_medium": dict(kind="agentic", runs_per_day=10, reasoning="Medium", situational=True, turns=2, system_tokens=1300, tools_tokens=4500, initial_user_tokens=2000, per_turn_output_tokens=280, per_turn_tool_result_tokens=380, final_answer_tokens=380, fin_weight=0.15, latency_sensitive=True, note="Agen Telegram tier menengah"),
    "chat_telegram_complex": dict(kind="agentic", runs_per_day=13, reasoning="Medium-High", situational=True, turns=3, system_tokens=1300, tools_tokens=4500, initial_user_tokens=2050, per_turn_output_tokens=300, per_turn_tool_result_tokens=400, final_answer_tokens=400, fin_weight=0.25, latency_sensitive=True, note="Agen Telegram tier kompleks", constraint="Harus lebih KUAT dari chat_telegram_medium"),
    "trade_reflection": dict(kind="single", runs_per_day=5, reasoning="Low", situational=False, in_tokens=600, out_tokens=300, fin_weight=0.20, latency_sensitive=False, note="Retrospeksi post-mortem"),
    "adversarial_check": dict(kind="single", runs_per_day=0, reasoning="Low", situational=False, in_tokens=3000, out_tokens=200, fin_weight=0.0, latency_sensitive=False, note="LEGACY (runs=0)"),
}

CURRENT_SETTINGS_YAML_MAPPING = {
    "stage1_shadow_check":            ("Gemini",   "gemini-3.5-flash"),
    "stage1_fundamental":             ("Claude",   "sonnet-5"),
    "stage1_escalation":              ("Claude",   "opus-5"),
    "stage2_per_asset_primary":       ("Claude",   "sonnet-5"),
    "stage2_per_asset_secondary":     ("DeepSeek", "deepseek-v4-pro"),
    "stage2_session_trigger":         ("Claude",   "sonnet-5"),
    "stage2_prescreen":               ("Gemini",   "gemini-3.5-flash-lite"),
    "stage2_adjudicator":             ("Gemini",   "gemini-3.5-flash"),
    "specialist_technical":           ("Groq",     "groq-gpt-oss-120b"),
    "specialist_sentiment":           ("Gemini",   "gemini-3.6-flash"),
    "specialist_macro":               ("Groq",     "groq-gpt-oss-120b"),
    "debate_bull":                    ("DeepSeek", "deepseek-v4-pro"),
    "debate_bear":                    ("OpenAI",   "gpt-5.6-terra"),
    "debate_judge":                   ("Claude",   "sonnet-5"),
    "risk_gate_conservative":         ("Gemini",   "gemini-3.5-flash-lite"),
    "risk_gate_aggressive":           ("Gemini",   "gemini-3.5-flash-lite"),
    "risk_gate_neutral":              ("Gemini",   "gemini-3.5-flash-lite"),
    "portfolio_synthesis":            ("Claude",   "sonnet-5"),
    "portfolio_manager_per_trade":    ("Gemini",   "gemini-3.5-flash"),
    "news_classification":            ("Gemini",   "gemini-3.5-flash-lite"),
    "news_classification_escalation": ("Groq",     "groq-gpt-oss-120b"),
    "news_classification_verifier":   ("Groq",     "groq-gpt-oss-120b"),
    "news_digest":                    ("DeepSeek", "deepseek-v4-pro"),
    "news_digest_macro_overview":     ("Claude",   "sonnet-5"),
    "news_digest_verifier":           ("Gemini",   "gemini-3.5-flash-lite"),
    "fundamental_verifier":           ("Gemini",   "gemini-3.5-flash"),
    "cot_precompute":                 ("Gemini",   "gemini-3.5-flash-lite"),
    "chat_telegram":                  ("Gemini",   "gemini-3.5-flash-lite"),
    "chat_telegram_medium":           ("Groq",     "groq-gpt-oss-120b"),
    "chat_telegram_complex":          ("Claude",   "sonnet-5"),
    "trade_reflection":               ("Claude",   "sonnet-5"),
    "adversarial_check":              ("Claude",   "sonnet-5"),
}

TASK_CONFIDENCE = {
    "stage1_shadow_check": "derived", "stage1_fundamental": "derived", "stage1_escalation": "derived",
    "stage2_per_asset_primary": "derived", "stage2_per_asset_secondary": "derived",
    "stage2_session_trigger": "derived", "stage2_prescreen": "derived",
    "stage2_adjudicator": "derived", "specialist_technical": "derived",
    "specialist_sentiment": "derived", "specialist_macro": "derived",
    "debate_bull": "estimated", "debate_bear": "estimated", "debate_judge": "estimated",
    "portfolio_synthesis": "estimated",
    "news_classification": "estimated",  
    "news_classification_escalation": "estimated", "news_classification_verifier": "estimated",
    "news_digest": "estimated", "news_digest_macro_overview": "derived", "news_digest_verifier": "estimated",
    "fundamental_verifier": "derived", "cot_precompute": "derived",
    "chat_telegram": "estimated", "chat_telegram_medium": "estimated", "chat_telegram_complex": "estimated",
    "trade_reflection": "estimated",
    "risk_gate_conservative": "derived", "risk_gate_aggressive": "derived", "risk_gate_neutral": "derived",
    "portfolio_manager_per_trade": "derived", "adversarial_check": "derived",
    "risk_gate_check": "derived"
}

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
            static_cost = (static_tokens / 1e6) * (
                in_price * CACHE_WRITE_MULTIPLIER if turn == 1 else cached_price
            )
        else:
            static_cost = (static_tokens / 1e6) * in_price
        dynamic_cost = (conv / 1e6) * in_price
        out_tok = t["per_turn_output_tokens"] + (t["final_answer_tokens"] if is_last else 0)
        output_cost = (out_tok / 1e6) * out_price
        total += static_cost + dynamic_cost + output_cost
        conv += t["per_turn_output_tokens"] + (
            t["final_answer_tokens"] if is_last else t["per_turn_tool_result_tokens"]
        )
    return total

def single_shot_cost_usd(provider, model, t):
    in_price, _, out_price = _price(provider, model)
    return (t["in_tokens"] / 1e6) * in_price + (t["out_tokens"] / 1e6) * out_price

def raw_task_cost_per_run(task_name, provider, model, tasks=None):
    tasks = TASKS if tasks is None else tasks
    t = tasks[task_name]
    if t["kind"] == "agentic":
        return agentic_run_cost_usd(provider, model, t)
    return single_shot_cost_usd(provider, model, t)

def estimate_avg_tokens_per_call(task_name, provider, model, tasks=None):
    tasks = TASKS if tasks is None else tasks
    t = tasks[task_name]
    if t["kind"] == "agentic":
        avg_in = (t["system_tokens"] + t["tools_tokens"] + t["initial_user_tokens"]) / max(t["turns"], 1) \
                 + t["per_turn_tool_result_tokens"]
        avg_out = t["per_turn_output_tokens"]
        return avg_in + avg_out
    return t["in_tokens"] + t["out_tokens"]

def check_tpm_feasibility(effective_candidates: dict, task_order: list, tasks=None,
                            gemini_tpm_cap=None, groq_quota_effective=None) -> list[str]:
    tasks = TASKS if tasks is None else tasks
    groq_quota_effective = groq_quota_effective or GROQ_QUOTA_EFFECTIVE
    gemini_tpm_cap = gemini_tpm_cap or GEMINI_TPM_EFFECTIVE
    warnings = []
    ACTIVE_HOURS_PER_DAY = 16
    usage_by_key = {}

    for task_name in task_order:
        cands = effective_candidates.get(task_name, [])
        if not cands:
            continue
        chosen = min(cands, key=lambda c: c["cost"])
        if chosen["cost"] != 0.0:
            continue
        key = (chosen["provider"], chosen["model"])
        t = tasks[task_name]
        calls_per_run = t["turns"] if t["kind"] == "agentic" else 1
        daily_calls = t["runs_per_day"] * calls_per_run
        avg_tokens = estimate_avg_tokens_per_call(task_name, chosen["provider"], chosen["model"], tasks=tasks)
        tokens_per_min = (daily_calls * avg_tokens) / (ACTIVE_HOURS_PER_DAY * 60)
        usage_by_key.setdefault(key, 0.0)
        usage_by_key[key] += tokens_per_min

    for (provider, model), tpm_used in usage_by_key.items():
        if provider == "Gemini":
            cap = gemini_tpm_cap
        elif provider == "Groq":
            cap = groq_quota_effective.get(model, {}).get("tpm", float("inf"))
        else:
            continue
        pct = tpm_used / cap * 100 if cap else 0
        if pct > 60:
            warnings.append(
                f"TPM RISK: {provider}/{model} — estimasi rata-rata {tpm_used:.0f} token/menit "
                f"({pct:.0f}% dari cap {cap:,.0f} TPM gabungan). Ini rata-rata, BURST konkuren "
                f"(mis. beberapa asset dianalisis paralel) bisa jauh melampaui ini sesaat."
            )
    return warnings

def effective_quality(task_name, provider, model, tasks=None):
    tasks = TASKS if tasks is None else tasks
    base = QUALITY_SCORE.get((provider, model))
    if base is None: return None
    fin = FIN_RELIABILITY_SCORE.get((provider, model), base)
    w = tasks[task_name].get("fin_weight", 0.0)
    return round(base * (1 - w) + fin * w, 3)

@dataclass
class Candidate:
    provider: str
    model: str
    quality: float
    general_quality: float
    fin_reliability: float
    cost_per_run: float
    monthly_cost_paid: float
    is_gemini_free_tier: bool
    gemini_tier: Optional[str]
    is_groq_free_tier: bool
    daily_calls: int
    latency_ttft_sec: Optional[float] = None

def build_candidates_for_task(task_name, tasks=None):
    tasks = TASKS if tasks is None else tasks
    t = tasks[task_name]
    calls_per_run = t["turns"] if t["kind"] == "agentic" else 1
    daily_calls = t["runs_per_day"] * calls_per_run
    out = []
    for provider, model in CANDIDATE_POOL:
        if t["kind"] == "agentic" and not PROVIDER_AGENTIC_CAPABLE.get(provider, False): continue
        if provider == "Gemini" and GEMINI_TIER.get(model) == "pro" and not GEMINI_HAS_PAID_KEY: continue
        q = effective_quality(task_name, provider, model, tasks=tasks)
        if q is None: continue
        gen_q = QUALITY_SCORE.get((provider, model))
        fin_q = FIN_RELIABILITY_SCORE.get((provider, model))
        per_run = raw_task_cost_per_run(task_name, provider, model, tasks=tasks)
        monthly_paid = per_run * t["runs_per_day"] * DAYS_PER_MONTH
        gemini_tier = GEMINI_TIER.get(model) if provider == "Gemini" else None
        is_gemini_free = provider == "Gemini" and gemini_tier in ("flash", "flash_lite")
        is_groq_free = provider == "Groq" and model in GROQ_MODELS
        latency = LATENCY_TTFT_SEC.get((provider, model))
        out.append(Candidate(
            provider=provider, model=model, quality=q, general_quality=gen_q,
            fin_reliability=fin_q, cost_per_run=per_run, monthly_cost_paid=monthly_paid,
            is_gemini_free_tier=is_gemini_free, gemini_tier=gemini_tier,
            is_groq_free_tier=is_groq_free, daily_calls=daily_calls,
            latency_ttft_sec=latency,
        ))
    if not out:
        raise RuntimeError(f"Tidak ada kandidat untuk task '{task_name}'.")
    return out

def eligible_candidates(task_name, tasks=None):
    tasks = TASKS if tasks is None else tasks
    t = tasks[task_name]
    if t["runs_per_day"] == 0: return []
    floor = REASONING_FLOOR[t["reasoning"]]
    cands = build_candidates_for_task(task_name, tasks=tasks)
    passed = [c for c in cands if c.quality >= floor]
    if not passed:
        best = max(cands, key=lambda c: c.quality)
        reasoning_val = t['reasoning']
        print(f"[WARN] tidak ada kandidat lolos floor '{reasoning_val}' ({floor}) "
              f"untuk '{task_name}'; pakai terbaik: {best.provider}/{best.model}")
        passed = [best]
    return passed

def allocate_gemini_quota(all_candidates, flash_cap, flash_lite_cap, tasks=None):
    tasks = TASKS if tasks is None else tasks
    requests = []
    for task_name, cands in all_candidates.items():
        paid_only = [c for c in cands if not c.is_gemini_free_tier]
        cheapest_paid = min((c.monthly_cost_paid for c in paid_only), default=None)
        task_weight = REASONING_WEIGHT.get(tasks[task_name]["reasoning"], 1.0)
        for c in cands:
            if c.is_gemini_free_tier:
                fallback = cheapest_paid if cheapest_paid is not None else 10_000.0
                priority = (fallback / max(c.daily_calls, 1)) * task_weight
                requests.append((task_name, c.gemini_tier, c.daily_calls, priority))
    granted = {t: set() for t in all_candidates}
    usage = {"flash": 0, "flash_lite": 0}
    caps = {"flash": flash_cap, "flash_lite": flash_lite_cap}
    for tier in ("flash_lite", "flash"):
        pool = sorted([r for r in requests if r[1] == tier], key=lambda r: -r[3])
        for (task_name, _, calls, _prio) in pool:
            if usage[tier] + calls <= caps[tier]:
                usage[tier] += calls
                granted[task_name].add(tier)
    return granted, usage, caps

def allocate_groq_quota(all_candidates, groq_quota_effective, tasks=None):
    tasks = TASKS if tasks is None else tasks
    granted = {t: set() for t in all_candidates}
    usage_rpd = {model: 0 for model in groq_quota_effective}
    for groq_model in groq_quota_effective:
        max_rpd = groq_quota_effective[groq_model].get("rpd", 0)
        requests = []
        for task_name, cands in all_candidates.items():
            gc = next((c for c in cands if c.provider == "Groq" and c.model == groq_model), None)
            if gc is None: continue
            non_groq = [c for c in cands if not c.is_groq_free_tier]
            cheapest = min((c.monthly_cost_paid for c in non_groq), default=None)
            task_weight = REASONING_WEIGHT.get(tasks[task_name]["reasoning"], 1.0)
            fallback = cheapest if cheapest is not None else 10_000.0
            priority = (fallback / max(gc.daily_calls, 1)) * task_weight
            requests.append((task_name, gc.daily_calls, priority))
        requests.sort(key=lambda r: -r[2])
        for (task_name, daily_calls, _) in requests:
            if usage_rpd[groq_model] + daily_calls <= max_rpd:
                usage_rpd[groq_model] += daily_calls
                granted[task_name].add(groq_model)
    caps = {m: groq_quota_effective[m].get("rpd", 0) for m in groq_quota_effective}
    return granted, usage_rpd, caps

def dominance_filter(cands):
    keep = []
    for i, c in enumerate(cands):
        dominated = any(
            o["cost"] <= c["cost"] and o["quality"] >= c["quality"]
            and (o["cost"] < c["cost"] or o["quality"] > c["quality"])
            for j, o in enumerate(cands) if j != i
        )
        if not dominated: keep.append(c)
    return keep

def build_effective_candidates(all_candidates, gemini_granted, groq_granted):
    effective = {}
    for task_name, cands in all_candidates.items():
        out = []
        for c in cands:
            if c.is_groq_free_tier:
                if c.model not in groq_granted.get(task_name, set()): continue
                eff_cost = 0.0
            elif c.is_gemini_free_tier:
                granted_here = c.gemini_tier in gemini_granted.get(task_name, set())
                eff_cost = 0.0 if granted_here else c.monthly_cost_paid
            else:
                eff_cost = c.monthly_cost_paid
            out.append({
                "provider": c.provider, "model": c.model,
                "quality": c.quality, "general_quality": c.general_quality,
                "fin_reliability": c.fin_reliability, "latency_ttft_sec": c.latency_ttft_sec,
                "cost": eff_cost, "paid_ref": c.monthly_cost_paid,
                "is_free": (c.is_gemini_free_tier or c.is_groq_free_tier) and eff_cost == 0.0,
            })
        if not out:
            for c in cands:
                if not c.is_groq_free_tier:
                    out.append({
                        "provider": c.provider, "model": c.model,
                        "quality": c.quality, "general_quality": c.general_quality,
                        "fin_reliability": c.fin_reliability, "latency_ttft_sec": c.latency_ttft_sec,
                        "cost": c.monthly_cost_paid, "paid_ref": c.monthly_cost_paid,
                        "is_free": False,
                    })
        effective[task_name] = dominance_filter(out) if out else []
    return effective

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
        cands = effective_candidates.get(task_name, [])
        if not cands:
            parents.append([None] * (B + 1))
            continue
        new_dp = [NEG_INF] * (B + 1)
        new_parent = [None] * (B + 1)
        for b, base in enumerate(dp):
            if base == NEG_INF: continue
            for ci, c in enumerate(cands):
                cost_units = int(round(c["cost"] * 100 / resolution_cents))
                nb = b + cost_units
                if nb > B: continue
                val = base + c["quality"] * weight
                if val > new_dp[nb]:
                    new_dp[nb] = val
                    new_parent[nb] = (ci, b)
        dp = new_dp
        parents.append(new_parent)
    best_b = max(range(B + 1), key=lambda b: dp[b])
    if dp[best_b] == NEG_INF: return None
    choice_idx = [0] * len(task_order)
    b = best_b
    for i in range(len(task_order) - 1, -1, -1):
        if parents[i][b] is None: continue
        ci, prev_b = parents[i][b]
        choice_idx[i] = ci
        b = prev_b
    result, total_cost = {}, 0.0
    for i, task_name in enumerate(task_order):
        cands = effective_candidates.get(task_name, [])
        if cands:
            c = cands[choice_idx[i]]
            result[task_name] = c
            total_cost += c["cost"]
    return {"assignment": result, "objective": dp[best_b], "total_cost": total_cost}

def min_cost_baseline(effective_candidates, task_order):
    assignment, total = {}, 0.0
    for task_name in task_order:
        cands = effective_candidates.get(task_name, [])
        if cands:
            best = min(cands, key=lambda c: (c["cost"], -c["quality"]))
            assignment[task_name] = best
            total += best["cost"]
    return {"assignment": assignment, "total_cost": total}

def max_quality_baseline(effective_candidates, task_order):
    assignment, total = {}, 0.0
    for task_name in task_order:
        cands = effective_candidates.get(task_name, [])
        if cands:
            best = max(cands, key=lambda c: c["quality"])
            assignment[task_name] = best
            total += best["cost"]
    return {"assignment": assignment, "total_cost": total}

def weighted_quality_score(assignment, task_order, tasks=None):
    tasks = TASKS if tasks is None else tasks
    num, den = 0.0, 0.0
    for task_name in task_order:
        if task_name not in assignment: continue
        t = tasks[task_name]
        w = t["runs_per_day"] * REASONING_WEIGHT[t["reasoning"]]
        if w == 0: continue
        num += assignment[task_name]["quality"] * w
        den += w
    return num / den if den else 0.0

def rpm_risk_check(assignment, task_order, tasks=None):
    tasks = TASKS if tasks is None else tasks
    max_f, max_fl = 0, 0
    for name in task_order:
        if name not in assignment: continue
        c = assignment[name]
        if c.get("cost", 1) != 0.0 or c.get("provider") != "Gemini": continue
        tier = GEMINI_TIER.get(c["model"])
        turns = tasks[name]["turns"] if tasks[name]["kind"] == "agentic" else 1
        if tier == "flash": max_f = max(max_f, turns)
        elif tier == "flash_lite": max_fl = max(max_fl, turns)
    warnings = []
    if max_f > FLASH_RPM: warnings.append(f"Agentic {max_f}-turn di flash berisiko melebihi RPM cap ({FLASH_RPM}/menit).")
    if max_fl > FLASH_LITE_RPM: warnings.append(f"Agentic {max_fl}-turn di flash_lite berisiko melebihi RPM cap ({FLASH_LITE_RPM}/menit).")
    return warnings

def latency_risk_check(assignment, task_order, tasks=None):
    tasks = TASKS if tasks is None else tasks
    warnings = []
    for name in task_order:
        if name not in assignment: continue
        t = tasks[name]
        if not t.get("latency_sensitive"): continue
        c = assignment[name]
        ttft = c.get("latency_ttft_sec")
        if ttft is not None and ttft > LATENCY_WARNING_THRESHOLD_SEC:
            warnings.append(f"'{name}' (latency-sensitive) -> {c['provider']}/{c['model']} TTFT={ttft:.1f}s > {LATENCY_WARNING_THRESHOLD_SEC:.0f}s.")
    return warnings

def financial_reliability_audit(assignment, task_order, tasks=None):
    tasks = TASKS if tasks is None else tasks
    warnings = []
    for name in task_order:
        if name not in assignment: continue
        t = tasks[name]
        if t.get("fin_weight", 0) < FIN_RELIABILITY_WARNING_WEIGHT: continue
        c = assignment[name]
        fin = c.get("fin_reliability")
        if fin is not None and fin < FIN_RELIABILITY_MODEL_FLOOR:
            fw = t.get('fin_weight', 0)
            warnings.append(f"'{name}' (fin_weight={fw:.2f}) -> {c['provider']}/{c['model']} fin_reliability={fin:.1f} (< floor {FIN_RELIABILITY_MODEL_FLOOR}).")
    return warnings

def value_leaderboard(top_n=15):
    rows_paid, rows_free = [], []
    for provider, model in CANDIDATE_POOL:
        in_price, _, out_price = PROVIDERS[provider][model]
        q = QUALITY_SCORE.get((provider, model))
        fin = FIN_RELIABILITY_SCORE.get((provider, model))
        if q is None: continue
        if provider == "Groq":
            rows_free.append({"provider": provider, "model": model, "quality": q, "fin_reliability": fin, "blended_price": 0.0})
        else:
            blended = 0.75 * in_price + 0.25 * out_price
            if blended > 0:
                rows_paid.append({"provider": provider, "model": model, "quality": q, "fin_reliability": fin, "blended_price": blended, "value": q / blended})
    rows_paid.sort(key=lambda r: -r["value"])
    rows_free.sort(key=lambda r: -r["quality"])
    return rows_paid[:top_n], rows_free

def find_knee_point(valid_frontier, threshold=0.05):
    if len(valid_frontier) < 2: return valid_frontier[-1] if valid_frontier else None
    last_good = valid_frontier[0]
    for i in range(1, len(valid_frontier)):
        _, c_prev, q_prev = valid_frontier[i - 1]
        _, c_curr, q_curr = valid_frontier[i]
        if c_curr > c_prev + 0.01:
            marginal = (q_curr - q_prev) / ((c_curr - c_prev) / 10)
            if marginal < threshold: return last_good
        last_good = valid_frontier[i]
    return valid_frontier[-1]

def budget_range_analysis(frontier):
    valid = [(b, cost, q) for b, cost, q in frontier if cost is not None and cost >= 0]
    if not valid: return None
    min_viable  = valid[0]
    max_quality = valid[-1]
    knee        = find_knee_point(valid, threshold=0.05)
    premium = None
    if knee:
        knee_q = knee[2]
        for b, cost, q in valid:
            if cost > knee[1] + 0.01 and q > knee_q + 0.3:
                premium = (b, cost, q)
                break
    return {"min_viable": min_viable, "optimal": knee, "premium": premium, "max_quality": max_quality}

def build_tasks_with_prescreen_rate(rate):
    main_a = STAGE2_MAIN_CYCLE_ATTEMPTS * STAGE2_MAIN_SURVIVAL_RATE
    react_a = STAGE2_REACTIVE_ATTEMPTS * STAGE2_MAIN_SURVIVAL_RATE
    primary  = round(main_a  * rate)
    secondary = round(react_a * rate)
    prescreen = round(main_a + react_a)
    all_runs = primary + secondary + STAGE2_SESSION_TRIGGER_RUNS

    tasks = copy.deepcopy(TASKS)
    for n in ("stage2_per_asset_primary",):
        tasks[n]["runs_per_day"] = primary
    for n in ("stage2_adjudicator", "specialist_technical", "specialist_sentiment", "specialist_macro"):
        tasks[n]["runs_per_day"] = all_runs
    tasks["stage2_per_asset_secondary"]["runs_per_day"] = secondary
    tasks["stage2_prescreen"]["runs_per_day"] = prescreen
    return tasks

def run_pipeline(tasks, budget_usd, gemini_flash_cap, gemini_flash_lite_cap, groq_free_keys=None, resolution_cents=10):
    groq_keys = GROQ_FREE_KEYS if groq_free_keys is None else groq_free_keys
    groq_quota = {model: {k: v * groq_keys for k, v in GROQ_QUOTA_PER_KEY[model].items()} for model in GROQ_QUOTA_PER_KEY}
    active = {k: v for k, v in tasks.items() if v["runs_per_day"] > 0}
    order = list(active.keys())
    raw = {name: eligible_candidates(name, tasks=active) for name in order}
    gg, _, _  = allocate_gemini_quota(raw, gemini_flash_cap, gemini_flash_lite_cap)
    grq, _, _ = allocate_groq_quota(raw, groq_quota)
    eff = build_effective_candidates(raw, gg, grq)
    result = optimize_for_budget(eff, order, budget_usd, resolution_cents=resolution_cents, tasks=active)
    if result is None: return None
    return result["total_cost"], weighted_quality_score(result["assignment"], order, tasks=active)

def sensitivity_analysis(base_budget, base_gemini_keys, base_groq_keys, base_rate):
    rows = []
    def add_row(param, value, tasks, budget, gkeys, groq_keys):
        fc = FLASH_RPD_PER_KEY * gkeys
        flc = FLASH_LITE_RPD_PER_KEY * gkeys
        r = run_pipeline(tasks, budget, fc, flc, groq_free_keys=groq_keys)
        rows.append({"param": param, "value": value, "cost": r[0] if r else None, "quality": r[1] if r else None})
    base_tasks = build_tasks_with_prescreen_rate(base_rate)
    for b in sorted({max(1, base_budget * 0.5), base_budget, base_budget * 1.5, base_budget * 2.0}):
        add_row("MONTHLY_BUDGET_USD", round(b, 2), base_tasks, b, base_gemini_keys, base_groq_keys)
    for k in sorted({max(1, base_gemini_keys // 2), base_gemini_keys, base_gemini_keys * 2}):
        add_row("GEMINI_FREE_KEYS", k, base_tasks, base_budget, k, base_groq_keys)
    for k in sorted({max(1, base_groq_keys // 2), base_groq_keys, base_groq_keys * 2}):
        add_row("GROQ_FREE_KEYS", k, base_tasks, base_budget, base_gemini_keys, k)
    for r_rate in sorted({max(0.05, base_rate * 0.6), base_rate, min(1.0, base_rate * 1.4)}):
        r_rate = round(r_rate, 3)
        add_row("PRESCREEN_PASS_RATE", r_rate, build_tasks_with_prescreen_rate(r_rate), base_budget, base_gemini_keys, base_groq_keys)
    return rows

def run_self_tests():
    problems = []
    for provider, models in PROVIDERS.items():
        for model, prices in models.items():
            if len(prices) != 3 or any(p < 0 for p in prices): problems.append(f"Harga tidak valid: {provider}/{model}")
    for key, val in QUALITY_SCORE.items():
        if not (0.0 <= val <= 10.0): problems.append(f"QUALITY_SCORE di luar 0-10: {key}")
    for provider, model in CANDIDATE_POOL:
        if provider not in PROVIDERS or model not in PROVIDERS[provider]: problems.append(f"CANDIDATE_POOL tanpa harga: {provider}/{model}")
        if (provider, model) not in QUALITY_SCORE: problems.append(f"CANDIDATE_POOL tanpa QUALITY_SCORE: {provider}/{model}")
    for name, t in TASKS.items():
        if "fin_weight" not in t or "latency_sensitive" not in t: problems.append(f"Task '{name}' kurang field")
        if name not in CURRENT_SETTINGS_YAML_MAPPING: problems.append(f"Task '{name}' tidak di CURRENT_SETTINGS_YAML_MAPPING")
    for name, t in TASKS.items():
        if t["runs_per_day"] > 0:
            try:
                if not eligible_candidates(name): problems.append(f"Task aktif '{name}' tidak punya kandidat")
            except Exception as exc: problems.append(f"Task '{name}' error: {exc}")
    
    for name in CURRENT_SETTINGS_YAML_MAPPING:
        if name not in TASKS:
            problems.append(f"CURRENT_SETTINGS_YAML_MAPPING punya '{name}' yang tidak ada di TASKS")

    for task_a, relation, task_b, severity in TASK_CONSTRAINTS:
        if task_a not in TASKS:
            problems.append(f"TASK_CONSTRAINTS mereferensikan task tak dikenal: '{task_a}'")
        if task_b not in TASKS:
            problems.append(f"TASK_CONSTRAINTS mereferensikan task tak dikenal: '{task_b}'")

    if problems:
        raise AssertionError("Self-test GAGAL:\n" + "\n".join(f"  - {p}" for p in problems))
    return True

def describe_gemini_quota(usage, caps):
    lines = [f"Gemini free tier ({GEMINI_FREE_KEYS} key):"]
    for tier, used in usage.items():
        cap = caps.get(tier, 0)
        pct = 100 * used / cap if cap > 0 else 0
        lines.append(f"  {tier:12s}: {used:5d}/{cap:6d} RPD ({pct:5.1f}%)")
    return "\n".join(lines)

def describe_groq_quota(groq_usage, groq_caps):
    lines = [f"Groq free tier ({GROQ_FREE_KEYS} key, per model):"]
    for model, used in groq_usage.items():
        cap = groq_caps.get(model, 0)
        pct = 100 * used / cap if cap > 0 else 0
        tpd = GROQ_QUOTA_EFFECTIVE.get(model, {}).get("tpd")
        note = f" [TPD max {tpd:,}]" if tpd else ""
        lines.append(f"  {model:22s}: {used:5d}/{cap:6d} RPD ({pct:5.1f}%){note}")
    return "\n".join(lines)

def build_executive_summary(reco, reco_quality, current_cost, current_q, current_violations,
                              reco_violations, tpm_warnings, active_task_order) -> list[str]:
    L = ["## 0. RINGKASAN EKSEKUTIF — Baca Ini Dulu\n"]
    delta_cost = current_cost - reco["total_cost"]
    delta_q = reco_quality - current_q
    L.append(f"| | Setup Saat Ini | Rekomendasi | Selisih |")
    L.append(f"|---|---|---|---|")
    L.append(f"| Biaya/bulan | ${current_cost:.2f} | ${reco['total_cost']:.2f} | "
              f"{'${:.2f} lebih hemat'.format(delta_cost) if delta_cost > 0 else '${:.2f} lebih mahal'.format(-delta_cost)} |")
    L.append(f"| Skor Kualitas | {current_q:.2f}/10 | {reco_quality:.2f}/10 | "
              f"{'+' if delta_q >= 0 else ''}{delta_q:.2f} |")
    L.append("")

    if current_violations:
        L.append(f"### 🔴 {len(current_violations)} Pelanggaran Aturan di settings.yaml SAAT INI\n")
        for v in current_violations:
            L.append(f"- {v}")
        L.append("")
    else:
        L.append("### ✅ Tidak ada pelanggaran constraint di settings.yaml saat ini.\n")

    if reco_violations:
        L.append(f"### ⚠️ {len(reco_violations)} Pelanggaran Terdeteksi pada Rekomendasi (sebelum auto-repair)\n")
        for v in reco_violations:
            L.append(f"- {v}")
        L.append("")

    if tpm_warnings:
        L.append("### ⚠️ Peringatan Kapasitas TPM\n")
        for w in tpm_warnings:
            L.append(f"- {w}")
        L.append("")

    L.append("### Perubahan Model yang Disarankan (hanya yang BEDA dari settings.yaml saat ini)\n")
    L.append("| Task | Saat Ini | Disarankan | Alasan Singkat |")
    L.append("|---|---|---|---|")
    changes_found = False
    for name in active_task_order:
        cur_p, cur_m = CURRENT_SETTINGS_YAML_MAPPING.get(name, ("-", "-"))
        rec = reco["assignment"].get(name)
        if not rec:
            continue
        if (rec["provider"], rec["model"]) != (cur_p, cur_m):
            changes_found = True
            reason = "Constraint fix" if any(name in v for v in reco_violations) else \
                     "Lebih murah pd kualitas setara" if rec["cost"] < 0.01 else "Optimasi budget"
            L.append(f"| {name} | {cur_p}/{cur_m} | {rec['provider']}/{rec['model']} | {reason} |")
    if not changes_found:
        L.append("| _(tidak ada perubahan — settings.yaml sudah optimal pada budget ini)_ | | | |")
    L.append("")
    return L

def write_markdown_report(
    active_task_order, zero_run_tasks,
    raw_candidates, gemini_granted, gemini_usage, gemini_caps,
    groq_granted, groq_usage, groq_caps,
    reco, reco_quality, min_cost_res, min_cost_q, max_quality_res, max_quality_q,
    current_cost, current_q, current_assignment,
    frontier, bra, sensitivity_rows,
    current_violations, reco_violations, tpm_warnings,
    path="ai_cost_analysis_v6.md",
):
    L = []
    L.append("# AI Cost & Performance Analysis v6 — Claude AI Trading Agent\n")
    L.extend(build_executive_summary(reco, reco_quality, current_cost, current_q,
                                     current_violations, reco_violations, tpm_warnings, active_task_order))
    L.append("## 0.5. Ringkasan Perubahan dari v4/v5\n")
    L.append(f"- Provider baru: Groq (5 model free tier)")
    L.append(f"- {GEMINI_FREE_KEYS} key Gemini gratis -> Flash {FLASH_RPD} RPD, Flash-Lite {FLASH_LITE_RPD} RPD")
    L.append(f"- {GROQ_FREE_KEYS} key Groq gratis (compound {250*GROQ_FREE_KEYS} RPD, gpt-oss-*/qwen {1000*GROQ_FREE_KEYS} RPD)")
    L.append(f"- 32 task (naik dari 19), sesuai settings.yaml Agustus 2026")
    L.append("- Budget Range Analysis: min viable / optimal knee / premium / max quality\n")

    L.append("## 1. Parameter Global\n")
    L.append(f"- Budget: ${MONTHLY_BUDGET_USD:.2f}/bulan")
    L.append(f"- Gemini: {GEMINI_FREE_KEYS} key gratis (Flash {FLASH_RPD} RPD/{FLASH_RPM} RPM, "
             f"Flash-Lite {FLASH_LITE_RPD} RPD/{FLASH_LITE_RPM} RPM)")
    L.append(f"- Gemini paid key (Pro): {'Ya' if GEMINI_HAS_PAID_KEY else 'Tidak'}")
    L.append(f"- Groq: {GROQ_FREE_KEYS} key gratis")
    L.append(f"- Prescreen pass rate: {PRESCREEN_PASS_RATE:.0%}")
    L.append(f"- CANDIDATE_POOL: {len(CANDIDATE_POOL)} model\n")

    L.append("## 2. Inventaris Task (32 task)\n")
    L.append("| Task | Jenis | Runs/hari | Calls/hari | Reasoning | fin_weight | LatSens | Status | Confidence |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for name in list(active_task_order) + list(zero_run_tasks):
        t = TASKS[name]
        turns = t["turns"] if t["kind"] == "agentic" else 1
        status = "Aktif" if t["runs_per_day"] > 0 else "Deterministik/Legacy"
        conf = TASK_CONFIDENCE.get(name, "-")
        L.append(f"| {name} | {t['kind']} | {t['runs_per_day']} | {t['runs_per_day']*turns} | "
                 f"{t['reasoning']} | {t.get('fin_weight', 0):.2f} | "
                 f"{'Ya' if t.get('latency_sensitive') else 'Tidak'} | {status} | {conf} |")
    L.append("\n*Catatan: Task berlabel `estimated` pada kolom Confidence sebaiknya dikalibrasi ulang menggunakan data aktual dari tabel `TokenUsageLog` setelah 2-4 minggu produksi.*\n")
    for name in list(active_task_order) + list(zero_run_tasks):
        L.append(f"**{name}** — {TASKS[name]['note']}\n")

    L.append("## 3. Budget Range Analysis (UTAMA)\n")
    if bra:
        mv  = bra["min_viable"]
        opt = bra["optimal"]
        prem = bra["premium"]
        mq  = bra["max_quality"]
        L.append("| Tier | Est. Budget/bln | Biaya Terpakai | Skor Kualitas | Deskripsi |")
        L.append("|---|---|---|---|---|")
        L.append(f"| **Minimum Viable** | ~${mv[0]:.0f} | ${mv[1]:.2f} | {mv[2]:.2f} | Semua floor terpenuhi; model terhemat |")
        if opt:
            L.append(f"| **Optimal (knee)** | ~${opt[0]:.0f} | ${opt[1]:.2f} | {opt[2]:.2f} | Efisiensi terbaik; delta kualitas/$10 mulai landai |")
        if prem:
            L.append(f"| **Premium** | ~${prem[0]:.0f} | ${prem[1]:.2f} | {prem[2]:.2f} | Lonjakan kualitas signifikan (+0.3) di atas knee |")
        L.append(f"| **Max Quality** | ~${mq[0]:.0f} | ${mq[1]:.2f} | {mq[2]:.2f} | Kualitas tertinggi, abaikan biaya |")
        L.append("")
        if opt:
            upper = prem[1] if prem else mq[1]
            upper_q = prem[2] if prem else mq[2]
            L.append(f"> **Range budget optimal: ${opt[1]:.0f}–${upper:.0f}/bulan** (kualitas {opt[2]:.2f}–{upper_q:.2f}/10).")
    else:
        L.append("_(Data frontier tidak tersedia.)_\n")

    L.append("\n## 4. Perbandingan Skenario\n")
    L.append("| Skenario | Biaya/bln | Skor Kualitas |")
    L.append("|---|---|---|")
    L.append(f"| Current settings.yaml | ${current_cost:.2f} | {current_q:.2f} |")
    L.append(f"| Termurah lolos floor | ${min_cost_res['total_cost']:.2f} | {min_cost_q:.2f} |")
    L.append(f"| **Optimal @ ${MONTHLY_BUDGET_USD:.0f}** | **${reco['total_cost']:.2f}** | **{reco_quality:.2f}** |")
    L.append(f"| Kualitas maksimum | ${max_quality_res['total_cost']:.2f} | {max_quality_q:.2f} |\n")

    L.append(f"## 5. Alokasi Model Optimal @ Budget ${MONTHLY_BUDGET_USD:.0f}\n")
    L.append("| Task | Model Terpilih | Kualitas | Fin. Rel | Biaya/bln | Free? |")
    L.append("|---|---|---|---|---|---|")
    for name in active_task_order:
        if name not in reco["assignment"]: continue
        c = reco["assignment"][name]
        fin = f"{c['fin_reliability']:.1f}" if c.get("fin_reliability") is not None else "-"
        L.append(f"| {name} | {c['provider']}/{c['model']} | {c['quality']:.2f} | {fin} | ${c['cost']:.2f} | {'Ya' if c.get('is_free') else 'Tidak'} |")
    L.append(f"\n**Total: ${reco['total_cost']:.2f}/bln** (kualitas: {reco_quality:.2f}/10)\n")

    L.append("## 6. Current Settings.yaml — Breakdown Biaya\n")
    L.append("| Task | Provider/Model | Runs/hari | Biaya/bln | Tipe |")
    L.append("|---|---|---|---|---|")
    for name in list(active_task_order) + list(zero_run_tasks):
        provider, model = CURRENT_SETTINGS_YAML_MAPPING[name]
        t = TASKS[name]
        cost = current_assignment.get(name, {}).get("cost", 0.0)
        tipe = ("Free (Groq)" if provider == "Groq" else
                "Free (Gemini)" if provider == "Gemini" and cost == 0 else
                "Deterministik" if t["runs_per_day"] == 0 else "Berbayar")
        L.append(f"| {name} | {provider}/{model} | {t['runs_per_day']} | ${cost:.2f} | {tipe} |")
    L.append(f"\n**Total current: ${current_cost:.2f}/bln** (kualitas: {current_q:.2f}/10)\n")

    L.append("## 7. Pemakaian Kuota Free Tier\n")
    L.append("### Gemini\n```\n" + describe_gemini_quota(gemini_usage, gemini_caps) + "\n```\n")
    L.append("### Groq (per model)\n```\n" + describe_groq_quota(groq_usage, groq_caps) + "\n```\n")

    L.append("## 8. Kandidat Model per Task\n")
    L.append("Floor minimum: " + ", ".join(f"{k}={v}" for k, v in REASONING_FLOOR.items()) + "\n")
    for name in active_task_order:
        L.append(f"### {name}")
        L.append("| Provider/Model | Kualitas | Kecerdasan | Fin. Rel | Biaya Normal/bln | Free? |")
        L.append("|---|---|---|---|---|---|")
        for c in sorted(raw_candidates[name], key=lambda x: -x.quality):
            free = ("Ya (Groq)" if c.is_groq_free_tier else f"Ya ({c.gemini_tier})" if c.is_gemini_free_tier else "Tidak")
            L.append(f"| {c.provider}/{c.model} | {c.quality:.2f} | {c.general_quality:.1f} | {c.fin_reliability:.1f} | ${c.monthly_cost_paid:.2f} | {free} |")
        L.append("")

    L.append("## 9. Audit Reliabilitas Finansial\n")
    flags = financial_reliability_audit(reco["assignment"], active_task_order)
    if flags:
        for f in flags: L.append(f"- PERINGATAN: {f}")
    else:
        L.append("Tidak ada peringatan fin_reliability.")
    L.append("\n## 10. Audit Risiko Latensi\n")
    flags = latency_risk_check(reco["assignment"], active_task_order)
    if flags:
        for f in flags: L.append(f"- PERINGATAN: {f}")
    else:
        L.append("Tidak ada peringatan TTFT.")
    L.append("\n## 11. Efficiency Frontier\n")
    L.append("| Budget/bln | Biaya Terpakai | Skor Kualitas | Delta Kualitas per $10 |")
    L.append("|---|---|---|---|")
    prev_q, prev_cost = None, None
    for b, cost, q in frontier:
        if cost is None:
            L.append(f"| ${b} | infeasible | - | - |")
            prev_q, prev_cost = None, None
            continue
        marg = "-"
        if prev_q is not None and cost > prev_cost + 0.01:
            marg = f"{(q - prev_q) / ((cost - prev_cost) / 10):.3f}"
        L.append(f"| ${b} | ${cost:.2f} | {q:.2f} | {marg} |")
        prev_q, prev_cost = q, cost
    L.append("")

    L.append("## 12. Value Leaderboard\n")
    rows_paid, rows_free = value_leaderboard(top_n=15)
    L.append("### Model Berbayar\n")
    L.append("| # | Provider/Model | Kecerdasan | Fin. Rel | Harga Blended/1M | Value |")
    L.append("|---|---|---|---|---|---|")
    for i, row in enumerate(rows_paid, 1):
        fin = f"{row['fin_reliability']:.1f}" if row["fin_reliability"] is not None else "-"
        L.append(f"| {i} | {row['provider']}/{row['model']} | {row['quality']:.1f} | {fin} | ${row['blended_price']:.3f} | {row['value']:.2f} |")
    L.append("\n### Model Free Tier — Groq\n")
    L.append("| Provider/Model | Kecerdasan | Fin. Rel | Quota Efektif |")
    L.append("|---|---|---|---|")
    for row in rows_free:
        q_eff = GROQ_QUOTA_EFFECTIVE.get(row["model"], {})
        rpd = q_eff.get("rpd", "?")
        fin = f"{row['fin_reliability']:.1f}" if row["fin_reliability"] is not None else "-"
        L.append(f"| {row['provider']}/{row['model']} | {row['quality']:.1f} | {fin} | {rpd} RPD/hari |")
    L.append("\n## 13. Analisis Sensitivitas\n")
    L.append("| Parameter | Nilai | Biaya/bln | Skor Kualitas |")
    L.append("|---|---|---|---|")
    for row in sensitivity_rows:
        if row["cost"] is None:
            L.append(f"| {row['param']} | {row['value']} | infeasible | - |")
        else:
            L.append(f"| {row['param']} | {row['value']} | ${row['cost']:.2f} | {row['quality']:.2f} |")
    L.append("\n## 14. Sumber Kalibrasi\n")
    L.append("- **AA Intelligence Index v4.1.1** (Agustus 2026)")
    L.append("- **AIMultiple FinanceReasoning + JurisTech (Apr 2026)**")
    L.append("- **Catatan**: Semua QUALITY_SCORE Groq = estimasi interpolasi.\n")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path

def interactive_selection(task_order, all_candidates, gemini_granted, groq_granted):
    print("\n" + "=" * 80 + "\n MODE KUSTOM\n" + "=" * 80)
    assignment = {}
    for task_name in task_order:
        t = TASKS[task_name]
        
        lat_sens = "Ya" if t.get("latency_sensitive") else "Tidak"
        fin_w = t.get("fin_weight", 0)
        note = t.get("note", "")
        
        if t["kind"] == "agentic":
            details = (f"Turns: {t.get('turns', 0)} | Sys: {t.get('system_tokens',0)} | "
                       f"User: {t.get('initial_user_tokens',0)} | Out/Turn: {t.get('per_turn_output_tokens',0)}")
            calls = t['runs_per_day'] * t.get('turns', 1)
        else:
            details = (f"In: {t.get('in_tokens',0)} | Out: {t.get('out_tokens',0)}")
            calls = t['runs_per_day']
            
        high_reasoning = "Ya" if t["reasoning"] in ("High", "Medium-High") else "Tidak"
        cost_efficient = "Tidak" if (t.get("latency_sensitive") or fin_w > 0.25) else "Ya"
        constraint_note = t.get("constraint", "Tidak ada kendala dependensi khusus.")
        
        print(f"\n{'='*80}")
        print(f"Nama Tugas                 : {task_name.upper()}")
        print(f"Deskripsi Komprehensif     : {note}")
        print(f"Kendala / Dependensi       : {constraint_note}")
        print(f"Agentic/Single             : {t['kind'].capitalize()}")
        print(f"Butuh High Reasoning?      : {high_reasoning} (Level: {t['reasoning']})")
        print(f"Boleh Cost Efficient?      : {cost_efficient} (LatSens: {lat_sens}, FinWeight: {fin_w:.2f})")
        print(f"Payload                    : {details}")
        print(f"Run & Call / hari          : {t['runs_per_day']} runs / {calls} calls")
        print(f"Floor                      : {REASONING_FLOOR[t['reasoning']]}")
        print(f"{'='*80}\n")
        
        cands = []
        for c in all_candidates[task_name]:
            if c.is_groq_free_tier:
                granted_here = c.model in groq_granted.get(task_name, set())
                if not granted_here: continue
                eff_cost = 0.0
            elif c.is_gemini_free_tier:
                granted_here = c.gemini_tier in gemini_granted.get(task_name, set())
                eff_cost = 0.0 if granted_here else c.monthly_cost_paid
            else:
                eff_cost = c.monthly_cost_paid
            cands.append({
                "provider": c.provider, "model": c.model, "quality": c.quality,
                "fin_reliability": c.fin_reliability, "cost": eff_cost,
                "is_free": (c.is_gemini_free_tier or c.is_groq_free_tier) and eff_cost == 0.0,
            })
        cands.sort(key=lambda c: (-c["quality"], c["cost"]))
        print(f"| {'No':>2} | {'Provider dan Model':<31} | {'Quality':>7} | {'Fin':>4} | {'Biaya/bln':>10} | {'Status':<6} | {'Free/Paid':<9} |")
        print("|" + "-"*89 + "|")
        for i, c in enumerate(cands, 1):
            status = "Lolos" if c["quality"] >= REASONING_FLOOR[t["reasoning"]] else "Gagal"
            tipe = "Free" if c["is_free"] else "Paid"
            print(f"| {i:2d} | {c['provider']+'/'+c['model']:<31} | {c['quality']:7.2f} | "
                  f"{c['fin_reliability']:4.1f} | ${c['cost']:9.2f} | {status:<6} | {tipe:<9} |")
        while True:
            try:
                ch = int(input(f"  Pilih (1-{len(cands)}): "))
                if 1 <= ch <= len(cands):
                    assignment[task_name] = cands[ch - 1]
                    break
            except ValueError:
                pass
            print("  Input tidak valid.")
    return assignment

# =====================================================================================
# 14. STRUCTURED CONSTRAINTS
# =====================================================================================
TASK_CONSTRAINTS = [
    ("stage1_escalation", "stronger", "stage1_fundamental", "soft"),
    ("stage2_per_asset_secondary", "diff_model", "stage2_per_asset_primary", "hard"),
    ("stage2_adjudicator", "diff_model", "stage2_per_asset_primary", "soft"),
    ("stage2_adjudicator", "diff_model", "stage2_per_asset_secondary", "soft"),
    ("debate_judge", "stronger", "debate_bull", "hard"),
    ("debate_judge", "stronger", "debate_bear", "hard"),
    ("news_classification_escalation", "stronger_soft", "news_classification", "soft"),
    ("news_classification_verifier", "diff_model", "news_classification", "hard"),
    ("news_digest_verifier", "diff_model", "news_digest", "hard"),
    ("fundamental_verifier", "diff_model", "stage1_fundamental", "hard"),
    ("chat_telegram_complex", "stronger", "chat_telegram_medium", "soft"),
]

def _quality_of(provider, model):
    return QUALITY_SCORE.get((provider, model))

def audit_constraints(assignment: dict, label: str = "") -> list[str]:
    violations = []
    for task_a, relation, task_b, severity in TASK_CONSTRAINTS:
        if task_a not in assignment or task_b not in assignment:
            continue
        a = assignment[task_a]
        b = assignment[task_b]
        if relation == "diff_model":
            if a["provider"] == b["provider"] and a["model"] == b["model"]:
                violations.append(
                    f"[{severity.upper()}] {label}'{task_a}' dan '{task_b}' WAJIB beda model, "
                    f"tapi keduanya = {a['provider']}/{a['model']}"
                )
        elif relation in ("stronger", "stronger_soft"):
            qa = _quality_of(a["provider"], a["model"])
            qb = _quality_of(b["provider"], b["model"])
            if qa is None or qb is None:
                continue
            if relation == "stronger" and qa <= qb:
                op = "harus >" if severity == "hard" else "sebaiknya >"
                violations.append(
                    f"[{severity.upper()}] {label}'{task_a}' ({a['provider']}/{a['model']}, q={qa}) "
                    f"{op} '{task_b}' ({b['provider']}/{b['model']}, q={qb}) tapi TIDAK (q sama/lebih rendah)"
                )
            elif relation == "stronger_soft" and qa < qb:
                violations.append(
                    f"[{severity.upper()}] {label}'{task_a}' (q={qa}) sebaiknya >= '{task_b}' (q={qb})"
                )
    return violations

def repair_assignment(effective_candidates: dict, assignment: dict, task_order: list) -> tuple[dict, list[str]]:
    import copy
    assignment = copy.deepcopy(assignment)
    repair_log = []
    for task_a, relation, task_b, severity in TASK_CONSTRAINTS:
        if severity != "hard":
            continue
        if task_a not in assignment or task_b not in assignment:
            continue
        violations = audit_constraints(assignment)
        still_violates = any(f"'{task_a}'" in v and f"'{task_b}'" in v for v in violations)
        if not still_violates:
            continue
        cands = sorted(effective_candidates.get(task_a, []), key=lambda c: (-c["quality"], c["cost"]))
        b = assignment[task_b]
        qb = _quality_of(b["provider"], b["model"]) or 0
        for c in cands:
            if relation == "diff_model" and (c["provider"] != b["provider"] or c["model"] != b["model"]):
                assignment[task_a] = c
                repair_log.append(f"AUTO-REPAIR: '{task_a}' -> {c['provider']}/{c['model']} (hindari duplikasi dgn '{task_b}')")
                break
            if relation == "stronger" and c["quality"] > qb:
                assignment[task_a] = c
                repair_log.append(f"AUTO-REPAIR: '{task_a}' -> {c['provider']}/{c['model']} (quality {c['quality']} > '{task_b}' {qb})")
                break
    return assignment, repair_log

def parse_args(argv):
    p = argparse.ArgumentParser(description="AI Cost & Performance Optimizer v6")
    p.add_argument("--budget",          type=float, default=None)
    p.add_argument("--mode",            choices=["1", "2", "auto", "manual"], default=None)
    p.add_argument("--output",          type=str,   default="ai_cost_analysis_v6.md")
    p.add_argument("--non-interactive", action="store_true")
    p.add_argument("--skip-sensitivity",action="store_true")
    p.add_argument("--gemini-keys",     type=int,   default=None, help="Override GEMINI_FREE_KEYS")
    p.add_argument("--groq-keys",       type=int,   default=None, help="Override GROQ_FREE_KEYS")
    p.add_argument("--prescreen-rate",  type=float, default=None, help="Override PRESCREEN_PASS_RATE (0-1)")
    p.add_argument("--strict-constraints", action="store_true",
                    help="Exit dengan kode error jika ada pelanggaran constraint 'hard' pada rekomendasi")
    return p.parse_args(argv)

def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    global MONTHLY_BUDGET_USD
    if args.budget is not None:
        MONTHLY_BUDGET_USD = args.budget
    
    global GEMINI_FREE_KEYS, GROQ_FREE_KEYS, FLASH_RPD, FLASH_RPM, FLASH_LITE_RPD, FLASH_LITE_RPM, GROQ_QUOTA_EFFECTIVE, PRESCREEN_PASS_RATE, TASKS, GEMINI_TPM_EFFECTIVE
    if args.gemini_keys is not None:
        GEMINI_FREE_KEYS = args.gemini_keys
        FLASH_RPD = FLASH_RPD_PER_KEY * GEMINI_FREE_KEYS
        FLASH_RPM = FLASH_RPM_PER_KEY * GEMINI_FREE_KEYS
        FLASH_LITE_RPD = FLASH_LITE_RPD_PER_KEY * GEMINI_FREE_KEYS
        FLASH_LITE_RPM = FLASH_LITE_RPM_PER_KEY * GEMINI_FREE_KEYS
        GEMINI_TPM_EFFECTIVE = GEMINI_TPM_PER_KEY * GEMINI_FREE_KEYS
    if args.groq_keys is not None:
        GROQ_FREE_KEYS = args.groq_keys
        GROQ_QUOTA_EFFECTIVE = {m: {k: v * GROQ_FREE_KEYS for k, v in q.items()} for m, q in GROQ_QUOTA_PER_KEY.items()}
    if args.prescreen_rate is not None:
        PRESCREEN_PASS_RATE = max(0.05, min(1.0, args.prescreen_rate))
        TASKS = build_tasks_with_prescreen_rate(PRESCREEN_PASS_RATE)

    non_interactive = args.non_interactive or not sys.stdin.isatty()

    print("=" * 80)
    print(" AI COST & PERFORMANCE OPTIMIZER v5")
    print("=" * 80)
    print(f"Gemini: {GEMINI_FREE_KEYS} key gratis + {'1 paid' if GEMINI_HAS_PAID_KEY else 'no paid'}")
    print(f"Groq  : {GROQ_FREE_KEYS} key gratis")
    print(f"Budget: ${MONTHLY_BUDGET_USD:.2f}/bulan")

    print("\n[Self-test] ...")
    run_self_tests()
    print("[Self-test] LULUS.")

    active_task_order = [n for n in TASKS if TASKS[n]["runs_per_day"] > 0]
    zero_run_tasks    = [n for n in TASKS if TASKS[n]["runs_per_day"] == 0]

    if args.mode in ("1", "auto"):   mode = "1"
    elif args.mode in ("2", "manual"): mode = "2"
    elif non_interactive:            mode = "1"
    else:
        print("\n1. Rekomendasi Otomatis\n2. Pilihan Kustom")
        while True:
            mode = input("Pilihan (1/2) [1]: ").strip() or "1"
            if mode in ("1", "2"): break

    if mode == "2":
        raw_candidates = {n: build_candidates_for_task(n) for n in active_task_order}
    else:
        raw_candidates = {n: eligible_candidates(n) for n in active_task_order}

    gemini_granted, gemini_usage, gemini_caps = allocate_gemini_quota(raw_candidates, FLASH_RPD, FLASH_LITE_RPD)
    groq_granted, groq_usage, groq_caps = allocate_groq_quota(raw_candidates, GROQ_QUOTA_EFFECTIVE)
    effective = build_effective_candidates(raw_candidates, gemini_granted, groq_granted)

    if mode == "2" and not non_interactive:
        reco_assignment = interactive_selection(active_task_order, raw_candidates, gemini_granted, groq_granted)
        reco = {"assignment": reco_assignment, "total_cost": sum(c["cost"] for c in reco_assignment.values())}
    else:
        reco = optimize_for_budget(effective, active_task_order, MONTHLY_BUDGET_USD, resolution_cents=1)
        if reco is None:
            min_f = min_cost_baseline(effective, active_task_order)["total_cost"]
            raise RuntimeError(f"Budget ${MONTHLY_BUDGET_USD:.2f} tidak cukup. Minimum: ${min_f:.2f}/bulan.")
    
    reco_assignment_for_audit = {k: {"provider": v["provider"], "model": v["model"]} for k, v in reco["assignment"].items()}
    reco_violations = audit_constraints(reco_assignment_for_audit, label="[REKOMENDASI] ")
    if reco_violations:
        print("\n[WARN] PELANGGARAN CONSTRAINT PADA REKOMENDASI:")
        for v in reco_violations:
            print(f"  - {v}")
        repaired, repair_log = repair_assignment(effective, reco["assignment"], active_task_order)
        if repair_log:
            print("  Auto-repair diterapkan:")
            for r in repair_log:
                print(f"  - {r}")
            reco["assignment"] = repaired
            reco["total_cost"] = sum(c["cost"] for c in repaired.values())

    reco_quality = weighted_quality_score(reco["assignment"], active_task_order)
    tpm_warnings = check_tpm_feasibility(effective, active_task_order)

    min_cost_res    = min_cost_baseline(effective, active_task_order)
    max_quality_res = max_quality_baseline(effective, active_task_order)
    min_cost_q      = weighted_quality_score(min_cost_res["assignment"], active_task_order)
    max_quality_q   = weighted_quality_score(max_quality_res["assignment"], active_task_order)

    current_assignment: dict = {}
    current_cost = 0.0
    for name in list(active_task_order) + list(zero_run_tasks):
        provider, model = CURRENT_SETTINGS_YAML_MAPPING[name]
        t = TASKS[name]
        if t["runs_per_day"] == 0 or provider == "Groq":
            eff_cost = 0.0
        else:
            cand = next((c for c in effective.get(name, []) if c["provider"] == provider and c["model"] == model), None)
            if cand is not None:
                eff_cost = cand["cost"]
            else:
                per_run = raw_task_cost_per_run(name, provider, model)
                paid = per_run * t["runs_per_day"] * DAYS_PER_MONTH
                gt = GEMINI_TIER.get(model) if provider == "Gemini" else None
                eff_cost = 0.0 if (provider == "Gemini" and gt in gemini_granted.get(name, set())) else paid
        q_val = effective_quality(name, provider, model) or QUALITY_SCORE.get((provider, model), 5.0)
        fin_val = FIN_RELIABILITY_SCORE.get((provider, model))
        current_assignment[name] = {"provider": provider, "model": model, "quality": q_val, "fin_reliability": fin_val, "cost": eff_cost, "is_free": eff_cost == 0.0}
        current_cost += eff_cost
    current_q = weighted_quality_score({k: v for k, v in current_assignment.items() if k in active_task_order}, active_task_order)

    current_for_audit = {k: {"provider": p, "model": m} for k, (p, m) in CURRENT_SETTINGS_YAML_MAPPING.items()}
    current_violations = audit_constraints(current_for_audit, label="[SETTINGS.YAML AKTUAL] ")
    if current_violations:
        print("\n[FAIL] PELANGGARAN CONSTRAINT DI settings.yaml SAAT INI:")
        for v in current_violations:
            print(f"  - {v}")

    sweep_points = [0, 5, 10, 20, 30, 40, 50, 60, 75, 100, 125, 150, 200, 250, 300]
    frontier = []
    for b in sweep_points:
        r = optimize_for_budget(effective, active_task_order, b, resolution_cents=10)
        if r is None:
            frontier.append((b, None, None))
        else:
            frontier.append((b, r["total_cost"], weighted_quality_score(r["assignment"], active_task_order)))
    bra = budget_range_analysis(frontier)

    if args.skip_sensitivity:
        sensitivity_rows = []
    else:
        print("\n[Sensitivitas] Sweep budget/Gemini-keys/Groq-keys/prescreen-rate...")
        sensitivity_rows = sensitivity_analysis(MONTHLY_BUDGET_USD, GEMINI_FREE_KEYS, GROQ_FREE_KEYS, PRESCREEN_PASS_RATE)

    print(f"\n{'Skenario':52s} {'Biaya/bln':>12s} {'Kualitas':>10s}")
    print("-" * 78)
    print(f"{'Current settings.yaml':52s} ${current_cost:>10.2f}  {current_q:>8.2f}")
    print(f"{'Termurah lolos floor':52s} ${min_cost_res['total_cost']:>10.2f}  {min_cost_q:>8.2f}")
    print(f"{'Rekomendasi @ $'+str(int(MONTHLY_BUDGET_USD)):52s} ${reco['total_cost']:>10.2f}  {reco_quality:>8.2f}")
    print(f"{'Kualitas maksimum':52s} ${max_quality_res['total_cost']:>10.2f}  {max_quality_q:>8.2f}")

    print(f"\n{describe_gemini_quota(gemini_usage, gemini_caps)}")
    print(f"\n{describe_groq_quota(groq_usage, groq_caps)}")

    if bra:
        print("\n" + "=" * 55 + " BUDGET RANGE ANALYSIS")
        mv = bra["min_viable"]
        print(f"  Minimum Viable  : ${mv[1]:.2f}/bln  (kualitas: {mv[2]:.2f})")
        if bra["optimal"]:
            opt = bra["optimal"]
            print(f"  Optimal (knee)  : ${opt[1]:.2f}/bln  (kualitas: {opt[2]:.2f})")
        if bra["premium"]:
            prem = bra["premium"]
            print(f"  Premium         : ${prem[1]:.2f}/bln  (kualitas: {prem[2]:.2f})")
        mq = bra["max_quality"]
        print(f"  Max Quality     : ${mq[1]:.2f}/bln  (kualitas: {mq[2]:.2f})")
        if bra["optimal"]:
            upper = bra["premium"][1] if bra["premium"] else bra["max_quality"][1]
            print(f"  => Range optimal: ${bra['optimal'][1]:.0f}–${upper:.0f}/bulan")

    for w in rpm_risk_check(reco["assignment"], active_task_order): print(f"PERINGATAN [RPM]: {w}")
    for w in latency_risk_check(reco["assignment"], active_task_order): print(f"PERINGATAN [Latency]: {w}")
    for w in financial_reliability_audit(reco["assignment"], active_task_order): print(f"PERINGATAN [FinReliability]: {w}")

    print(f"\nAlokasi model per-task @ ${MONTHLY_BUDGET_USD:.0f}:")
    for name in active_task_order:
        if name not in reco["assignment"]: continue
        c = reco["assignment"][name]
        tag = " [FREE]" if c.get("is_free") else ""
        fin = f"{c['fin_reliability']:.1f}" if c.get("fin_reliability") else "-"
        print(f"  {name:38s} {c['provider']}/{c['model']:24s} q={c['quality']:.2f} fin={fin} ${c['cost']:.2f}/bln{tag}")

    report_path = write_markdown_report(
        active_task_order, zero_run_tasks,
        raw_candidates, gemini_granted, gemini_usage, gemini_caps,
        groq_granted, groq_usage, groq_caps,
        reco, reco_quality, min_cost_res, min_cost_q, max_quality_res, max_quality_q,
        current_cost, current_q, current_assignment,
        frontier, bra, sensitivity_rows,
        current_violations, reco_violations, tpm_warnings,
        path=args.output,
    )
    print(f"\nLaporan: {report_path}")

    hard_unresolved = [v for v in audit_constraints(reco_assignment_for_audit) if v.startswith("[HARD]")]
    if args.strict_constraints and hard_unresolved:
        print("\n[ERROR] --strict-constraints aktif dan masih ada pelanggaran HARD setelah auto-repair. Exiting(1).")
        sys.exit(1)

if __name__ == "__main__":
    main()
