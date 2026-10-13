import json
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Awaitable, Any
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("Benchmark.TaskSpecs")

from monika.application.skills.loader import compose_system_prompt
from monika.application.analysis.prefetch.stage1_prefetcher import Stage1DataBundler
from monika.application.analysis.prefetch.stage2_prefetcher import Stage2DataBundler
from monika.application.analysis.stages.fundamental_stage import USER_MESSAGE as STAGE1_USER_MESSAGE_TEXT
from monika.application.analysis.stages.per_asset_stage import (
    SPECIALIST_PROMPTS,
    SYMBOL_TO_COT,
    _render_specialist_prompt,
    PerAssetStage,
)
from monika.application.analysis.schemas.schemas import get_tool_schema, SubmitFundamentalBriefSchema
from monika.application.analysis.tools.tools_definitions import STAGE1_TOOLS, STAGE2_TOOLS, TELEGRAM_TOOLS
from monika.application.analysis.calculators.unified_threshold_calculator import compute_unified_confluence_threshold
from monika.application.analysis.debate.fact_sheet import build_fact_sheet
from monika.application.analysis.debate.bull_analyst import generate_bull_advocacy
from monika.application.analysis.debate.bear_analyst import generate_bear_dissent
from monika.application.analysis.debate.investment_judge import evaluate_debate
from monika.application.analysis.debate.conservative_risk_llm import analyze_risk_conservative_llm
from monika.application.analysis.debate.aggressive_risk_llm import analyze_risk_aggressive_llm
from monika.application.analysis.debate.neutral_risk_llm import analyze_risk_neutral_llm
from monika.application.analysis.debate.portfolio_manager import make_portfolio_decision
from monika.application.analysis.debate.deterministic_risk import (
    analyze_risk_conservative,
    analyze_risk_aggressive,
    analyze_risk_neutral,
)
from monika.application.analysis.validators.fundamental_verifier import (
    VERIFIER_SCHEMA,
    FUNDAMENTAL_VERIFIER_SYSTEM_PROMPT,
)
from monika.application.analysis.memory.reflector import REFLECTION_SCHEMA, TradeReflector
from monika.application.analysis.prefetch.news_digest import (
    NEWS_CLASSIFICATION_SCHEMA,
    DIGEST_CONSISTENCY_SCHEMA,
    NewsDigestProcessor,
)
from monika.application.analysis.prefetch.macro_preprocessor import MacroPreprocessor
from monika.application.protocol.context_coherence import get_base_quote_tags

from .db_access import (
    pick_asset_analysis,
    latest_brief,
    latest_digest,
    recent_news,
    resolved_reflection,
    latest_user_message,
    entry_context,
    BenchmarkToolExecutor,
)
from .invoker import make_client
from .fixture_loader import (
    load_fixture_json,
    get_synthetic_market_snapshot,
    get_synthetic_stage1_bundle,
    get_synthetic_stage2_bundle,
    get_synthetic_fundamental_brief,
    get_synthetic_news_items,
    get_synthetic_risk_context,
    get_synthetic_debate_claims,
    get_synthetic_compaction_payload,
    get_synthetic_session_reports_payload,
    get_synthetic_fomc_transcript_payload,
    get_synthetic_macro_anomaly_payload,
    get_synthetic_sentiment_feed_payload,
    get_golden_macro_stage1,
    get_golden_escalation_crisis,
    get_golden_shadow_check_audit,
    get_golden_asset_bundle,
    get_golden_prescreen_matrix,
    get_golden_technical_indicators,
    get_golden_sentiment_matrix,
    get_golden_pattern_case,
    get_golden_debate_case,
    get_golden_adjudication_case,
    get_golden_jev_debate_clash,
    get_golden_risk_state,
    get_golden_adversarial_case,
    get_golden_trade_reflection,
    get_production_decision_reflections,
    get_golden_concurrent_orders,
    get_golden_news_batch,
    get_golden_breaking_news,
    get_golden_news_digest,
    get_synthetic_news_digest,
    get_production_news_1000,
    get_golden_jev_reflexes,
    get_golden_jev_confluence,
    get_golden_jev_timing,
    get_golden_telegram_dialogues,
    get_golden_voice_transcripts,
    get_golden_reasoning_prompts,
)


@dataclass
class BenchmarkCase:
    context_key: str
    category: str
    system_prompt: str = ""
    user_prompt: str = ""
    schema: Optional[dict] = None
    tools: Optional[list] = None
    stage_name: str = ""
    history: Optional[list] = None
    role_kwargs: dict = field(default_factory=dict)
    custom_fn: Optional[Callable] = None
    custom_args: tuple = ()
    context_summary: str = ""  # yang dilihat judge sebagai "context yang diberikan"
    state: Optional[dict] = None
    questions: Optional[list] = None
    expected_answers: Optional[dict] = None
    latency_target_ms: float = 100.0
    fixture_data: Optional[dict] = None

    def __init__(
        self,
        context_key: str,
        category: str,
        system_prompt: str = "",
        user_prompt: str = "",
        schema: Optional[dict] = None,
        tools: Optional[list] = None,
        stage_name: str = "",
        history: Optional[list] = None,
        role_kwargs: Optional[dict] = None,
        custom_fn: Optional[Callable] = None,
        custom_args: tuple = (),
        context_summary: str = "",
        state: Optional[dict] = None,
        questions: Optional[list] = None,
        expected_answers: Optional[dict] = None,
        latency_target_ms: float = 100.0,
        fixture_data: Optional[dict] = None,
    ):
        self.context_key = context_key
        self.category = category
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.schema = schema
        self.tools = tools
        self.stage_name = stage_name
        self.history = history
        self.role_kwargs = role_kwargs if role_kwargs is not None else {}
        self.custom_fn = custom_fn
        self.custom_args = custom_args
        self.context_summary = context_summary
        self.state = state
        self.questions = questions
        self.expected_answers = expected_answers
        self.latency_target_ms = latency_target_ms
        self.fixture_data = fixture_data


@dataclass
class TaskSpec:
    task_id: str
    category: str
    mode: str  # "agent" | "json" | "text" | "chat" | "custom" | "system_one"
    build_case: Callable[[AsyncSession, dict, BenchmarkToolExecutor], Awaitable[BenchmarkCase]]


def _sym(settings: dict) -> str:
    return settings.get("_benchmark_symbol") or settings.get("trading", {}).get("asset_universe", ["EURUSD"])[0]


# =========================================================================
# STAGE 1 (macro) -- mode agent, pakai skill loader ASLI + bundle prefetch ASLI
# =========================================================================
def _stage1_system_prompt(settings: dict) -> str:
    skills = [
        "macro_analysis_framework",
        "market_dynamics_framework",
        "performance_notes",
        "fundamental_performance_notes",
    ]
    if settings.get("trading", {}).get("caveman_mode", False):
        skills.append("caveman_mode")
    return compose_system_prompt(*skills)


