# ==============================================================================
# File: application/benchmark/task_specs/chat_cases.py
# ==============================================================================

"""
Telegram, interactive chat co-pilot, and voice command benchmark task specs.
"""

from __future__ import annotations

from typing import Any

from monika.application.analysis.tools.tools_definitions import OPERATOR_INTERACTIVE_TOOLS

from ..db_access import latest_user_message
from ..fixture_loader import get_golden_voice_transcripts
from .base import BenchmarkCase

_FALLBACK_CHAT_QUESTIONS = [
    "What is the current account status and open positions?",
    "Summarize the latest fundamental brief and its implications for XAUUSD.",
    "What is current VIX and how does it affect our risk sentiment?",
]


async def _build_chat_case(session: Any, settings: dict[str, Any], ex: Any, idx: int) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    msg = None
    if not use_fixtures and session:
        try:
            msg = await latest_user_message(session)
        except Exception:
            msg = None
    if not msg:
        msg = _FALLBACK_CHAT_QUESTIONS[idx % len(_FALLBACK_CHAT_QUESTIONS)]
    sysp = (
        "You are an AI Trading Assistant. Use tools for real-time data. "
        "Answer grounded in data, do not fabricate numbers. Markdown format, concise."
    )
    return BenchmarkCase(
        f"chat_{idx}",
        "chat",
        sysp,
        msg,
        tools=OPERATOR_INTERACTIVE_TOOLS,
        history=[],
        role_kwargs=dict(max_tokens=3000, max_tool_turns=8, thinking="medium"),
        context_summary=msg,
    )


async def _case_chat_telegram(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    return await _build_chat_case(session, settings, ex, 0)


async def _case_chat_telegram_medium(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    return await _build_chat_case(session, settings, ex, 1)


async def _case_chat_telegram_complex(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    return await _build_chat_case(session, settings, ex, 2)


async def _case_jev_telegram_intent(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    prompt = "Tolong analisis apakah posisi EURUSD kita masih aman setelah lonjakan inflasi flash CPI Jerman tadi?"
    schema = {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["risk_inquiry", "market_question", "command", "chat", "panic_intervention"],
            },
            "requires_agent_loop": {"type": "boolean"},
            "target_symbol": {"type": "string"},
            "urgency": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": ["intent", "requires_agent_loop", "urgency"],
    }
    return BenchmarkCase(
        "jev_telegram_intent",
        "chat",
        system_prompt="You are a high-speed Telegram intent classifier for trading assistant.",
        user_prompt=prompt,
        schema=schema,
        role_kwargs=dict(max_tokens=256, thinking="none", temperature=0.0),
        context_summary=prompt,
    )


async def _case_chat_interactive_fast(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    prompt = "Berapa status spread dan floating drawdown akun saat ini?"
    return BenchmarkCase(
        "chat_interactive_fast",
        "chat",
        system_prompt="You are Monika's ultra-responsive terminal co-pilot. Keep replies concise and data-grounded.",
        user_prompt=prompt,
        history=[],
        role_kwargs=dict(max_tokens=512, thinking="none"),
        context_summary=prompt,
    )


async def _case_chat_interactive_balanced(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    prompt = "Jelaskan mengapa sinyal BUY pada pair XAUUSD ditolak oleh RiskGate pada sesi Asia tadi malam."
    return BenchmarkCase(
        "chat_interactive_balanced",
        "chat",
        system_prompt="You are Monika's analytical trading assistant. Provide clear, balanced explanations citing specific rules and market data.",
        user_prompt=prompt,
        history=[],
        role_kwargs=dict(max_tokens=1500, thinking="low"),
        context_summary=prompt,
    )


async def _case_chat_interactive_reasoning(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    prompt = (
        "Analisis korelasi transmisi antara lonjakan harga minyak Brent ke $106/bbl terhadap imbal hasil US 10Y "
        "dan ekspektasi pemotongan suku bunga The Fed pada kuartal 4 2026. Bagaimana dampaknya terhadap EURUSD dan XAUUSD?"
    )
    return BenchmarkCase(
        "chat_interactive_reasoning",
        "chat",
        system_prompt="You are Monika's deep macro reasoning engine. Provide multi-step causal reasoning with yield differentials and cross-asset spillover.",
        user_prompt=prompt,
        history=[],
        role_kwargs=dict(max_tokens=4096, thinking="high"),
        context_summary=prompt,
    )


async def _case_chat_interactive_pro(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    prompt = (
        "Evaluasi strategi trailing stop berbasis 1.5x ATR versus dynamic ADR-cap pada aset EURUSD saat regime chop vs trending. "
        "Berapa ekspektansi matematis dan maximum drawdown reduction yang didapat?"
    )
    return BenchmarkCase(
        "chat_interactive_pro",
        "chat",
        system_prompt="You are Monika's Senior Quantitative Strategist and Portfolio Architect.",
        user_prompt=prompt,
        history=[],
        role_kwargs=dict(max_tokens=4096, thinking="high"),
        context_summary=prompt,
    )


async def _case_voice_transcription(session: Any, settings: dict[str, Any], ex: Any) -> BenchmarkCase:
    transcripts = get_golden_voice_transcripts()
    case = transcripts[0] if transcripts else {}
    audio_text = case.get(
        "raw_transcript", "Monika tolong amankan profit buy gold sekarang ya geser stop loss ke break even"
    )
    prompt = (
        f"Audio Transcript: '{audio_text}'.\n\n"
        "Extract structured order intent: symbol, action, entry_type, price, stop_loss, take_profit."
    )
    schema = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "action": {
                "type": "string",
                "enum": ["BUY", "SELL", "UPDATE_STOP_LOSS", "CLOSE_SYMBOL_POSITIONS", "PENDING_BUY_LIMIT"],
            },
            "order_type": {"type": "string", "enum": ["LIMIT", "STOP", "MARKET", "BREAK_EVEN"]},
            "price": {"type": ["number", "null"]},
            "stop_loss": {"type": ["number", "string", "null"]},
            "take_profit": {"type": ["number", "null"]},
        },
        "required": ["symbol", "action"],
    }
    return BenchmarkCase(
        "voice_transcription",
        "chat",
        system_prompt="You are a voice trading command parser converting spoken transcriptions into structured orders.",
        user_prompt=prompt,
        schema=schema,
        role_kwargs=dict(max_tokens=512, thinking="none"),
        context_summary=prompt,
    )
