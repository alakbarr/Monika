# ==============================================================================
# File: config/profile_applicator.py
# ==============================================================================

"""
Profile Applicator for Monika LLM Task Roles.
Deterministic, multi-provider mapping for all 49 task roles across 6 operational profiles:
  1. high_analysis_high_freq: Analisis Tinggi — Frekuensi Tinggi
  2. high_analysis_low_freq:  Analisis Tinggi — Frekuensi Rendah
  3. simple_task_high_freq:   Tugas Sederhana — Frekuensi Tinggi
  4. simple_task_low_freq:    Tugas Sederhana — Frekuensi Rendah
  5. low_latency_smart:       Latensi Rendah — Cerdas
  6. low_latency_cheap:       Latensi Rendah — Murah / Hemat
"""

import os
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("TradingAgent.ProfileApplicator")

ALL_TASK_ROLES = [
    "stage1_shadow_check",
    "stage1_fundamental",
    "stage1_escalation",
    "stage2_per_asset_primary",
    "stage2_per_asset_secondary",
    "stage2_session_trigger",
    "stage2_prescreen",
    "debate_bear",
    "debate_bull",
    "debate_judge",
    "risk_gate_conservative",
    "risk_gate_aggressive",
    "risk_gate_neutral",
    "risk_gate",
    "macro_analyst",
    "sentiment_analyst",
    "portfolio_manager_per_trade",
    "adversarial_check",
    "news_classification",
    "jev_news_realtime",
    "jev_trigger_validator",
    "jev_position_guard",
    "jev_telegram_intent",
    "jev_exit_prescreen",
    "news_classification_escalation",
    "news_classification_verifier",
    "news_digest",
    "news_digest_macro_overview",
    "news_digest_verifier",
    "fundamental_verifier",
    "cot_precompute",
    "specialist_technical",
    "specialist_sentiment",
    "specialist_macro",
    "portfolio_synthesis",
    "stage2_adjudicator",
    "trade_reflection",
    "chat_telegram",
    "chat_telegram_medium",
    "chat_telegram_complex",
    "chat_interactive_fast",
    "chat_interactive_balanced",
    "chat_interactive_reasoning",
    "chat_interactive_pro",
    "deep_research",
    "context_compaction",
    "summarizer",
    "report_synthesizer",
    "pattern_context_verifier",
    "jev_confluence_gate",
    "jev_session_timing_gate",
    "jev_debate_evaluator",
    "voice_transcription",
]
ALL_49_ROLES = ALL_TASK_ROLES


PROFILE_METADATA = {
    "high_analysis_high_freq": {
        "title": "High Analysis — High Frequency",
        "description": "Active scalping and intraday trading. Deep multi-step reasoning with rapid turnover. Suitable for volatile markets.",
        "recommended_keys": ["gemini", "openrouter", "anthropic", "9router"],
    },
    "high_analysis_low_freq": {
        "title": "High Analysis — Low Frequency",
        "description": "Swing trading and macro overview. Rigorous reasoning at wider evaluation intervals (4-8h) to conserve rate limits.",
        "recommended_keys": ["gemini", "openrouter", "anthropic"],
    },
    "simple_task_high_freq": {
        "title": "Simple Tasks — High Frequency",
        "description": "Rapid technical screening and continuous indicator polling. Minimal token and rate-limit overhead.",
        "recommended_keys": ["gemini", "groq", "9router"],
    },
    "simple_task_low_freq": {
        "title": "Simple Tasks — Low Frequency",
        "description": "Passive market monitoring with 1-2 periodic evaluations per day. Fully sustainable on a single free Gemini API key.",
        "recommended_keys": ["gemini"],
    },
    "low_latency_smart": {
        "title": "Low Latency — Smart",
        "description": "Rapid execution against price spikes (flash crash, trailing stops) with high-fidelity validation logic.",
        "recommended_keys": ["gemini", "groq", "anthropic"],
    },
    "low_latency_cheap": {
        "title": "Low Latency — Cost-Optimized",
        "description": "Maximum cost efficiency (free-tier friendly), high execution throughput. Ideal for testing and educational use.",
        "recommended_keys": ["gemini", "9router"],
    },
}