async def _case_stage1_fundamental(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    bundle = None
    if not use_fixtures and session:
        try:
            bundle, _, _ = await Stage1DataBundler(session, settings).prefetch_all_data()
        except Exception:
            bundle = None
    if not bundle:
        bundle = get_synthetic_stage1_bundle()
    user_msg = STAGE1_USER_MESSAGE_TEXT + f"\n\n[PRE-FETCHED DATA]\n{bundle}"
    return BenchmarkCase(
        "stage1",
        "macro",
        _stage1_system_prompt(settings),
        user_msg,
        tools=STAGE1_TOOLS,
        stage_name="benchmark_stage1_fundamental",
        role_kwargs=dict(max_tokens=12000, max_tool_turns=8, thinking="high"),
        context_summary=bundle,
    )


async def _case_stage1_escalation(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    bundle = None
    if not use_fixtures and session:
        try:
            bundle, _, _ = await Stage1DataBundler(session, settings).prefetch_all_data()
        except Exception:
            bundle = None
    if not bundle:
        bundle = get_synthetic_stage1_bundle()
    prior_json = "{}"
    if use_fixtures:
        esc = get_golden_escalation_crisis()
        cat = esc.get("catalyst_event", {})
        prior_json = json.dumps(get_synthetic_fundamental_brief())
        escalation_note = f"\n\n--- CRITICAL ESCALATION TRIGGER ---\n{cat.get('headline')}\nImpact: {cat.get('impact')} | Source: {cat.get('source')}\nRe-evaluate macro regime and risk posture under acute crisis shock."
    elif session:
        try:
            prior_json = (await latest_brief(session)).structured_json or "{}"
        except Exception:
            pass
        escalation_note = "\n\n--- ESCALATION REQUIRED ---\nPrior brief had low confidence. Re-evaluate exhaustively with maximum rigor, resolving all ambiguities explicitly."
    else:
        prior_json = json.dumps(get_synthetic_fundamental_brief())
        escalation_note = "\n\n--- ESCALATION REQUIRED ---\nPrior brief had low confidence."

    user_msg = (
        STAGE1_USER_MESSAGE_TEXT + f"\n\n[PRE-FETCHED DATA]\n{bundle}{escalation_note}\nPRIOR BRIEF:\n{prior_json}"
    )
    return BenchmarkCase(
        "stage1_escalation",
        "macro",
        _stage1_system_prompt(settings),
        user_msg,
        tools=STAGE1_TOOLS,
        stage_name="benchmark_stage1_escalation",
        role_kwargs=dict(max_tokens=16000, max_tool_turns=8, thinking="high"),
        context_summary=bundle[:6000],
    )


_SHADOW_SCHEMA = {
    "type": "object",
    "properties": {
        "currency_bias": {"type": "object"},
        "agreement_pct": {"type": "number"},
        "flagged_currencies": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["currency_bias", "agreement_pct", "flagged_currencies"],
}


async def _case_stage1_shadow_check(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    bundle = None
    if not use_fixtures and session:
        try:
            bundle, _, _ = await Stage1DataBundler(session, settings).prefetch_all_data()
        except Exception:
            bundle = None
    if not bundle:
        bundle = get_synthetic_stage1_bundle()
    declared_bias = {}
    if use_fixtures:
        audit_case = get_golden_shadow_check_audit()
        draft = audit_case.get("proposed_draft_brief", {})
        declared_bias = draft.get("currency_bias", {})
    elif session:
        try:
            declared_bias = json.loads((await latest_brief(session)).structured_json or "{}").get("currency_bias", {})
        except Exception:
            pass
    if not declared_bias:
        declared_bias = get_synthetic_fundamental_brief().get("currency_bias", {})
    prompt = (
        "Independently determine USD/EUR/GBP/JPY/AUD/XAU bias "
        "(bullish/bearish/neutral) based SOLELY on the following raw data:\n"
        + bundle
        + f"\n\nThe brief being verified concluded: {json.dumps(declared_bias)}\n"
        "Calculate agreement_pct and list any diverging flagged_currencies."
    )
    return BenchmarkCase(
        "stage1_shadow_check",
        "macro",
        "",
        prompt,
        schema=_SHADOW_SCHEMA,
        role_kwargs=dict(max_tokens=1200, thinking="low"),
        context_summary=bundle[:8000],
    )


async def _case_fundamental_verifier(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    st = {}
    if not use_fixtures and session:
        try:
            brief = await latest_brief(session)
            st = json.loads(brief.structured_json or "{}")
        except Exception:
            pass
    if not st:
        st = get_synthetic_fundamental_brief()
    prompt = f"""Narrative:
{st.get("macro_narrative", "")}

Currency Bias: {json.dumps(st.get("currency_bias", {}))}
Currency Confidence: {json.dumps(st.get("currency_confidence", {}))}
Risk Sentiment: {st.get("risk_sentiment")}
Overall Confidence: {st.get("confidence")}
Invalidation Conditions: {json.dumps(st.get("invalidation_conditions", {}))}
Strongest Counter Thesis: {st.get("strongest_counter_thesis")}"""
    return BenchmarkCase(
        "fundamental_verifier",
        "macro",
        system_prompt=FUNDAMENTAL_VERIFIER_SYSTEM_PROMPT,
        user_prompt=prompt,
        schema=VERIFIER_SCHEMA,
        role_kwargs=dict(max_tokens=1024, thinking="low"),
        context_summary=prompt[:4000],
    )


# =========================================================================
# STAGE 2 (per-asset) -- mode agent, pakai bundle + skill loader ASLI
# =========================================================================
def _stage2_system_prompt(settings, symbol, cot_code, threshold) -> str:
    skills = [
        "smc_ict_playbook",
        "market_dynamics_framework",
        "liquidity_and_macro_edge",
        "risk_management_principles",
        "session_timing_rules",
    ]
    if symbol == "XTIUSD":
        skills.insert(1, "commodity_analysis")
    elif symbol in settings.get("trading", {}).get("24_7_assets", ["BTCUSD"]):
        skills.insert(1, "crypto_analysis")
    if settings.get("trading", {}).get("caveman_mode", False):
        skills.append("caveman_mode")
    body = compose_system_prompt(*skills).replace(
        "{tool_order_guidance}", "Standard data is pre-fetched below; only invoke tools for genuinely missing data."
    )
    static = "You are a professional FX/Gold/commodity/crypto technical analyst using SMC/ICT.\n\n" + body
    dyn = (
        f"\n\n=== CURRENT ANALYSIS TARGET ===\nSymbol: {symbol}\nCOT Code: {cot_code or 'N/A'}\n"
        f"Effective Confluence Threshold: {threshold}/14\n"
        f"Minimum R:R Ratio: {settings.get('trading', {}).get('risk', {}).get('min_rr_ratio', 1.3)}\n"
        "=== END TARGET ===\n"
    )
    return static + dyn


async def _build_stage2_case(session, settings, symbol: str, stage_tag: str) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    cot_code = SYMBOL_TO_COT.get(symbol, "")
    threshold = 8
    if not use_fixtures and session:
        try:
            threshold, _ = await compute_unified_confluence_threshold(session, symbol, settings)
        except Exception:
            threshold = 8
    sysp = _stage2_system_prompt(settings, symbol, cot_code, threshold)
    bundle_text = None
    if not use_fixtures and session:
        try:
            from monika.infrastructure.database.models import FundamentalBrief
            from sqlalchemy import select

            b_row = (
                await session.execute(select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1))
            ).scalar_one_or_none()
            if not b_row:
                import monika.core.primitives.clock as clock

                syn = get_synthetic_fundamental_brief()
                session.add(
                    FundamentalBrief(
                        generated_at=clock.now(),
                        valid_until=clock.now(),
                        content_markdown=syn.get("macro_narrative", ""),
                        structured_json=json.dumps(syn),
                        confidence=0.82,
                        risk_sentiment="selective_risk_off",
                    )
                )
                await session.flush()

            bundled = await Stage2DataBundler(session, settings).fetch_bundle(symbol, cot_code=cot_code or None)
            bundle_text = bundled[0] if isinstance(bundled, tuple) else (bundled or "")
            if "CORE DATA INVALID" in bundle_text or len(bundle_text) < 500:
                bundle_text = None
        except Exception:
            bundle_text = None
    if not bundle_text:
        bundle_text, _ = get_synthetic_stage2_bundle(symbol)
    user_msg = bundle_text + (
        f"\n\nAnalyze {symbol} using pre-fetched data above, then call submit_asset_analysis with your final decision."
    )
    return BenchmarkCase(
        symbol,
        "trade_decision",
        sysp,
        user_msg,
        tools=STAGE2_TOOLS,
        stage_name=f"benchmark_{stage_tag}_{symbol}",
        role_kwargs=dict(max_tokens=12000, max_tool_turns=10, thinking="high"),
        context_summary=bundle_text[:6000],
    )


async def _case_stage2_primary(session, settings, ex):
    return await _build_stage2_case(session, settings, _sym(settings), "stage2_primary")


async def _case_stage2_secondary(session, settings, ex):
    return await _build_stage2_case(session, settings, _sym(settings), "stage2_secondary")


async def _case_stage2_session_trigger(session, settings, ex):
    return await _build_stage2_case(session, settings, _sym(settings), "stage2_session_trigger")


async def _case_stage2_prescreen(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    use_fixtures = settings.get("_use_fixtures", False)
    vix_val = 16.70
    trading_paused = False
    if use_fixtures:
        matrix = get_golden_prescreen_matrix()
        asset_info = matrix.get(symbol, {})
        if asset_info:
            price_val = asset_info.get("price")
            atr_val = asset_info.get("atr_m15")
            adx_val = asset_info.get("adx_h1")
            spread_val = asset_info.get("spread_points")
            regime = asset_info.get("market_regime")
            prompt = (
                f"Prescreen opportunity evaluation for {symbol}:\n"
                f"Price: {price_val}\n"
                f"ATR(14) M15: {atr_val} | ADX(14) H1: {adx_val}\n"
                f"Spread: {spread_val} points | Regime: {regime}\n"
                f"VIX: {vix_val} | Risk Paused: {trading_paused} | Tier-1 News Next 30m: False\n\n"
                "Evaluate if liquidity, volatility, and market conditions meet requirements for full specialist analysis. "
                "Output YES if viable, NO if risk paused, VIX extreme (>28), or market is dead/illiquid."
            )
            schema = {
                "type": "object",
                "properties": {"decision": {"type": "string", "enum": ["YES", "NO"]}, "reason": {"type": "string"}},
                "required": ["decision", "reason"],
            }
            return BenchmarkCase(
                symbol,
                "trade_decision",
                "",
                prompt,
                schema=schema,
                role_kwargs=dict(max_tokens=256, thinking="none"),
                context_summary=prompt,
            )
    if not use_fixtures and ex:
        try:
            vix = await ex.execute("get_vix", {})
            vix_val = (vix.get("latest") or {}).get("close", 16.70)
            risk_state = await ex.execute("get_risk_state", {})
            trading_paused = risk_state.get("trading_paused", False)
        except Exception:
            pass
    prompt = (
        f"Quick trading opportunity check for {symbol}.\n"
        f"VIX: {vix_val}\nRisk paused: {trading_paused}\n"
        "YES if viable for full analysis, NO if risk is paused / VIX is extreme (>28) / dead market."
    )
    schema = {
        "type": "object",
        "properties": {"decision": {"type": "string", "enum": ["YES", "NO"]}, "reason": {"type": "string"}},
        "required": ["decision", "reason"],
    }
    return BenchmarkCase(
        symbol,
        "trade_decision",
        "",
        prompt,
        schema=schema,
        role_kwargs=dict(max_tokens=256, thinking="none"),
        context_summary=prompt,
    )


# =========================================================================
# SPECIALIST (technical / sentiment / macro) -- mode json, pakai prompt & key-map ASLI
# =========================================================================
_SPEC_SCHEMA = {
    "type": "object",
    "properties": {
        "directional_bias": {"type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"]},
        "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "key_evidence": {"type": "array", "items": {"type": "string"}},
        "invalidation": {"type": "string"},
        "analysis": {"type": "string"},
    },
    "required": ["directional_bias", "confidence", "key_evidence", "invalidation", "analysis"],
}


async def _build_specialist_case(session, settings, symbol, role: str) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    cot_code = SYMBOL_TO_COT.get(symbol, "")
    _text, raw = "", {}
    if not use_fixtures and session:
        try:
            bundled = await Stage2DataBundler(session, settings).fetch_bundle(symbol, cot_code=cot_code or None)
            _text, raw = bundled if isinstance(bundled, tuple) else ("", {})
        except Exception:
            pass
    if not raw:
        _, raw = get_synthetic_stage2_bundle(symbol)
    keys = PerAssetStage._SPECIALIST_KEY_MAP.get(role, [])
    view = {k: v for k, v in raw.items() if k in keys and v is not None} if isinstance(raw, dict) else {}
    if not view:
        view = raw
    data_view = json.dumps(view, default=str, indent=2) if view else "(no data available for this domain)"
    currencies = get_base_quote_tags(symbol).split(",")
    base_c = currencies[0].strip() if currencies else "USD"
    quote_c = currencies[1].strip() if len(currencies) > 1 else "USD"
    sysp = _render_specialist_prompt(SPECIALIST_PROMPTS[role], symbol, base_c, quote_c)
    return BenchmarkCase(
        symbol,
        "specialist",
        sysp,
        data_view,
        schema=_SPEC_SCHEMA,
        role_kwargs=dict(max_tokens=1400, thinking="low"),
        context_summary=data_view[:6000],
    )


async def _case_specialist_technical(session, settings, ex):
    return await _build_specialist_case(session, settings, _sym(settings), "technical")


async def _case_specialist_sentiment(session, settings, ex):
    return await _build_specialist_case(session, settings, _sym(settings), "sentiment")


async def _case_specialist_macro(session, settings, ex):
    return await _build_specialist_case(session, settings, _sym(settings), "macro")


# =========================================================================
# DEBATE -- mode custom, pakai fungsi produksi ASLI (client sudah jadi parameter)
# =========================================================================
async def _get_debate_context(session, settings, symbol: str) -> tuple[dict, dict]:
    use_fixtures = settings.get("_use_fixtures", False)
    if not use_fixtures and session:
        try:
            analysis = await pick_asset_analysis(session, symbol)
            ctx = entry_context(analysis)
            fs = await build_fact_sheet(session, analysis.id)
            return ctx, fs
        except Exception:
            pass

    sym = (symbol or "EURUSD").upper()
    prod_fix = load_fixture_json(f"production_smc_snapshot_{sym.lower()}.json")
    price = prod_fix.get(
        "price",
        1.1377 if sym == "EURUSD" else (4260.50 if sym == "XAUUSD" else (158.80 if sym == "USDJPY" else 1.3217)),
    )
    tech = prod_fix.get("analysis", {})

    if sym == "EURUSD":
        decision = "BUY"
        entry_price = 1.1377
        stop_loss = 1.1340
        take_profit = 1.1460
        confluence_score = 11
        confluence_factors = ["BOS_BULLISH", "FVG_REBALANCE", "LONDON_SESSION_MOMENTUM"]
        rationale = "H1 Bullish Displacement with Order Block mitigation at 1.1350 and FVG fill."
        invalidation = "Break below swing low 1.1342"
    elif sym == "XAUUSD":
        decision = "BUY"
        entry_price = 4260.50
        stop_loss = 4248.00
        take_profit = 4290.00
        confluence_score = 12
        confluence_factors = ["ASIAN_LOW_SWEEP", "H1_ORDER_BLOCK", "INSTITUTIONAL_ABSORPTION", "SAFE_HAVEN_FLOW"]
        rationale = "Liquidity sweep below Asian session low ($4,252) followed by sharp bullish displacement and FVG confirmation."
        invalidation = "H1 close below $4,245"
    elif sym == "USDJPY":
        decision = "SELL"
        entry_price = 158.80
        stop_loss = 159.50
        take_profit = 157.20
        confluence_score = 10
        confluence_factors = ["H4_SUPPLY_REJECTION", "BOJ_NORMALIZATION", "BEARISH_DIVERGENCE"]
        rationale = "Rejection at key psychological resistance 159.20 with bearish order flow and BoJ yield pressure."
        invalidation = "H4 close above 159.60"
    elif sym == "GBPUSD":
        decision = "WAIT"
        entry_price = 1.3217
        stop_loss = 1.3180
        take_profit = 1.3320
        confluence_score = 6
        confluence_factors = ["RANGE_BOUND", "TRAPPED_VOLUME"]
        rationale = "Chop consolidation between 1.3190 and 1.3250 with extreme retail longing (83%). No clear edge."
        invalidation = "Break of range boundaries"
    elif sym == "BTCUSD":
        decision = "BUY"
        entry_price = 84200.0
        stop_loss = 83400.0
        take_profit = 85800.0
        confluence_score = 10
        confluence_factors = ["VWAP_RECLAIM", "FUNDING_RESET", "BULLISH_ORDER_FLOW"]
        rationale = "Reclaim of weekly anchored VWAP at $84,000 following weekend leverage flush."
        invalidation = "H1 close below $83,200"
    elif sym == "XTIUSD":
        decision = "BUY"
        entry_price = 95.80
        stop_loss = 94.20
        take_profit = 99.00
        confluence_score = 11
        confluence_factors = ["GEOPOLITICAL_SUPPLY_DISRUPTION", "H1_BOS", "INVENTORY_DRAW"]
        rationale = "Strait of Hormuz transit threat drives acute prompt backwardation and H1 structure breakout."
        invalidation = "Break below $93.80"
    else:
        decision = "BUY"
        entry_price = price
        stop_loss = round(price * 0.995, 5)
        take_profit = round(price * 1.012, 5)
        confluence_score = 9
        confluence_factors = ["STRUCTURE_BREAK", "FVG_FILL"]
        rationale = f"Structural setup on {sym} with favorable risk to reward."
        invalidation = f"Break below {price * 0.995:.5f}"

    ctx = {
        "symbol": sym,
        "decision": decision,
        "rationale": rationale,
        "confluence_score": confluence_score,
        "confluence_factors": confluence_factors,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "invalidation": invalidation,
    }
    fs = {
        "symbol": sym,
        "h1_structure": tech.get(
            "structure", "BULLISH" if decision == "BUY" else ("BEARISH" if decision == "SELL" else "CONSOLIDATION")
        ),
        "m15_structure": "BULLISH" if decision == "BUY" else ("BEARISH" if decision == "SELL" else "CHOP"),
        "key_support": stop_loss,
        "key_resistance": take_profit,
        "macro_bias": "Transatlantic divergence and Hormuz oil shock dictate directional positioning.",
    }
    return ctx, fs


async def _case_debate_bull(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    ctx, fs = await _get_debate_context(session, settings, symbol)
    return BenchmarkCase(
        symbol,
        "debate",
        custom_fn=generate_bull_advocacy,
        custom_args=(symbol, ctx, fs),
        role_kwargs=dict(max_tokens=1500, thinking="medium"),
        context_summary=json.dumps({"context": ctx, "fact_sheet": fs}, default=str)[:5000],
    )


async def _case_debate_bear(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    ctx, fs = await _get_debate_context(session, settings, symbol)
    use_fixtures = settings.get("_use_fixtures", False)
    bull_claim = None
    if not use_fixtures:
        try:
            ref_model = settings.get("_benchmark_reference_model") or "gemini-3.8-flash"
            ref = make_client(ref_model, settings, max_tokens=1500, thinking="medium")
            bull_claim = await generate_bull_advocacy(ref, symbol, ctx, fs)
        except Exception as e:
            logger.debug(f"Reference bull generation fallback to synthetic claims: {e}")
    if not bull_claim:
        bull_claim, _ = get_synthetic_debate_claims(symbol)

    return BenchmarkCase(
        symbol,
        "debate",
        custom_fn=generate_bear_dissent,
        custom_args=(symbol, ctx, bull_claim, fs),
        role_kwargs=dict(max_tokens=1500, thinking="medium"),
        context_summary=json.dumps({"context": ctx, "bull_claim": bull_claim, "fact_sheet": fs}, default=str)[:5000],
    )


async def _case_debate_judge(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    ctx, fs = await _get_debate_context(session, settings, symbol)
    use_fixtures = settings.get("_use_fixtures", False)
    bull_claim, bear_dissent = None, None
    if not use_fixtures:
        try:
            ref_model = settings.get("_benchmark_reference_model") or "gemini-3.8-flash"
            ref = make_client(ref_model, settings, max_tokens=1500, thinking="medium")
            bull_claim = await generate_bull_advocacy(ref, symbol, ctx, fs)
            bear_dissent = await generate_bear_dissent(ref, symbol, ctx, bull_claim, fs)
        except Exception as e:
            logger.debug(f"Reference debate generation fallback to synthetic claims: {e}")
    if not bull_claim or not bear_dissent:
        syn_bull, syn_bear = get_synthetic_debate_claims(symbol)
        bull_claim = bull_claim or syn_bull
        bear_dissent = bear_dissent or syn_bear

    return BenchmarkCase(
        symbol,
        "debate",
        custom_fn=evaluate_debate,
        custom_args=(symbol, ctx, bull_claim, bear_dissent),
        role_kwargs=dict(max_tokens=800, thinking="high"),
        context_summary=json.dumps({"context": ctx, "bull": bull_claim, "bear": bear_dissent}, default=str)[:5000],
    )


_ADJUDICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "adjudication_rule_correctly_applied": {"type": "boolean"},
        "expected_outcome_per_rules": {"type": "string", "enum": ["buy", "sell", "wait", "avoid", "ambiguous"]},
        "mismatch_explanation": {"type": "string"},
        "verdict": {"type": "string", "enum": ["CONFIRM", "FLAG_FOR_REVIEW", "CONTRADICTS_OWN_FRAMEWORK"]},
    },
    "required": ["adjudication_rule_correctly_applied", "expected_outcome_per_rules", "verdict"],
}


async def _case_stage2_adjudicator(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    use_fixtures = settings.get("_use_fixtures", False)
    if use_fixtures:
        adj = get_golden_adjudication_case()
        symbol = adj.get("symbol", "USDJPY")
        biases_raw = adj.get("specialist_biases", {})
        biases = {k: v.get("bias", "NEUTRAL") for k, v in biases_raw.items()}
        confidences = {k: v.get("confidence", "MEDIUM") for k, v in biases_raw.items()}
        decision = "WAIT"
        rationale = f"{adj.get('conflict_description')} | Rules: {adj.get('adjudication_rules')}"
    else:
        biases = {"technical": "BULLISH", "sentiment": "BULLISH", "macro": "NEUTRAL"}
        confidences = {"technical": "HIGH", "sentiment": "MEDIUM", "macro": "LOW"}
        decision = "BUY"
        rationale = "High confidence bullish technical confluence aligns with sentiment."
        if session:
            try:
                analysis = await pick_asset_analysis(session, symbol)
                biases_row = json.loads(analysis.specialist_biases_json) if analysis.specialist_biases_json else {}
                biases = biases_row.get("biases", biases)
                confidences = biases_row.get("confidence", confidences)
                decision = analysis.decision or decision
                rationale = analysis.rationale or rationale
            except Exception:
                pass
    prompt = (
        "Rules: IF Technical=BULLISH AND Macro=BULLISH -> HIGH conf BUY. IF Technical=BEARISH AND "
        "Macro=BEARISH -> HIGH conf SELL. IF Technical vs Macro conflict -> WAIT unless technical "
        "trust_weight>0.8. IF all NEUTRAL/MIXED -> WAIT.\n\n"
        f"Specialist biases {symbol}: {json.dumps(biases)}\n"
        f"Specialist confidence: {json.dumps(confidences)}\n"
        f"Final decision: {decision}\nRationale: {rationale[:1500]}\n\n"
        "Did the final decision correctly follow the adjudication rules based on these specialist biases?"
    )
    return BenchmarkCase(
        symbol,
        "debate",
        "",
        prompt,
        schema=_ADJUDICATION_SCHEMA,
        role_kwargs=dict(max_tokens=800, thinking="medium"),
        context_summary=prompt,
    )


# =========================================================================
# RISK -- risk_gate_* & portfolio_manager_per_trade = mode custom (fungsi ASLI)
# =========================================================================
async def _build_strict_risk_context(session, settings, ex, symbol) -> tuple[dict, object]:
    use_fixtures = settings.get("_use_fixtures", False)
    if not use_fixtures and session:
        try:
            analysis = await pick_asset_analysis(session, symbol)
            ctx = entry_context(analysis)
            risk_state = await ex.execute("get_risk_state", {}) if ex else {}
            open_pos = await ex.execute("get_open_positions", {}) if ex else {}
            entry_price = ctx.get("entry_price")
            rr = None
            if entry_price and analysis.stop_loss and analysis.take_profit:
                sl_d, tp_d = abs(entry_price - analysis.stop_loss), abs(entry_price - analysis.take_profit)
                rr = (tp_d / sl_d) if sl_d else None
            strict_context = {
                "symbol": symbol,
                "decision": ctx["decision"],
                "confluence_score": analysis.confluence_score,
                "priced_in_score": analysis.priced_in_score,
                "rr_ratio": rr,
                "sl_beyond_structure": True,
                "actual_risk_state": {
                    "daily_pnl_pct": risk_state.get("daily_pnl_pct", 0.0),
                    "open_positions": open_pos.get("count", 0),
                    "portfolio_heat_pct": 0.0,
                },
            }
            return strict_context, analysis
        except Exception:
            pass
    strict_context = get_synthetic_risk_context(symbol)
    return strict_context, None


async def _case_risk_gate(session, settings, ex, fn) -> BenchmarkCase:
    symbol = _sym(settings)
    strict_context, _ = await _build_strict_risk_context(session, settings, ex, symbol)
    return BenchmarkCase(
        symbol,
        "risk",
        custom_fn=fn,
        custom_args=(symbol, strict_context),
        role_kwargs=dict(max_tokens=500, thinking="low"),
        context_summary=json.dumps(strict_context, default=str),
    )


async def _case_risk_gate_conservative(session, settings, ex):
    return await _case_risk_gate(session, settings, ex, analyze_risk_conservative_llm)


async def _case_risk_gate_aggressive(session, settings, ex):
    return await _case_risk_gate(session, settings, ex, analyze_risk_aggressive_llm)


async def _case_risk_gate_neutral(session, settings, ex):
    return await _case_risk_gate(session, settings, ex, analyze_risk_neutral_llm)


async def _case_portfolio_manager_per_trade(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    strict_context, _ = await _build_strict_risk_context(session, settings, ex, symbol)
    min_rr = settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.3)
    risk_debate_states = {
        "conservative": analyze_risk_conservative(strict_context),
        "aggressive": analyze_risk_aggressive(strict_context, min_rr_ratio=min_rr),
        "neutral": analyze_risk_neutral(strict_context, min_rr_ratio=min_rr),
    }
    return BenchmarkCase(
        symbol,
        "risk",
        custom_fn=make_portfolio_decision,
        custom_args=(symbol, risk_debate_states, strict_context["actual_risk_state"]),
        role_kwargs=dict(max_tokens=400, thinking="low"),
        context_summary=json.dumps(
            {"risk_debate_states": risk_debate_states, "actual_risk_state": strict_context["actual_risk_state"]},
            default=str,
        ),
    )


_PORTFOLIO_SYNTHESIS_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendation": {"type": "string", "enum": ["execute_all", "reduce"]},
        "keep": {"type": "array", "items": {"type": "string"}},
        "size_adjustments": {"type": "object"},
        "reasoning": {"type": "string"},
    },
    "required": ["recommendation", "keep", "reasoning"],
}


async def _case_portfolio_synthesis(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    rows = []
    if not use_fixtures and session:
        try:
            from sqlalchemy import select as _sel
            from monika.infrastructure.database.models import AssetAnalysis as _AA

            rows = (
                (
                    await session.execute(
                        _sel(_AA).where(_AA.decision.in_(["buy", "sell"])).order_by(_AA.generated_at.desc()).limit(3)
                    )
                )
                .scalars()
                .all()
            )
        except Exception:
            rows = []
    use_fixtures = settings.get("_use_fixtures", False)
    if use_fixtures or len(rows) < 2:
        concurrent = get_golden_concurrent_orders()
        proposals = concurrent.get("simultaneous_order_proposals", [])
        if proposals:
            summaries = [
                f"- {p['symbol']} {p['decision']}: confidence={int(p.get('confidence', 0.8) * 100)}% "
                f"(Entry {p.get('entry_price')}, SL {p.get('stop_loss')}, TP {p.get('take_profit')}, "
                f"Risk ${p.get('risk_amount_usd', 400)} / {p.get('risk_pct', 0.5)}%, Confluence {p.get('confluence_score', 10)}/14)"
                for p in proposals
            ]
        else:
            summaries = [
                "- EURUSD BUY: confidence=82% (Entry 1.1065, SL 1.1035, TP 1.1135, R:R 2.33)",
                "- GBPUSD WAIT: confidence=60% (Entry 1.3020, range bound chop)",
                "- USDJPY SELL: confidence=78% (Entry 143.80, SL 144.60, TP 142.20, R:R 2.10)",
                "- XAUUSD BUY: confidence=85% (Entry 2658.50, SL 2642.00, TP 2695.00, R:R 2.45)",
                "- XTIUSD BUY: confidence=80% (Entry 71.85, SL 70.40, TP 74.50, R:R 2.00)",
            ]
        brief_sentiment = concurrent.get("market_regime", "selective_risk_off")
        brief_confidence = 0.82
        vix_val = 16.70
    else:
        summaries = [f"- {r.symbol} {r.decision.upper()}: confidence={r.confidence:.0%}" for r in rows]
        try:
            brief = await latest_brief(session)
            brief_sentiment = brief.risk_sentiment
            brief_confidence = brief.confidence
        except Exception:
            brief_sentiment = "neutral"
            brief_confidence = 0.70
        try:
            vix = await ex.execute("get_vix", {}) if ex else {}
            vix_val = (vix.get("latest") or {}).get("close", 16.70)
        except Exception:
            vix_val = 16.70
    prompt = (
        f"Portfolio Review: Multiple proposed trades across asset universe.\n\nProposed Trades:\n"
        + "\n".join(summaries)
        + f"\n\nRisk sentiment: {brief_sentiment}\nBrief confidence: {brief_confidence}\n"
        f"VIX: {vix_val}\n\n"
        "Execute ALL of these trades, or REDUCE portfolio exposure due to correlation/risk clustering? Respond with "
        "recommendation, keep[], optional size_adjustments{symbol:multiplier}, and reasoning."
    )
    return BenchmarkCase(
        "portfolio",
        "risk",
        "",
        prompt,
        schema=_PORTFOLIO_SYNTHESIS_SCHEMA,
        role_kwargs=dict(max_tokens=800, thinking="high"),
        context_summary=prompt,
    )


_ADVERSARIAL_SCHEMA = {
    "type": "object",
    "properties": {
        "approve": {"type": "boolean"},
        "overall_quality": {"type": "string", "enum": ["high", "medium", "low"]},
        "strongest_counter_argument": {"type": "string"},
        "hard_block": {"type": "boolean"},
        "hard_block_reason": {"type": "string"},
        "recommend_block": {"type": "boolean"},
        "block_reason": {"type": "string"},
    },
    "required": ["approve", "overall_quality", "strongest_counter_argument", "hard_block", "recommend_block"],
}


async def _case_adversarial_check(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    use_fixtures = settings.get("_use_fixtures", False)
    if use_fixtures:
        adv = get_golden_adversarial_case()
        symbol = adv.get("symbol", symbol)
        decision = "BUY"
        confluence = 11
        priced_in = 3
        invalidation = "Break below 1.1030"
        entry_zone = "1.1055 - 1.1070"
        sl, tp = 1.1035, 1.1135
        traps = "\n".join(f"- {t}" for t in adv.get("hidden_traps", []))
        rationale = f"{adv.get('setup_appearance')}\nContext Hazards:\n{traps}"
    else:
        decision = "BUY"
        confluence = 11
        priced_in = 3
        invalidation = "Break below 1.1030"
        entry_zone = "1.1055 - 1.1070"
        sl, tp = 1.1035, 1.1135
        rationale = "H1 BOS bullish after liquidity sweep below London low. Risk-reward is 2.33."
        if session:
            try:
                analysis = await pick_asset_analysis(session, symbol)
                decision = (analysis.decision or "BUY").upper()
                confluence = analysis.confluence_score
                priced_in = analysis.priced_in_score
                invalidation = analysis.invalidation or invalidation
                entry_zone = str(analysis.entry_zone)
                sl = analysis.stop_loss or sl
                tp = analysis.take_profit or tp
                rationale = analysis.rationale or rationale
            except Exception:
                pass
    prompt = (
        f"Symbol: {symbol}\nDirection: {decision}\n"
        f"Confluence Score: {confluence}/14\nPriced-In Score: {priced_in}/10\n"
        f"Invalidation: {invalidation}\nEntry context: {entry_zone}\n"
        f"SL: {sl}  TP: {tp}\n\n"
        f"Full Rationale:\n{rationale[:3500]}\n\n"
        "Find the STRONGEST argument against this specific trade. hard_block=true only for objective "
        "defects (mathematical error, self-contradiction, missing invalidation). recommend_block=true "
        "for significant non-fatal risk."
    )
    return BenchmarkCase(
        symbol,
        "risk",
        "You are a skeptical risk-desk reviewer conducting a final pre-trade challenge.",
        prompt,
        schema=_ADVERSARIAL_SCHEMA,
        role_kwargs=dict(max_tokens=1200, thinking="medium"),
        context_summary=prompt,
    )


# =========================================================================
# NEWS -- classification / verifier / digest, mode json/text, data live
# =========================================================================
async def _get_news_items_list(session, settings, limit: int = 25):
    use_fixtures = settings.get("_use_fixtures", False)
    bench_limit = settings.get("benchmark", {}).get("news_limit", limit)
    if not use_fixtures and session:
        try:
            items = await recent_news(session, limit=bench_limit)
            if items and len(items) >= min(10, bench_limit):
                return items
        except Exception:
            pass
    raw_fixtures = get_synthetic_news_items()
    from collections import namedtuple

    NewsMock = namedtuple("NewsMock", ["title", "summary", "fetched_at", "impact"])
    items = []
    for item in raw_fixtures[:bench_limit]:
        items.append(
            NewsMock(
                title=item.get("title", ""),
                summary=item.get("summary", ""),
                fetched_at=item.get("fetched_at", "2026-10-02T08:00:00Z"),
                impact=item.get("expected_impact", "HIGH"),
            )
        )
    return items


async def _case_news_classification(session, settings, ex) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=20)
    lines = [
        f"{i + 1}. TITLE: {n.title[:150]}\n   SUMMARY: {(n.summary or '')[:200]}\n   FETCHED: {n.fetched_at}"
        for i, n in enumerate(items)
    ]
    prompt = (
        "Classify market impact of each news item for FX, Commodities (Gold/Oil), and Crypto (Bitcoin) trading "
        "(BREAKING/HIGH/MEDIUM/LOW/NONE), surprise_magnitude, currencies, sentiments.\n\n"
        + NewsDigestProcessor.CLASSIFICATION_FEW_SHOT_EXAMPLES
        + "\n\nITEMS:\n"
        + "\n".join(lines)
    )
    return BenchmarkCase(
        "news_batch",
        "news",
        "",
        prompt,
        schema=NEWS_CLASSIFICATION_SCHEMA,
        role_kwargs=dict(max_tokens=2000, thinking="medium"),
        context_summary=prompt[:5000],
    )


async def _case_news_classification_escalation(session, settings, ex) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=10)
    lines = [
        f"{i + 1}. ORIGINAL_VERDICT=HIGH\n   TITLE: {n.title[:200]}\n   FULL SUMMARY: {(n.summary or '')[:600]}"
        for i, n in enumerate(items)
    ]
    prompt = "Re-evaluate each item from SCRATCH, without bias toward original verdict.\n\nITEMS:\n" + "\n".join(lines)
    return BenchmarkCase(
        "news_escalation",
        "news",
        "",
        prompt,
        schema=NEWS_CLASSIFICATION_SCHEMA,
        role_kwargs=dict(max_tokens=2000, thinking="low"),
        context_summary=prompt[:5000],
    )


async def _case_news_classification_verifier(session, settings, ex) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=15)
    text = "\n\n".join(
        [f"{i + 1}. [current=HIGH] {n.title[:150]}\n   {(n.summary or '')[:200]}" for i, n in enumerate(items)]
    )
    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "verdict": {
                    "type": "string",
                    "enum": ["CONFIRM", "PROMOTE_TO_HIGH", "DEMOTE_TO_MEDIUM", "DEMOTE_TO_LOW"],
                },
                "reason": {"type": "string"},
            },
            "required": ["index", "verdict", "reason"],
        },
    }
    prompt = (
        f"HIGH-vs-MEDIUM calibration editor. For each item decide if current tier is appropriate.\n\nITEMS:\n{text}"
    )
    return BenchmarkCase(
        "news_verifier",
        "news",
        "",
        prompt,
        schema=schema,
        role_kwargs=dict(max_tokens=600, thinking="low"),
        context_summary=prompt[:4000],
    )


async def _case_news_digest(session, settings, ex) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=60)
    text = "\n\n".join([f"[{getattr(n, 'impact', 'HIGH')}] {n.title}\n{(n.summary or '')[:300]}" for n in items])
    prompt = (
        f"Synthesize the following news into a MACRO OVERVIEW for FX, Commodities (Gold/Oil), and Crypto (Bitcoin) traders.\n\nNEWS:\n{text}\n\n"
        "Cover: [MACRO REGIME], [KEY DRIVERS], [WHAT MARKET IS WAITING FOR], "
        "[WHAT IS PRICED IN vs NOT], [CROSS-CURRENCY IMPLICATIONS]. Each claim MUST cite "
        "concrete numbers/levels/dates from the NEWS above."
    )
    return BenchmarkCase(
        "news_digest",
        "news",
        "",
        prompt,
        role_kwargs=dict(max_tokens=3000, thinking="medium"),
        context_summary=text[:5000],
    )


MACRO_OVERVIEW_STATIC_SYSTEM = """You are a senior macro trading analyst. Synthesize the following market news into a cohesive MACRO OVERVIEW for FX, Commodities (Gold/Oil), and Crypto (Bitcoin) traders.

Your output MUST include these 6 sections:

**[MACRO REGIME]**
What is the current macro regime? (Risk-on/Risk-off/Stagflation/Disinflation/Uncertainty). Provide 2-3 sentences explaining the dominant macro theme. What changed from the previous digest?

**[5-DAY THEME EVOLUTION]**
Summarize how dominant themes evolved across the 5-day horizon. Which storylines are escalating (fresh catalysts / shocks) vs which are fading / saturating (narrative exhaustion / de-escalation relief)?

**[KEY DRIVERS]**
What are the 2-3 primary drivers moving markets right now? What is the market REACTING TO vs what is ALREADY PRICED IN?

**[WHAT MARKET IS WAITING FOR]**
List upcoming catalysts or data points the market is currently pricing/positioning for. Include: next major events, analyst consensus expectations, potential surprise scenarios.

**[WHAT IS PRICED IN vs NOT PRICED IN]**
Based on news narrative saturation, identify:
- What themes have been repeated 3+ days -> likely priced in (narrative exhaustion)
- What data/events are upcoming with uncertain outcomes -> potential surprise (fresh catalyst)
- What consensus expectations exist that could be "buy the rumor, sell the news"

**[CROSS-CURRENCY IMPLICATIONS]**
Based on the dominant USD theme, explain the cascading implications:
- If USD strengthens/weakens -> impact on EURUSD, GBPUSD, AUDUSD, USDJPY, XAUUSD
- Note any divergence from historical correlation patterns
- Identify which currency pairs are MOST affected by current news vs. LEAST affected

GROUNDING & ANTI-HALLUCINATION REQUIREMENT (MANDATORY):
1. CITE SPECIFIC NUMBERS ONLY FROM PROVIDED DATA: Every quantitative claim (price levels, %, bps, volumes, $, ¥, date) MUST be grounded directly in the NEWS or MARKET DATA CONTEXT provided in the user prompt.
2. STRICT PROHIBITION ON FABRICATED/PARAMETRIC NUMBERS: NEVER invent numbers, ETF flows, market caps, Treasury sizes, or central bank intervention figures from your pre-training memory. If a figure is not explicitly written in the provided text, DO NOT cite it.
3. QUALITATIVE FALLBACK: If a news driver contains no specific numeric statistics in the raw text, summarize the qualitative event and policy narrative accurately without inventing fake numbers."""