class ProfileApplicator:
    """Generates complete 49-role LLM configuration dictionary based on profile and available keys."""

    @staticmethod
    def detect_available_providers(env_dict: Optional[Dict[str, str]] = None) -> Dict[str, bool]:
        """Detect which providers have valid API keys in environment or supplied dictionary."""
        env = env_dict if env_dict is not None else os.environ
        return {
            "gemini": bool(env.get("GEMINI_API_KEY") or env.get("GEMINI_API_KEYS")),
            "openrouter": bool(env.get("OPENROUTER_API_KEY") or env.get("OPENROUTER_API_KEYS")),
            "anthropic": bool(env.get("ANTHROPIC_API_KEY") or env.get("ANTHROPIC_API_KEYS")),
            "openai": bool(env.get("OPENAI_API_KEY")),
            "groq": bool(env.get("GROQ_API_KEY")),
            "deepseek": bool(env.get("DEEPSEEK_API_KEY")),
            "9router": bool(env.get("ENABLE_9ROUTER", "true").lower() in ("1", "true", "yes")),
        }

    @classmethod
    def build_task_roles_config(
        cls,
        profile_key: str = "low_latency_cheap",
        available_providers: Optional[Dict[str, bool]] = None,
    ) -> Dict[str, Any]:
        """
        Build complete task_roles dictionary for all 49 roles deterministically.
        Ensures NO orphan role falls back to an unconfigured provider.
        """
        if profile_key not in PROFILE_METADATA:
            profile_key = "low_latency_cheap"

        provs = available_providers or cls.detect_available_providers()
        has_gemini = provs.get("gemini", False)
        has_anthropic = provs.get("anthropic", False)
        has_openrouter = provs.get("openrouter", False)
        has_groq = provs.get("groq", False)
        has_9router = provs.get("9router", True)

        # ── Model Selection Strategy ──────────────────────────────────────────
        # Heavy reasoning models (Judges, Reflections, Macro Synthesis)
        if has_anthropic and profile_key in ("high_analysis_high_freq", "high_analysis_low_freq"):
            heavy_primary = "claude-3-5-sonnet"
            heavy_fallback = "gemini-3.8-flash" if has_gemini else "openrouter/free"
        elif has_gemini:
            heavy_primary = "gemini-3.8-flash" if profile_key != "high_analysis_low_freq" else "gemini-3.7-flash"
            heavy_fallback = "gemini-3.5-flash-lite"
        elif has_openrouter:
            heavy_primary = "openrouter/anthropic/claude-3.5-sonnet"
            heavy_fallback = "openrouter/google/gemini-3.5-flash"
        elif has_9router:
            heavy_primary = "kr/claude-sonnet-4.5"
            heavy_fallback = "kr/claude-sonnet-4.5-thinking"
        else:
            heavy_primary = "gemini-3.5-flash-lite"
            heavy_fallback = "gemini-3.1-flash-lite"

        # Debater models (Bull, Bear, Specialists)
        if has_gemini:
            debater_primary = "gemini-3.8-flash" if "high_analysis" in profile_key or profile_key == "low_latency_smart" else "gemini-3.5-flash-lite"
            debater_fallback = "gemini-3.5-flash-lite"
        elif has_anthropic and "high_analysis" in profile_key:
            debater_primary = "claude-3-5-haiku-20241022"
            debater_fallback = "claude-3-5-sonnet"
        elif has_groq and profile_key in ("simple_task_high_freq", "low_latency_smart"):
            debater_primary = "groq-compound"
            debater_fallback = "groq-compound-mini"
        elif has_openrouter:
            debater_primary = "openrouter/google/gemini-3.5-flash"
            debater_fallback = "openrouter/free"
        else:
            debater_primary = "gemini-3.5-flash-lite"
            debater_fallback = "gemini-3.1-flash-lite"

        # Fast screening / classification / micro-gates models (High rate-limit tolerance: 500 RPD)
        if has_groq and profile_key in ("simple_task_high_freq", "low_latency_smart", "low_latency_cheap"):
            fast_primary = "groq-compound-mini"
            fast_fallback = "gemini-3.1-flash-lite" if has_gemini else "groq-gpt-oss-20b"
        elif has_gemini:
            fast_primary = "gemini-3.5-flash-lite"
            fast_fallback = "gemini-3.1-flash-lite"
        elif has_openrouter:
            fast_primary = "openrouter/free"
            fast_fallback = "openrouter/google/gemini-3.5-flash"
        elif has_9router:
            fast_primary = "kr/claude-sonnet-4.5"
            fast_fallback = "kr/claude-sonnet-4.5-thinking"
        else:
            fast_primary = "gemini-3.1-flash-lite"
            fast_fallback = "gemini-3.5-flash-lite"

        # System One Micro-Gates (Jev)
        jev_primary = "gemini-3.1-flash-lite" if has_gemini else fast_primary
        jev_fallback = fast_fallback

        # Group classification of the 49 roles
        heavy_roles = {
            "stage1_fundamental", "stage1_escalation", "stage2_per_asset_primary",
            "stage2_per_asset_secondary", "stage2_adjudicator", "debate_judge",
            "trade_reflection", "portfolio_synthesis", "deep_research",
            "report_synthesizer", "chat_telegram_complex", "macro_analyst",
        }

        debater_roles = {
            "debate_bull", "debate_bear", "sentiment_analyst", "specialist_technical",
            "specialist_sentiment", "specialist_macro", "adversarial_check",
            "portfolio_manager_per_trade", "fundamental_verifier", "pattern_context_verifier",
            "risk_gate", "risk_gate_conservative", "risk_gate_aggressive", "risk_gate_neutral",
        }

        jev_micro_roles = {
            "jev_news_realtime", "jev_trigger_validator", "jev_position_guard",
            "jev_telegram_intent", "jev_exit_prescreen", "jev_confluence_gate",
            "jev_session_timing_gate", "jev_debate_evaluator",
        }

        task_roles_config: Dict[str, Any] = {}

        for role in ALL_TASK_ROLES:
            if role == "chat_interactive_fast":
                p_mod = "gemini-3.5-flash-lite" if has_gemini else fast_primary
                fb_mod = "gemini-3.1-flash-lite" if has_gemini else fast_fallback
                tokens = 4096
                temp = 0.2
            elif role == "chat_interactive_balanced":
                p_mod = "gemini-3.7-flash" if has_gemini else debater_primary
                fb_mod = "gemini-3.6-flash" if has_gemini else debater_fallback
                tokens = 4096
                temp = 0.1
            elif role == "chat_interactive_reasoning":
                p_mod = "gemini-3.8-flash" if has_gemini else heavy_primary
                fb_mod = "gemini-3.7-flash" if has_gemini else heavy_fallback
                tokens = 8192
                temp = 0.0
            elif role == "chat_interactive_pro":
                p_mod = "gemini-3.1-pro-preview" if has_gemini else heavy_primary
                fb_mod = "gemini-3.8-flash" if has_gemini else heavy_fallback
                tokens = 8192
                temp = 0.0
            elif role == "voice_transcription":
                p_mod = "gemini-3.8-live" if has_gemini else "gemini-3.5-transcribe-live"
                fb_mod = "gemini-3.8-live-extended-thinking" if has_gemini else "gemini-3-flash-live"
                tokens = 2048
                temp = 0.0
            elif role in heavy_roles:
                p_mod = heavy_primary
                fb_mod = heavy_fallback
                tokens = 8192 if "high_analysis" in profile_key else 4096
                temp = 0.0
            elif role in debater_roles:
                p_mod = debater_primary
                fb_mod = debater_fallback
                tokens = 4096 if "high_analysis" in profile_key else 2048
                temp = 0.1 if "debate" in role else 0.0
            elif role in jev_micro_roles:
                p_mod = jev_primary
                fb_mod = jev_fallback
                tokens = 1024
                temp = 0.0
            else:
                # Fast / screening / chat roles
                p_mod = fast_primary
                fb_mod = fast_fallback
                tokens = 2048
                temp = 0.0

            task_roles_config[role] = {
                "primary": p_mod,
                "fallback_1": fb_mod,
                "max_tokens": tokens,
                "temperature": temp,
            }

        return task_roles_config

    @classmethod
    def apply_profile_to_settings(
        cls,
        settings_path: str,
        profile_key: str,
        available_providers: Optional[Dict[str, bool]] = None,
    ) -> bool:
        """
        Atomically applies profile to settings.yaml, fully replacing task_roles
        with guaranteed 49-role coverage.
        """
        from config.atomic_writer import AtomicConfigWriter

        new_roles = cls.build_task_roles_config(profile_key, available_providers)
        payload = {
            "llm": {
                "active_profile": profile_key,
                "task_roles": new_roles,
            }
        }
        try:
            AtomicConfigWriter.update_in_place(settings_path, payload)
            logger.info(f"[ProfileApplicator] Successfully mapped all 49 task roles for profile '{profile_key}' into {settings_path}")
            return True
        except Exception as e:
            logger.error(f"[ProfileApplicator] Failed to apply profile to {settings_path}: {e}")
            return False