async def _case_news_digest_macro_overview(session, settings, ex) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=35)
    news_text = "\n\n".join([f"[{getattr(n, 'impact', 'HIGH')}] {n.title}\n{(n.summary or '')[:300]}" for n in items])
    macro_5d = (
        "5-DAY MACRO CONTEXT:\n"
        "- US: Non-farm payrolls blew out consensus (+265k vs +175k). Fed Chair Powell reiterates patient plateau at 3.75-4.00%.\n"
        "- Middle East: Naval conflict in Strait of Hormuz escalated, crude spikes to $106.40/bbl.\n"
        "- Eurozone: Flash CPI estimates show persistent energy-driven inflation at 3.2% while Germany factory orders decline -1.4%.\n"
        "- Japan: BoJ signals potential 25 bps rate hike at upcoming meeting, triggering JPY short covering."
    )
    quant_anchors = (
        "QUANTITATIVE ANCHORS:\n"
        "USD Bias: +0.85 (Strong Bullish) | EUR Bias: -0.75 (Strong Bearish) | JPY: +0.75 | XAU: +0.85\n"
        "DXY: 101.48 (+0.42%) | US 10Y Yield: 4.582% (+12.4 bps) | 10Y-2Y Spread: +34.1 bps | Brent Crude: $106.40/bbl"
    )
    user_prompt = f"""{macro_5d}

NEWS (sorted by recency and impact):
<untrusted_news_data>
{news_text}
</untrusted_news_data>

{quant_anchors}

Guidance: Synthesize all dominant drivers into a professional trading desk macro overview."""
    return BenchmarkCase(
        "news_digest_macro_overview",
        "news",
        system_prompt=MACRO_OVERVIEW_STATIC_SYSTEM,
        user_prompt=user_prompt,
        role_kwargs=dict(max_tokens=4000, thinking="high"),
        context_summary=user_prompt[:5000],
    )


async def _case_news_digest_verifier(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    digest_text = ""
    if not use_fixtures and session:
        try:
            digest = await latest_digest(session)
            if digest and digest.digest_text:
                digest_text = digest.digest_text
        except Exception:
            pass
    if not digest_text:
        digest_text = get_synthetic_news_digest()
    if not digest_text:
        digest_text = (
            "[MACRO REGIME] Hawkish rate plateau in US with Fed at 3.75-4.00% vs ECB at 2.50%.\n"
            "[KEY DRIVERS] Hormuz naval escalation pushing crude oil to $106/bbl.\n"
            "[CROSS-CURRENCY IMPLICATIONS] Strong USD tailwinds; EUR under pressure due to energy import drag."
        )
    prompt = (
        "Read this trading news digest and look for glaring contradictions between sections (quote "
        "verbatim both conflicting claims, rate severity material/minor).\n\nDIGEST:\n" + digest_text
    )
    return BenchmarkCase(
        "digest_verifier",
        "news",
        "",
        prompt,
        schema=DIGEST_CONSISTENCY_SCHEMA,
        role_kwargs=dict(max_tokens=800, thinking="low"),
        context_summary=digest_text[:6000],
    )


async def _case_cot_precompute(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    cot_signals = None
    if not use_fixtures and session:
        try:
            cot_signals = await MacroPreprocessor(settings=settings).compute_cot_signals(session)
        except Exception:
            cot_signals = None
    if not cot_signals:
        matrix_data = get_golden_sentiment_matrix()
        assets = matrix_data.get("assets", {})
        if assets:
            cot_signals = {
                sym: {
                    "non_commercial_bias": d.get("cot_institutional", {}).get("non_commercial_bias", "NEUTRAL"),
                    "net_position": d.get("cot_institutional", {}).get("net_position", 0),
                    "retail_contrarian": d.get("retail_fxssi", {}).get("contrarian_signal", "HOLD"),
                    "retail_long_pct": d.get("retail_myfxbook", {}).get("long_pct", 50.0),
                }
                for sym, d in assets.items()
            }
        else:
            cot_signals = {
                "EUR": {
                    "commercial_net": -45000,
                    "non_commercial_net": 38000,
                    "z_score": 1.45,
                    "bias": "BEARISH_EXTREME",
                },
                "USD": {
                    "commercial_net": 62000,
                    "non_commercial_net": -51000,
                    "z_score": -1.82,
                    "bias": "BULLISH_EXTREME",
                },
                "XAU": {
                    "commercial_net": -120000,
                    "non_commercial_net": 115000,
                    "z_score": 2.10,
                    "bias": "OVERBOUGHT_REVERSAL_RISK",
                },
            }
    prompt = (
        f"Computed COT and Institutional Positioning data:\n{json.dumps(cot_signals, indent=2)}\n\n"
        "Produce a 2-3 sentence summary of institutional positioning, highlighting extreme/"
        "overcrowded positions and reversal risk implications. Do not invent new figures."
    )
    return BenchmarkCase(
        "cot",
        "news",
        "You are a concise institutional positioning analyst.",
        prompt,
        role_kwargs=dict(max_tokens=1024, thinking="low"),
        context_summary=prompt,
    )


# =========================================================================
# CHAT -- Telegram assistant, mode chat.
# =========================================================================
_FALLBACK_CHAT_QUESTIONS = [
    "What is the current account status and open positions?",
    "Summarize the latest fundamental brief and its implications for XAUUSD.",
    "What is current VIX and how does it affect our risk sentiment?",
]


async def _build_chat_case(session, settings, ex, idx: int) -> BenchmarkCase:
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
        tools=TELEGRAM_TOOLS,
        history=[],
        role_kwargs=dict(max_tokens=3000, max_tool_turns=8, thinking="medium"),
        context_summary=msg,
    )


async def _case_chat_telegram(session, settings, ex):
    return await _build_chat_case(session, settings, ex, 0)


async def _case_chat_telegram_medium(session, settings, ex):
    return await _build_chat_case(session, settings, ex, 1)


async def _case_chat_telegram_complex(session, settings, ex):
    return await _build_chat_case(session, settings, ex, 2)


# =========================================================================
# REFLECTION
# =========================================================================
async def _case_trade_reflection(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    reflection = None
    enrichment = {}
    if not use_fixtures and session:
        try:
            reflection = await resolved_reflection(session)
            if reflection:
                enrichment = await TradeReflector(settings)._fetch_enrichment_context(session, reflection)
        except Exception:
            reflection = None
    if reflection is None:
        golden_ref = get_golden_trade_reflection()
        raw_pnl = golden_ref.get("outcome_pnl_usd")
        pnl = float(raw_pnl) if raw_pnl is not None else -280.0
        outcome_str = f"Outcome: {'Profitable' if pnl > 0 else 'Loss'} (${pnl:.2f})"
        exit_r = golden_ref.get("exit_reason") or "STOP_LOSS_HIT"
        holding = golden_ref.get("holding_hours") or 3.5
        dec = (golden_ref.get("decision") or "BUY").upper()
        sym = golden_ref.get("symbol") or "EURUSD"
        ref_text = (
            golden_ref.get("reflection_text")
            or "Stop loss placed too tight inside M15 liquidity pool rather than behind H4 structural swing low."
        )
        lesson = (
            golden_ref.get("lesson_crystallized") or "Always buffer Stop Loss beyond higher timeframe liquidity sweeps."
        )
        enrichment_data = {
            "symbol": sym,
            "vix_at_entry": 15.68,
            "vix_at_exit": 24.10,
            "historical_lesson": lesson,
            "post_mortem_notes": ref_text,
        }
        prompt = (
            f"Trade Rationale: {sym} {dec} at 1.1377 targeting 1.1460 based on H1 bullish displacement\n"
            f"Decision: {dec} (Confidence: 0.85)\n"
            f"{outcome_str}\n"
            f"Exit Reason: {exit_r}\n"
            f"Holding: {holding}h\n"
            f"Enrichment Data: {json.dumps(enrichment_data)}"
        )
        return BenchmarkCase(
            "golden_reflection_01",
            "reflection",
            "You are a trading post-mortem analyst. Use ONLY tags from enum. Concrete, not generic.",
            prompt,
            schema=REFLECTION_SCHEMA,
            role_kwargs=dict(max_tokens=1500, thinking="medium"),
            context_summary=prompt[:5000],
        )
    outcome_str = f"Outcome: {'Profitable' if reflection.was_profitable else 'Loss'} (${reflection.outcome_pnl_usd})"
    prompt = (
        f"Trade Rationale: {reflection.rationale_summary}\nDecision: {reflection.decision} "
        f"(Confidence: {reflection.confidence})\n{outcome_str}\nExit Reason: {reflection.exit_reason}\n"
        f"Holding: {reflection.holding_hours}h\nEnrichment Data: {json.dumps(enrichment, default=str)}"
    )
    return BenchmarkCase(
        str(reflection.id),
        "reflection",
        "You are a trading post-mortem analyst. Use ONLY tags from enum. Concrete, not generic.",
        prompt,
        schema=REFLECTION_SCHEMA,
        role_kwargs=dict(max_tokens=1500, thinking="medium"),
        context_summary=prompt[:5000],
    )


_HARNESS_HALLUCINATION_SCHEMA = {
    "type": "object",
    "properties": {
        "contradictions_detected": {"type": "array", "items": {"type": "string"}},
        "is_consistent": {"type": "boolean"},
        "severity": {"type": "string", "enum": ["none", "low", "medium", "high"]},
        "reasoning": {"type": "string"},
    },
    "required": ["contradictions_detected", "is_consistent", "severity", "reasoning"],
}


async def _case_harness_hallucination_detect(session, settings, ex) -> BenchmarkCase:
    contradictory_brief = {
        "currency_bias": {"USD": "bullish", "EUR": "bullish", "AUD": "bullish"},
        "dxy_trend": "strengthening +1.2%",
        "vix": 34.5,
        "risk_sentiment": "risk-on",
        "treasury_10y_yield": "4.65% (rising)",
        "fedwatch_cut_prob": "92%",
    }
    prompt = (
        "Audit this macro brief data for internal contradictions and hallucination risks:\n\n"
        f"{json.dumps(contradictory_brief, indent=2)}\n\n"
        "Identify ALL contradictions (e.g. VIX > 30 vs risk-on, DXY rising vs EUR/AUD bullish simultaneously, "
        "yields rising vs 92% rate cut expectation). Output JSON matching schema."
    )
    return BenchmarkCase(
        "stage1_shadow_check",
        "macro",
        "You are an adversarial quantitative auditor detecting internal contradictions and hallucination risks.",
        prompt,
        schema=_HARNESS_HALLUCINATION_SCHEMA,
        role_kwargs=dict(max_tokens=600, thinking="medium"),
        context_summary=prompt,
    )


async def _case_harness_context_efficiency(session, settings, ex) -> BenchmarkCase:
    from monika.infrastructure.llm.prompt_compressor import PromptBundleCompressor as ContextCompressor

    compressor = ContextCompressor(settings)
    raw_data = "Sample market structure text with extensive descriptions.\n" * 50
    compressed = compressor.compress_stage1_bundle(raw_data, max_tokens=200)
    prompt = (
        f"Analyze this compressed context and extract key market bias:\n\n{compressed}\n\n"
        "Provide a concise 1-paragraph summary with directional bias."
    )
    return BenchmarkCase(
        "news_digest",
        "macro",
        "You are a concise trading analyst.",
        prompt,
        role_kwargs=dict(max_tokens=400, thinking="low"),
        context_summary=prompt,
    )


async def _case_harness_self_correction(session, settings, ex) -> BenchmarkCase:
    prompt = (
        "The previous trading proposal for EURUSD had an invalid Stop Loss:\n"
        "- Proposed decision: BUY\n"
        "- Entry: 1.1000\n"
        "- Stop Loss: 1.1050 (ERROR: Stop loss is ABOVE entry for a BUY order)\n"
        "- Take Profit: 1.1100\n\n"
        "Correct this decision so that SL is strictly BELOW entry (e.g. 1.0950) and R:R >= 1.3."
    )
    return BenchmarkCase(
        "stage2_prescreen",
        "trade_decision",
        "You are a disciplined trade execution validator.",
        prompt,
        schema={
            "type": "object",
            "properties": {
                "decision": {"type": "string"},
                "entry": {"type": "number"},
                "stop_loss": {"type": "number"},
                "take_profit": {"type": "number"},
                "reasoning": {"type": "string"},
            },
            "required": ["decision", "entry", "stop_loss", "take_profit"],
        },
        role_kwargs=dict(max_tokens=400, thinking="low"),
        context_summary=prompt,
    )


# =========================================================================
# SYSTEM ONE & EXPANDED TASK IMPLEMENTATIONS
# =========================================================================


async def _case_jev_news_realtime(session, settings, ex) -> BenchmarkCase:
    fix = load_fixture_json("s1_news_breaking_iran.json")
    state = fix.get(
        "state",
        {
            "title": "BREAKING: Iran IRGC launches cruise missile strike on oil tankers in Strait of Hormuz",
            "summary": "Three commercial crude oil tankers struck in the Strait of Hormuz. Brent crude surges +7.5% to $114/bbl.",
            "open_positions": ["XAUUSD", "EURUSD", "USDJPY"],
        },
    )
    questions = fix.get(
        "questions",
        [
            {
                "name": "market_sentiment",
                "type": "Score",
                "range": [1, 5],
                "description": "1: Risk-off panic, 5: Risk-on euphoria",
            },
            {
                "name": "threatens_positions",
                "type": "Noul",
                "description": "Does headline introduce immediate sharp adverse volatility threat to open positions?",
            },
            {
                "name": "requires_circuit_breaker",
                "type": "Noul",
                "description": "Is this an extreme systemic shock requiring emergency circuit breaker or stop tightening?",
            },
        ],
    )
    expected = fix.get(
        "expected_answers",
        {
            "market_sentiment": 1,
            "threatens_positions": True,
            "threatens_positions_confidence_min": 0.85,
            "requires_circuit_breaker": True,
            "requires_circuit_breaker_confidence_min": 0.90,
        },
    )
    return BenchmarkCase(
        "jev_news_realtime",
        "news",
        user_prompt="Evaluate breaking news shock in real time against open positions.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        fixture_data=fix,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )


async def _case_jev_trigger_validator(session, settings, ex) -> BenchmarkCase:
    fix = load_fixture_json("s1_trigger_stale_eurusd.json")
    state = fix.get(
        "state",
        {
            "symbol": "EURUSD",
            "trigger_type": "breakout_buy",
            "trigger_condition": {"level": 1.1460, "timeframe": "M15"},
            "current_price": 1.1377,
            "age_hours": 18.5,
            "macro_context": "Hawkish Fed hike + DXY break above 101.20 has shifted market structure to bearish H1.",
        },
    )
    questions = fix.get(
        "questions",
        [
            {
                "name": "is_still_valid",
                "type": "Noul",
                "description": "Is this trade trigger still structurally valid and actionable given price action and elapsed time?",
            },
            {
                "name": "invalidation_risk",
                "type": "Score",
                "range": [1, 4],
                "description": "Rate risk that trigger is invalidated: 1: None, 2: Low, 3: Moderate, 4: High",
            },
        ],
    )
    expected = fix.get(
        "expected_answers", {"is_still_valid": False, "is_still_valid_confidence_min": 0.85, "invalidation_risk": 4}
    )
    return BenchmarkCase(
        "jev_trigger_validator",
        "trade_decision",
        user_prompt="Validate trade trigger validity against current price action.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        fixture_data=fix,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )


async def _case_jev_position_guard(session, settings, ex) -> BenchmarkCase:
    fix = load_fixture_json("s1_position_guard_xauusd.json")
    state = fix.get(
        "state",
        {
            "symbol": "XAUUSD",
            "direction": "BUY",
            "entry_price": 4275.00,
            "current_price": 4260.00,
            "sl": 4252.00,
            "tp": 4320.00,
            "volume": 0.5,
            "adverse_move_pips": 1500,
            "current_momentum": "sharp_bearish_impulse",
        },
    )
    questions = fix.get(
        "questions",
        [
            {
                "name": "adverse_momentum",
                "type": "Noul",
                "description": "Is there strong adverse momentum against our BUY position in XAUUSD?",
            },
            {
                "name": "sl_threat_level",
                "type": "Score",
                "range": [1, 4],
                "description": "1: Safe, 2: Normal, 3: Elevated, 4: Critical",
            },
            {"name": "should_tighten_stop", "type": "Noul", "description": "Should trailing stop be tightened?"},
        ],
    )
    expected = fix.get(
        "expected_answers",
        {
            "adverse_momentum": True,
            "adverse_momentum_confidence_min": 0.85,
            "sl_threat_level": 4,
            "should_tighten_stop": True,
        },
    )
    return BenchmarkCase(
        "jev_position_guard",
        "risk",
        user_prompt="Evaluate position risk and adverse momentum in real time.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        fixture_data=fix,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )


async def _case_jev_exit_prescreen(session, settings, ex) -> BenchmarkCase:
    fix = load_fixture_json("s1_exit_prescreen_gbpusd.json")
    state = fix.get(
        "state",
        {
            "symbol": "GBPUSD",
            "direction": "BUY",
            "entry_price": 1.3320,
            "sl": 1.3250,
            "tp": 1.3450,
            "current_price": 1.3217,
            "holding_hours": 14.2,
            "structural_breakdown": True,
            "adverse_move_pips": 103,
        },
    )
    questions = fix.get(
        "questions",
        [
            {
                "name": "thesis_still_valid",
                "type": "Noul",
                "description": "Is original trading thesis still structurally valid?",
            },
            {
                "name": "exit_urgency",
                "type": "Score",
                "range": [1, 5],
                "description": "1: No urgency, 3: Moderate, 5: Critical",
            },
        ],
    )
    expected = fix.get(
        "expected_answers", {"thesis_still_valid": False, "thesis_still_valid_confidence_min": 0.90, "exit_urgency": 4}
    )
    return BenchmarkCase(
        "jev_exit_prescreen",
        "risk",
        user_prompt="Prescreen open position for early thesis invalidation exit.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        fixture_data=fix,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )


async def _case_deep_research(session, settings, ex) -> BenchmarkCase:
    prompt = (
        "Conduct a deep macroeconomic research report analyzing the divergence between US Fed (+25bps hike to 3.75-4.00%) "
        "and ECB (+25bps to 2.50%) against the backdrop of the Middle East energy shock ($106 Brent). "
        "Evaluate the net impact on EUR/USD cross-asset liquidity and institutional positioning."
    )
    return BenchmarkCase(
        "deep_research",
        "macro",
        system_prompt="You are a Senior Quantitative Macro Researcher. Provide in-depth analysis citing specific yields, spreads, and liquidity dynamics.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=8192, thinking="high"),
        context_summary=prompt,
    )


async def _case_report_synthesizer(session, settings, ex) -> BenchmarkCase:
    reports = get_synthetic_session_reports_payload()
    prompt = (
        "Synthesize an end-of-cycle executive portfolio brief across EURUSD, GBPUSD, USDJPY, and XAUUSD based on today's session reports below.\n\n"
        f"{reports}\n\n"
        "Instructions: Synthesize macro cross-currents, evaluate portfolio correlation risks, rank proposed opportunities by expected risk-adjusted edge, "
        "and formulate clear capital allocation recommendations for the upcoming Asian/London rollover."
    )
    return BenchmarkCase(
        "report_synthesizer",
        "macro",
        system_prompt="You are an Executive Trading Desk Synthesizer. Synthesize multi-asset reports into risk allocations, currency exposures, and trade prioritization.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=4096, thinking="medium"),
        context_summary=reports[:6000],
    )


async def _case_context_compaction(session, settings, ex) -> BenchmarkCase:
    raw_payload = get_synthetic_compaction_payload()
    prompt = (
        "Compress the following 12-page economic calendar and news transcript into a strict 400-token high-signal fact sheet.\n\n"
        f"[RAW UNFILTERED DATA TRANSCRIPT]\n{raw_payload}\n\n"
        "Requirements: Retain all exact numerical prints, surprises, bond yields, spreads, and high-impact policy statements without hallucination."
    )
    return BenchmarkCase(
        "context_compaction",
        "macro",
        system_prompt="You are a lossless context compression engine. Retain all exact numbers, rates, and quotes.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=1024, thinking="low"),
        context_summary=raw_payload[:6000],
    )


async def _case_summarizer(session, settings, ex) -> BenchmarkCase:
    transcript = get_synthetic_fomc_transcript_payload()
    prompt = (
        "Provide a 3-bullet progressive summary of the latest FOMC press conference transcript below.\n\n"
        f"[FOMC TRANSCRIPT]\n{transcript}\n\n"
        "Requirements:\n"
        "- Bullet 1: Core policy decision and economic assessment (labor & inflation).\n"
        "- Bullet 2: Reaction function to energy shock and guidance on rate trajectory.\n"
        "- Bullet 3: Actionable takeaway for FX and rate traders."
    )
    return BenchmarkCase(
        "summarizer",
        "macro",
        system_prompt="You are an ultra-concise financial summarizer. Extract monetary policy posture, data dependencies, and risk shifts.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=512, thinking="low"),
        context_summary=transcript[:4000],
    )


async def _case_macro_analyst(session, settings, ex) -> BenchmarkCase:
    anomaly_data = get_synthetic_macro_anomaly_payload()
    prompt = (
        "Investigate the real-yield divergence anomaly between US TIPS and German Bunds during the recent crude oil spike based on the market data below.\n\n"
        f"{anomaly_data}\n\n"
        "Provide in-depth quantitative analysis explaining causal mechanisms, transmission channels to EUR/USD, terms-of-trade degradation, and central bank reaction functions."
    )
    return BenchmarkCase(
        "macro_analyst",
        "macro",
        system_prompt="You are a Macro Anomaly Specialist. Analyze real yield divergence, terms-of-trade degradation, and central bank reaction functions.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=4096, thinking="high"),
        context_summary=anomaly_data[:4000],
    )


async def _case_sentiment_analyst(session, settings, ex) -> BenchmarkCase:
    feed = get_synthetic_sentiment_feed_payload()
    prompt = (
        "Extract directional sentiment, positioning bias, and fear/greed score from the institutional commentary and positioning feed below.\n\n"
        f"{feed}\n\n"
        "Output structured JSON matching schema."
    )
    return BenchmarkCase(
        "sentiment_analyst",
        "specialist",
        system_prompt="You are a Sentiment and Positioning Specialist analyzing institutional flows, COT positioning, and retail sentiment extremes.",
        user_prompt=prompt,
        schema={
            "type": "object",
            "properties": {
                "sentiment_score": {"type": "number"},
                "bias": {"type": "string"},
                "institutional_positioning": {"type": "string"},
                "retail_crowd_risk": {"type": "string"},
            },
            "required": ["sentiment_score", "bias", "institutional_positioning"],
        },
        role_kwargs=dict(max_tokens=1024, thinking="low"),
        context_summary=feed[:4000],
    )


async def _case_risk_gate_task(session, settings, ex) -> BenchmarkCase:
    risk_state = get_golden_risk_state("baseline")
    acct = risk_state.get("account_state", {})
    prop = risk_state.get("proposed_trade", {})
    prompt = (
        f"Subagent Risk Gate Compliance Audit:\n"
        f"Account Equity: ${acct.get('equity', 76849.91):,.2f} | Free Margin: ${acct.get('margin_free', 75200.0):,.2f}\n"
        f"Daily Realized PnL: ${acct.get('daily_realized_pnl', -350.0):,.2f} | Daily Drawdown: {acct.get('daily_drawdown_pct', 1.2)}%\n"
        f"Open Positions: {acct.get('open_positions_count', 2)} | Max Daily Loss Limit: ${acct.get('max_daily_loss_limit_usd', 1500.0):,.2f}\n\n"
        f"Proposed Order:\n"
        f"Symbol: {prop.get('symbol', 'EURUSD')} {prop.get('direction', 'BUY')} | Lots: {prop.get('calculated_lots', 1.5)}\n"
        f"Entry: {prop.get('entry_price', 1.1065)} | SL: {prop.get('stop_loss', 1.1035)} | TP: {prop.get('take_profit', 1.1135)}\n"
        f"Risk Amount: ${prop.get('risk_amount_usd', 450.0):,.2f} | R:R: {prop.get('risk_reward_ratio', 2.33)}\n\n"
        "Evaluate compliance with portfolio risk gates, capital preservation rules, and maximum loss limits."
    )
    return BenchmarkCase(
        "risk_gate",
        "risk",
        system_prompt="You are a Subagent Risk Gate Auditor.",
        user_prompt=prompt,
        schema={
            "type": "object",
            "properties": {
                "approved": {"type": "boolean"},
                "veto_reason": {"type": "string"},
                "multiplier": {"type": "number"},
            },
            "required": ["approved", "multiplier"],
        },
        role_kwargs=dict(max_tokens=1024, thinking="medium"),
        context_summary=prompt,
    )


# =========================================================================
# ADDITIONAL 8+ TASK ROLES MAPPED DIRECTLY FROM settings.yaml
# =========================================================================


async def _case_jev_telegram_intent(session, settings, ex) -> BenchmarkCase:
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


async def _case_chat_interactive_fast(session, settings, ex) -> BenchmarkCase:
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


async def _case_chat_interactive_balanced(session, settings, ex) -> BenchmarkCase:
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


async def _case_chat_interactive_reasoning(session, settings, ex) -> BenchmarkCase:
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


async def _case_chat_interactive_pro(session, settings, ex) -> BenchmarkCase:
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


async def _case_pattern_context_verifier(session, settings, ex) -> BenchmarkCase:
    pattern_data = get_golden_pattern_case()
    sym = pattern_data.get("symbol", "EURUSD")
    cur = pattern_data.get("current_conditions", {})
    hist = pattern_data.get("historical_match", {})
    prompt = f"""CURRENT CONDITIONS ({cur.get("date", "2026-10-01")}):
{cur.get("summary", "Fed hawkish at 3.75-4.00%, Middle East crude supply risk, DXY at 101.48, VIX at 16.7.")}

HISTORICAL MATCH ({hist.get("match_date", "2024-04-12")}, Symbol: {sym}):
- Pattern Shape Similarity: {hist.get("shape_similarity_pct", 84.5)}%
- Historical Volatility Level: {hist.get("hist_vix", 14.8)} ({hist.get("hist_vix_cat", "NORMAL")})
- Historical USD Trend: {hist.get("hist_dxy_trend", "BULLISH_REBOUND")}
- Historical Asset Position: {hist.get("hist_asset_trend", "BEARISH_CONTINUATION_BREAKDOWN")}
- Recorded Chronicle Context: {hist.get("recorded_chronicle", "")}

INSTRUCTIONS:
Evaluate whether macro drivers are comparable and output structured ContextVerdict JSON."""
    schema = {
        "type": "object",
        "properties": {
            "relevance": {"type": "string", "enum": ["high", "medium", "low"]},
            "historical_context_summary": {"type": "string"},
            "is_macro_driver_similar": {"type": "boolean"},
            "adjustment_factor": {"type": "number"},
            "verdict_reason": {"type": "string"},
        },
        "required": ["relevance", "is_macro_driver_similar", "adjustment_factor", "verdict_reason"],
    }
    return BenchmarkCase(
        "pattern_context_verifier",
        "specialist",
        system_prompt="You are Monika's Principal Macroeconomic Historian.",
        user_prompt=prompt,
        schema=schema,
        role_kwargs=dict(max_tokens=1024, thinking="low"),
        context_summary=prompt,
    )


async def _case_jev_confluence_gate(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    confl = get_golden_jev_confluence() if use_fixtures else {}
    state = {
        "symbol": confl.get("symbol", "EURUSD"),
        "proposed_decision": "BUY",
        "confluence_score": confl.get("calculated_score", 8.4),
        "confluence_threshold": confl.get("threshold", 7.0),
        "factors": ["BOS_BULLISH", "FVG_DEMAND_BOUNCE", "H4_TREND_ALIGNED", "YIELD_SPREAD_SUPPORT"],
        "discrepancies": 0,
    }
    questions = [
        {
            "name": "pass_confluence",
            "type": "Noul",
            "description": "Does the trade proposal satisfy the required confluence threshold?",
        },
        {
            "name": "confluence_quality",
            "type": "Score",
            "range": [1, 5],
            "description": "1: Marginal, 3: Robust, 5: Pristine High-Conviction",
        },
    ]
    expected = {"pass_confluence": True, "pass_confluence_confidence_min": 0.90, "confluence_quality": 4}
    return BenchmarkCase(
        "jev_confluence_gate",
        "trade_decision",
        user_prompt="Evaluate trade confluence factors against structural gating threshold.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )


async def _case_jev_session_timing_gate(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    t_state = get_golden_jev_timing() if use_fixtures else {}
    state = {
        "current_utc_hour": t_state.get("current_utc_hour", 14),
        "active_sessions": t_state.get("active_sessions", ["London", "New York"]),
        "is_overlap": t_state.get("is_overlap", True),
        "symbol": t_state.get("symbol", "EURUSD"),
        "near_tier1_event": t_state.get("near_tier1_event", False),
        "minutes_to_next_tier1": t_state.get("minutes_to_next_tier1", 180),
    }
    questions = [
        {
            "name": "timing_allowed",
            "type": "Noul",
            "description": "Is current session timing permissible for fresh order execution?",
        },
        {
            "name": "liquidity_tier",
            "type": "Score",
            "range": [1, 4],
            "description": "1: Illiquid off-peak, 2: Moderate Asian, 3: High single-session, 4: Peak London-NY overlap",
        },
    ]
    expected = {"timing_allowed": True, "timing_allowed_confidence_min": 0.95, "liquidity_tier": 4}
    return BenchmarkCase(
        "jev_session_timing_gate",
        "risk",
        user_prompt="Verify session timing and liquidity constraints before execution.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )


async def _case_jev_debate_evaluator(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    clash = get_golden_jev_debate_clash() if use_fixtures else {}
    state = {
        "symbol": clash.get("symbol", "EURUSD"),
        "bull_score": clash.get("bull_score", 8),
        "bear_score": clash.get("bear_score", 5),
        "bull_unmitigated_invalidation": clash.get("bull_unmitigated_invalidation", False),
        "bear_unmitigated_invalidation": clash.get("bear_unmitigated_invalidation", True),
        "bear_invalidation_detail": clash.get(
            "bear_invalidation_detail", "D1 close broke above 1.1050 invalidating bearish order block."
        ),
    }
    questions = [
        {
            "name": "winner",
            "type": "Choice",
            "options": ["bull", "bear", "deadlock"],
            "description": "Which debate persona holds the structurally superior thesis?",
        },
        {
            "name": "consensus_conviction",
            "type": "Score",
            "range": [1, 5],
            "description": "1: Ambiguous deadlock, 3: Clear edge, 5: Decisive refutation",
        },
    ]
    expected = {
        "winner": clash.get("expected_winner", "bull"),
        "consensus_conviction": clash.get("consensus_conviction", 4),
    }
    return BenchmarkCase(
        "jev_debate_evaluator",
        "debate",
        user_prompt="Arbitrate debate clash and determine winner based on structural refutations.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0),
    )


async def _case_voice_transcription(session, settings, ex) -> BenchmarkCase:
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


# =========================================================================
# REGISTRY -- 53 task roles dipetakan penuh ke settings.yaml
# =========================================================================
TASKS: dict[str, TaskSpec] = {
    # 1. Macro Analysis & Verification
    "stage1_fundamental": TaskSpec("stage1_fundamental", "macro", "agent", _case_stage1_fundamental),
    "stage1_escalation": TaskSpec("stage1_escalation", "macro", "agent", _case_stage1_escalation),
    "stage1_shadow_check": TaskSpec("stage1_shadow_check", "macro", "json", _case_stage1_shadow_check),
    "fundamental_verifier": TaskSpec("fundamental_verifier", "macro", "json", _case_fundamental_verifier),
    "macro_analyst": TaskSpec("macro_analyst", "macro", "agent", _case_macro_analyst),
    "deep_research": TaskSpec("deep_research", "macro", "agent", _case_deep_research),
    "report_synthesizer": TaskSpec("report_synthesizer", "macro", "text", _case_report_synthesizer),
    "context_compaction": TaskSpec("context_compaction", "macro", "text", _case_context_compaction),
    "summarizer": TaskSpec("summarizer", "macro", "text", _case_summarizer),
    # 2. Stage 2 Per-Asset Decisions
    "stage2_per_asset_primary": TaskSpec("stage2_per_asset_primary", "trade_decision", "agent", _case_stage2_primary),
    "stage2_per_asset_secondary": TaskSpec(
        "stage2_per_asset_secondary", "trade_decision", "agent", _case_stage2_secondary
    ),
    "stage2_session_trigger": TaskSpec(
        "stage2_session_trigger", "trade_decision", "agent", _case_stage2_session_trigger
    ),
    "stage2_prescreen": TaskSpec("stage2_prescreen", "trade_decision", "json", _case_stage2_prescreen),
    # 3. Domain Specialists
    "specialist_technical": TaskSpec("specialist_technical", "specialist", "json", _case_specialist_technical),
    "specialist_sentiment": TaskSpec("specialist_sentiment", "specialist", "json", _case_specialist_sentiment),
    "specialist_macro": TaskSpec("specialist_macro", "specialist", "json", _case_specialist_macro),
    "sentiment_analyst": TaskSpec("sentiment_analyst", "specialist", "json", _case_sentiment_analyst),
    "pattern_context_verifier": TaskSpec(
        "pattern_context_verifier", "specialist", "json", _case_pattern_context_verifier
    ),
    # 4. Dialectical Debate & Arbitration
    "debate_bull": TaskSpec("debate_bull", "debate", "custom", _case_debate_bull),
    "debate_bear": TaskSpec("debate_bear", "debate", "custom", _case_debate_bear),
    "debate_judge": TaskSpec("debate_judge", "debate", "custom", _case_debate_judge),
    "stage2_adjudicator": TaskSpec("stage2_adjudicator", "debate", "json", _case_stage2_adjudicator),
    "jev_debate_evaluator": TaskSpec("jev_debate_evaluator", "debate", "system_one", _case_jev_debate_evaluator),
    # 5. Risk Fortress & Portfolio Management
    "risk_gate": TaskSpec("risk_gate", "risk", "json", _case_risk_gate_task),
    "risk_gate_conservative": TaskSpec("risk_gate_conservative", "risk", "custom", _case_risk_gate_conservative),
    "risk_gate_aggressive": TaskSpec("risk_gate_aggressive", "risk", "custom", _case_risk_gate_aggressive),
    "risk_gate_neutral": TaskSpec("risk_gate_neutral", "risk", "custom", _case_risk_gate_neutral),
    "portfolio_manager_per_trade": TaskSpec(
        "portfolio_manager_per_trade", "risk", "custom", _case_portfolio_manager_per_trade
    ),
    "portfolio_synthesis": TaskSpec("portfolio_synthesis", "risk", "json", _case_portfolio_synthesis),
    "adversarial_check": TaskSpec("adversarial_check", "risk", "json", _case_adversarial_check),
    "trade_reflection": TaskSpec("trade_reflection", "reflection", "json", _case_trade_reflection),
    # 6. News Ingestion & Processing
    "news_classification": TaskSpec("news_classification", "news", "json", _case_news_classification),
    "news_classification_escalation": TaskSpec(
        "news_classification_escalation", "news", "json", _case_news_classification_escalation
    ),
    "news_classification_verifier": TaskSpec(
        "news_classification_verifier", "news", "json", _case_news_classification_verifier
    ),
    "news_digest": TaskSpec("news_digest", "news", "text", _case_news_digest),
    "news_digest_macro_overview": TaskSpec(
        "news_digest_macro_overview", "news", "text", _case_news_digest_macro_overview
    ),
    "news_digest_verifier": TaskSpec("news_digest_verifier", "news", "json", _case_news_digest_verifier),
    "cot_precompute": TaskSpec("cot_precompute", "news", "text", _case_cot_precompute),
    # 7. System One High-Speed Reflexes
    "jev_news_realtime": TaskSpec("jev_news_realtime", "news", "system_one", _case_jev_news_realtime),
    "jev_trigger_validator": TaskSpec(
        "jev_trigger_validator", "trade_decision", "system_one", _case_jev_trigger_validator
    ),
    "jev_position_guard": TaskSpec("jev_position_guard", "risk", "system_one", _case_jev_position_guard),
    "jev_exit_prescreen": TaskSpec("jev_exit_prescreen", "risk", "system_one", _case_jev_exit_prescreen),
    "jev_confluence_gate": TaskSpec("jev_confluence_gate", "trade_decision", "system_one", _case_jev_confluence_gate),
    "jev_session_timing_gate": TaskSpec("jev_session_timing_gate", "risk", "system_one", _case_jev_session_timing_gate),
    "jev_telegram_intent": TaskSpec("jev_telegram_intent", "chat", "json", _case_jev_telegram_intent),
    # 8. Interactive Assistants & Omnichannel
    "chat_telegram": TaskSpec("chat_telegram", "chat", "chat", _case_chat_telegram),
    "chat_telegram_medium": TaskSpec("chat_telegram_medium", "chat", "chat", _case_chat_telegram_medium),
    "chat_telegram_complex": TaskSpec("chat_telegram_complex", "chat", "chat", _case_chat_telegram_complex),
    "chat_interactive_fast": TaskSpec("chat_interactive_fast", "chat", "chat", _case_chat_interactive_fast),
    "chat_interactive_balanced": TaskSpec("chat_interactive_balanced", "chat", "chat", _case_chat_interactive_balanced),
    "chat_interactive_reasoning": TaskSpec(
        "chat_interactive_reasoning", "chat", "chat", _case_chat_interactive_reasoning
    ),
    "chat_interactive_pro": TaskSpec("chat_interactive_pro", "chat", "chat", _case_chat_interactive_pro),
    "voice_transcription": TaskSpec("voice_transcription", "chat", "json", _case_voice_transcription),
    # 9. Harness Auditing Probes
    "harness_hallucination_detect": TaskSpec(
        "harness_hallucination_detect", "macro", "json", _case_harness_hallucination_detect
    ),
    "harness_context_efficiency": TaskSpec(
        "harness_context_efficiency", "macro", "text", _case_harness_context_efficiency
    ),
    "harness_self_correction": TaskSpec(
        "harness_self_correction", "trade_decision", "json", _case_harness_self_correction
    ),
}
