import json
from dataclasses import dataclass, field
from typing import Callable, Optional, Awaitable, Any
from sqlalchemy.ext.asyncio import AsyncSession

from skills.loader import compose_system_prompt
from analysis.prefetch.stage1_prefetcher import Stage1DataBundler
from analysis.prefetch.stage2_prefetcher import Stage2DataBundler
from analysis.stages.fundamental_stage import USER_MESSAGE as STAGE1_USER_MESSAGE_TEXT
from analysis.stages.per_asset_stage import SPECIALIST_PROMPTS, SYMBOL_TO_COT, _render_specialist_prompt, PerAssetStage
from analysis.schemas.schemas import get_tool_schema, SubmitFundamentalBriefSchema
from analysis.tools.tools_definitions import STAGE1_TOOLS, STAGE2_TOOLS, TELEGRAM_TOOLS
from analysis.calculators.unified_threshold_calculator import compute_unified_confluence_threshold
from analysis.debate.fact_sheet import build_fact_sheet
from analysis.debate.bull_analyst import generate_bull_advocacy
from analysis.debate.bear_analyst import generate_bear_dissent
from analysis.debate.investment_judge import evaluate_debate
from analysis.debate.conservative_risk_llm import analyze_risk_conservative_llm
from analysis.debate.aggressive_risk_llm import analyze_risk_aggressive_llm
from analysis.debate.neutral_risk_llm import analyze_risk_neutral_llm
from analysis.debate.portfolio_manager import make_portfolio_decision
from analysis.debate.deterministic_risk import analyze_risk_conservative, analyze_risk_aggressive, analyze_risk_neutral
from analysis.validators.fundamental_verifier import VERIFIER_SCHEMA
from analysis.memory.reflector import REFLECTION_SCHEMA, TradeReflector
from analysis.prefetch.news_digest import NEWS_CLASSIFICATION_SCHEMA, DIGEST_CONSISTENCY_SCHEMA, NewsDigestProcessor
from analysis.prefetch.macro_preprocessor import MacroPreprocessor
from utils.protocol.context_coherence import get_base_quote_tags

from .db_access import pick_asset_analysis, latest_brief, latest_digest, recent_news, resolved_reflection, latest_user_message, entry_context, BenchmarkToolExecutor
from .invoker import make_client
from .fixture_loader import (
    load_fixture_json,
    get_synthetic_market_snapshot,
    get_synthetic_stage1_bundle,
    get_synthetic_stage2_bundle,
    get_synthetic_fundamental_brief,
    get_synthetic_news_items,
    get_synthetic_risk_context,
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
    skills = ["macro_analysis_framework", "market_dynamics_framework", "performance_notes", "fundamental_performance_notes"]
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
    return BenchmarkCase("stage1", "macro", _stage1_system_prompt(settings), user_msg,
                          tools=STAGE1_TOOLS, stage_name="benchmark_stage1_fundamental",
                          role_kwargs=dict(max_tokens=12000, max_tool_turns=8, thinking="high"),
                          context_summary=bundle)


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
    if not use_fixtures and session:
        try:
            prior_json = (await latest_brief(session)).structured_json or "{}"
        except Exception:
            pass
    if prior_json == "{}":
        prior_json = json.dumps(get_synthetic_fundamental_brief())
    user_msg = (STAGE1_USER_MESSAGE_TEXT + f"\n\n[PRE-FETCHED DATA]\n{bundle}"
                "\n\n--- ESCALATION REQUIRED ---\nBrief sebelumnya berkonfidensi rendah. Evaluasi "
                f"ulang dengan sangat teliti, selesaikan semua ambiguitas secara eksplisit.\n"
                f"BRIEF SEBELUMNYA:\n{prior_json}")
    return BenchmarkCase("stage1_escalation", "macro", _stage1_system_prompt(settings), user_msg,
                          tools=STAGE1_TOOLS, stage_name="benchmark_stage1_escalation",
                          role_kwargs=dict(max_tokens=16000, max_tool_turns=8, thinking="high"),
                          context_summary=bundle[:6000])


_SHADOW_SCHEMA = {"type": "object", "properties": {
    "currency_bias": {"type": "object"}, "agreement_pct": {"type": "number"},
    "flagged_currencies": {"type": "array", "items": {"type": "string"}}},
    "required": ["currency_bias", "agreement_pct", "flagged_currencies"]}


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
    if not use_fixtures and session:
        try:
            declared_bias = json.loads((await latest_brief(session)).structured_json or "{}").get("currency_bias", {})
        except Exception:
            pass
    if not declared_bias:
        declared_bias = get_synthetic_fundamental_brief().get("currency_bias", {})
    prompt = ("Independen dari brief manapun, tentukan bias USD/EUR/GBP/JPY/AUD/XAU "
              "(bullish/bearish/neutral) HANYA dari data mentah berikut:\n" + bundle[:6000] +
              f"\n\nBrief yang sedang diverifikasi menyimpulkan: {json.dumps(declared_bias)}\n"
              "Hitung agreement_pct dan sebutkan flagged_currencies yang berbeda.")
    return BenchmarkCase("stage1_shadow_check", "macro", "", prompt, schema=_SHADOW_SCHEMA,
                          role_kwargs=dict(max_tokens=800, thinking="low"), context_summary=bundle[:4000])


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
    prompt = ("Review brief trading makro ini untuk KONSISTENSI INTERNAL SAJA:\n\n"
              f"Narrative:\n{st.get('macro_narrative','')[:2500]}\n\n"
              f"Currency Bias: {json.dumps(st.get('currency_bias', {}))}\n"
              f"Currency Confidence: {json.dumps(st.get('currency_confidence', {}))}\n"
              f"Risk Sentiment: {st.get('risk_sentiment')}\nOverall Confidence: {st.get('confidence')}\n"
              f"Strongest Counter Thesis: {st.get('strongest_counter_thesis')}\n\n"
              "Cek: (1) nada narasi cocok currency_bias? (2) risk_sentiment konsisten dengan bias? "
              "(3) confidence berdasar? (4) counter thesis substantif & falsifiable? Jangan menilai "
              "apakah CALL makronya sendiri benar.")
    return BenchmarkCase("fundamental_verifier", "macro", "", prompt, schema=VERIFIER_SCHEMA,
                          role_kwargs=dict(max_tokens=1024, thinking="low"), context_summary=json.dumps(st)[:4000])


# =========================================================================
# STAGE 2 (per-asset) -- mode agent, pakai bundle + skill loader ASLI
# =========================================================================
def _stage2_system_prompt(settings, symbol, cot_code, threshold) -> str:
    skills = ["smc_ict_playbook", "market_dynamics_framework", "liquidity_and_macro_edge",
              "risk_management_principles", "session_timing_rules"]
    if symbol == "XTIUSD":
        skills.insert(1, "commodity_analysis")
    elif symbol in settings.get("trading", {}).get("24_7_assets", ["BTCUSD"]):
        skills.insert(1, "crypto_analysis")
    if settings.get("trading", {}).get("caveman_mode", False):
        skills.append("caveman_mode")
    body = compose_system_prompt(*skills).replace(
        "{tool_order_guidance}",
        "Data standar sudah di-prefetch di bawah; hanya panggil tool untuk data yang benar-benar hilang.")
    static = ("You are a professional FX/Gold/commodity/crypto technical analyst using SMC/ICT.\n\n" + body)
    dyn = (f"\n\n=== CURRENT ANALYSIS TARGET ===\nSymbol: {symbol}\nCOT Code: {cot_code or 'N/A'}\n"
           f"Effective Confluence Threshold: {threshold}/14\n"
           f"Minimum R:R Ratio: {settings.get('trading',{}).get('risk',{}).get('min_rr_ratio', 1.3)}\n"
           "=== END TARGET ===\n")
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
            bundled = await Stage2DataBundler(session, settings).fetch_bundle(symbol, cot_code=cot_code or None)
            bundle_text = bundled[0] if isinstance(bundled, tuple) else (bundled or "")
        except Exception:
            bundle_text = None
    if not bundle_text:
        bundle_text, _ = get_synthetic_stage2_bundle(symbol)
    user_msg = bundle_text + (f"\n\nAnalisis {symbol} pakai data pre-fetched di atas, lalu panggil "
                               "submit_asset_analysis dengan keputusan final.")
    return BenchmarkCase(symbol, "trade_decision", sysp, user_msg, tools=STAGE2_TOOLS,
                          stage_name=f"benchmark_{stage_tag}_{symbol}",
                          role_kwargs=dict(max_tokens=12000, max_tool_turns=10, thinking="high"),
                          context_summary=bundle_text[:6000])


async def _case_stage2_primary(session, settings, ex): return await _build_stage2_case(session, settings, _sym(settings), "stage2_primary")
async def _case_stage2_secondary(session, settings, ex): return await _build_stage2_case(session, settings, _sym(settings), "stage2_secondary")
async def _case_stage2_session_trigger(session, settings, ex): return await _build_stage2_case(session, settings, _sym(settings), "stage2_session_trigger")


async def _case_stage2_prescreen(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    use_fixtures = settings.get("_use_fixtures", False)
    vix_val = 15.68
    trading_paused = False
    if not use_fixtures and ex:
        try:
            vix = await ex.execute("get_vix", {})
            vix_val = (vix.get("latest") or {}).get("close", 15.68)
            risk_state = await ex.execute("get_risk_state", {})
            trading_paused = risk_state.get("trading_paused", False)
        except Exception:
            pass
    prompt = (f"Quick trading opportunity check untuk {symbol}.\n"
              f"VIX: {vix_val}\nRisk paused: {trading_paused}\n"
              "YES kalau layak analisis penuh, NO kalau risk paused / VIX ekstrem(>28) / pasar mati.")
    schema = {"type": "object", "properties": {"decision": {"type": "string", "enum": ["YES", "NO"]},
              "reason": {"type": "string"}}, "required": ["decision", "reason"]}
    return BenchmarkCase(symbol, "trade_decision", "", prompt, schema=schema,
                          role_kwargs=dict(max_tokens=256, thinking="none"), context_summary=prompt)


# =========================================================================
# SPECIALIST (technical / sentiment / macro) -- mode json, pakai prompt & key-map ASLI
# =========================================================================
_SPEC_SCHEMA = {"type": "object", "properties": {
    "directional_bias": {"type": "string", "enum": ["BULLISH", "BEARISH", "NEUTRAL"]},
    "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
    "key_evidence": {"type": "array", "items": {"type": "string"}},
    "invalidation": {"type": "string"}, "analysis": {"type": "string"}},
    "required": ["directional_bias", "confidence", "key_evidence", "invalidation", "analysis"]}


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
    data_view = json.dumps(view, default=str)[:6000] if view else "(tidak ada data untuk domain ini)"
    currencies = get_base_quote_tags(symbol).split(",")
    base_c = currencies[0].strip() if currencies else "USD"
    quote_c = currencies[1].strip() if len(currencies) > 1 else "USD"
    sysp = _render_specialist_prompt(SPECIALIST_PROMPTS[role], symbol, base_c, quote_c)
    return BenchmarkCase(symbol, "specialist", sysp, data_view, schema=_SPEC_SCHEMA,
                          role_kwargs=dict(max_tokens=1400, thinking="low"), context_summary=data_view)


async def _case_specialist_technical(session, settings, ex): return await _build_specialist_case(session, settings, _sym(settings), "technical")
async def _case_specialist_sentiment(session, settings, ex): return await _build_specialist_case(session, settings, _sym(settings), "sentiment")
async def _case_specialist_macro(session, settings, ex): return await _build_specialist_case(session, settings, _sym(settings), "macro")


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
    ctx = {
        "decision": "BUY",
        "rationale": "H1 Bullish Displacement with Order Block mitigation at 1.1350 and FVG fill.",
        "confluence_score": 11,
        "confluence_factors": ["BOS_BULLISH", "FVG_REBALANCE", "LONDON_SESSION_MOMENTUM"],
        "entry_price": 1.1377,
        "stop_loss": 1.1340,
        "take_profit": 1.1460,
        "invalidation": "Break below swing low 1.1342"
    }
    fs = {
        "symbol": symbol,
        "h1_structure": "BULLISH",
        "m15_structure": "BULLISH",
        "key_support": 1.1350,
        "key_resistance": 1.1460,
        "macro_bias": "EUR weak vs USD strong, but technical setup offers high R:R"
    }
    return ctx, fs


async def _case_debate_bull(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    ctx, fs = await _get_debate_context(session, settings, symbol)
    return BenchmarkCase(symbol, "debate", custom_fn=generate_bull_advocacy, custom_args=(symbol, ctx, fs),
                          role_kwargs=dict(max_tokens=1500, thinking="medium"),
                          context_summary=json.dumps({"context": ctx, "fact_sheet": fs}, default=str)[:5000])


async def _case_debate_bear(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    ctx, fs = await _get_debate_context(session, settings, symbol)
    ref = make_client(settings.get("_benchmark_reference_model", "anthropic:claude-3-5-sonnet-20241022"), settings, max_tokens=1500, thinking="medium")
    bull_claim = await generate_bull_advocacy(ref, symbol, ctx, fs)
    return BenchmarkCase(symbol, "debate", custom_fn=generate_bear_dissent, custom_args=(symbol, ctx, bull_claim, fs),
                          role_kwargs=dict(max_tokens=1500, thinking="medium"),
                          context_summary=json.dumps({"context": ctx, "bull_claim": bull_claim, "fact_sheet": fs}, default=str)[:5000])


async def _case_debate_judge(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    ctx, fs = await _get_debate_context(session, settings, symbol)
    ref = make_client(settings.get("_benchmark_reference_model", "anthropic:claude-3-5-sonnet-20241022"), settings, max_tokens=1500, thinking="medium")
    bull_claim = await generate_bull_advocacy(ref, symbol, ctx, fs)
    bear_dissent = await generate_bear_dissent(ref, symbol, ctx, bull_claim, fs)
    return BenchmarkCase(symbol, "debate", custom_fn=evaluate_debate, custom_args=(symbol, ctx, bull_claim, bear_dissent),
                          role_kwargs=dict(max_tokens=800, thinking="high"),
                          context_summary=json.dumps({"context": ctx, "bull": bull_claim, "bear": bear_dissent}, default=str)[:5000])


_ADJUDICATION_SCHEMA = {"type": "object", "properties": {
    "adjudication_rule_correctly_applied": {"type": "boolean"},
    "expected_outcome_per_rules": {"type": "string", "enum": ["buy", "sell", "wait", "avoid", "ambiguous"]},
    "mismatch_explanation": {"type": "string"},
    "verdict": {"type": "string", "enum": ["CONFIRM", "FLAG_FOR_REVIEW", "CONTRADICTS_OWN_FRAMEWORK"]}},
    "required": ["adjudication_rule_correctly_applied", "expected_outcome_per_rules", "verdict"]}


async def _case_stage2_adjudicator(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    use_fixtures = settings.get("_use_fixtures", False)
    biases = {"technical": "BULLISH", "sentiment": "BULLISH", "macro": "NEUTRAL"}
    confidences = {"technical": "HIGH", "sentiment": "MEDIUM", "macro": "LOW"}
    decision = "BUY"
    rationale = "High confidence bullish technical confluence aligns with sentiment."
    if not use_fixtures and session:
        try:
            analysis = await pick_asset_analysis(session, symbol)
            biases_row = json.loads(analysis.specialist_biases_json) if analysis.specialist_biases_json else {}
            biases = biases_row.get("biases", biases)
            confidences = biases_row.get("confidence", confidences)
            decision = analysis.decision or decision
            rationale = analysis.rationale or rationale
        except Exception:
            pass
    prompt = ("Rules: IF Technical=BULLISH AND Macro=BULLISH -> HIGH conf BUY. IF Technical=BEARISH AND "
              "Macro=BEARISH -> HIGH conf SELL. IF Technical vs Macro conflict -> WAIT kecuali technical "
              "trust_weight>0.8. IF semua NEUTRAL/MIXED -> WAIT.\n\n"
              f"Specialist biases {symbol}: {json.dumps(biases)}\n"
              f"Specialist confidence: {json.dumps(confidences)}\n"
              f"Keputusan final: {decision}\nRationale: {rationale[:1500]}\n\n"
              "Apakah keputusan final mengikuti aturan dengan benar berdasarkan bias-bias ini?")
    return BenchmarkCase(symbol, "debate", "", prompt, schema=_ADJUDICATION_SCHEMA,
                          role_kwargs=dict(max_tokens=800, thinking="medium"), context_summary=prompt)


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
                "symbol": symbol, "decision": ctx["decision"], "confluence_score": analysis.confluence_score,
                "priced_in_score": analysis.priced_in_score, "rr_ratio": rr, "sl_beyond_structure": True,
                "actual_risk_state": {
                    "daily_pnl_pct": risk_state.get("daily_pnl_pct", 0.0),
                    "open_positions": open_pos.get("count", 0),
                    "portfolio_heat_pct": 0.0
                }
            }
            return strict_context, analysis
        except Exception:
            pass
    strict_context = get_synthetic_risk_context(symbol)
    return strict_context, None


async def _case_risk_gate(session, settings, ex, fn) -> BenchmarkCase:
    symbol = _sym(settings)
    strict_context, _ = await _build_strict_risk_context(session, settings, ex, symbol)
    return BenchmarkCase(symbol, "risk", custom_fn=fn, custom_args=(symbol, strict_context),
                          role_kwargs=dict(max_tokens=500, thinking="low"), context_summary=json.dumps(strict_context, default=str))


async def _case_risk_gate_conservative(session, settings, ex): return await _case_risk_gate(session, settings, ex, analyze_risk_conservative_llm)
async def _case_risk_gate_aggressive(session, settings, ex): return await _case_risk_gate(session, settings, ex, analyze_risk_aggressive_llm)
async def _case_risk_gate_neutral(session, settings, ex): return await _case_risk_gate(session, settings, ex, analyze_risk_neutral_llm)


async def _case_portfolio_manager_per_trade(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    strict_context, _ = await _build_strict_risk_context(session, settings, ex, symbol)
    min_rr = settings.get("trading", {}).get("risk", {}).get("min_rr_ratio", 1.3)
    risk_debate_states = {
        "conservative": analyze_risk_conservative(strict_context),
        "aggressive": analyze_risk_aggressive(strict_context, min_rr_ratio=min_rr),
        "neutral": analyze_risk_neutral(strict_context, min_rr_ratio=min_rr)
    }
    return BenchmarkCase(symbol, "risk", custom_fn=make_portfolio_decision,
                          custom_args=(symbol, risk_debate_states, strict_context["actual_risk_state"]),
                          role_kwargs=dict(max_tokens=400, thinking="low"),
                          context_summary=json.dumps({"risk_debate_states": risk_debate_states,
                                                       "actual_risk_state": strict_context["actual_risk_state"]}, default=str))


_PORTFOLIO_SYNTHESIS_SCHEMA = {"type": "object", "properties": {
    "recommendation": {"type": "string", "enum": ["execute_all", "reduce"]},
    "keep": {"type": "array", "items": {"type": "string"}},
    "size_adjustments": {"type": "object"}, "reasoning": {"type": "string"}},
    "required": ["recommendation", "keep", "reasoning"]}


async def _case_portfolio_synthesis(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    rows = []
    if not use_fixtures and session:
        try:
            from sqlalchemy import select as _sel
            from database.models import AssetAnalysis as _AA
            rows = (await session.execute(_sel(_AA).where(_AA.decision.in_(["buy", "sell"]))
                    .order_by(_AA.generated_at.desc()).limit(3))).scalars().all()
        except Exception:
            rows = []
    if len(rows) < 2:
        summaries = [
            "- EURUSD BUY: confidence=82% (Entry 1.1377, SL 1.1340, TP 1.1460)",
            "- GBPUSD BUY: confidence=65% (Entry 1.3217, SL 1.3180, TP 1.3320)",
            "- USDJPY SELL: confidence=78% (Entry 158.80, SL 159.50, TP 157.20)"
        ]
        brief_sentiment = "selective_risk_off"
        brief_confidence = 0.82
        vix_val = 15.68
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
            vix_val = (vix.get("latest") or {}).get("close", 16.0)
        except Exception:
            vix_val = 16.0
    prompt = (f"Portfolio Review: Multiple proposed trades across asset universe.\n\nProposed Trades:\n" + "\n".join(summaries) +
              f"\n\nRisk sentiment: {brief_sentiment}\nBrief confidence: {brief_confidence}\n"
              f"VIX: {vix_val}\n\n"
              "Eksekusi SEMUA trade ini, atau KURANGI portofolio karena korelasi/risiko? Jawab dengan "
              "recommendation, keep[], size_adjustments{symbol:multiplier} opsional, reasoning.")
    return BenchmarkCase("portfolio", "risk", "", prompt, schema=_PORTFOLIO_SYNTHESIS_SCHEMA,
                          role_kwargs=dict(max_tokens=800, thinking="high"), context_summary=prompt)


_ADVERSARIAL_SCHEMA = {"type": "object", "properties": {
    "approve": {"type": "boolean"}, "overall_quality": {"type": "string", "enum": ["high", "medium", "low"]},
    "strongest_counter_argument": {"type": "string"}, "hard_block": {"type": "boolean"},
    "hard_block_reason": {"type": "string"}, "recommend_block": {"type": "boolean"}, "block_reason": {"type": "string"}},
    "required": ["approve", "overall_quality", "strongest_counter_argument", "hard_block", "recommend_block"]}


async def _case_adversarial_check(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    use_fixtures = settings.get("_use_fixtures", False)
    decision = "BUY"
    confluence = 11
    priced_in = 3
    invalidation = "Break below 1.1342"
    entry_zone = "1.1365 - 1.1375"
    sl, tp = 1.1340, 1.1460
    rationale = "H1 BOS bullish after liquidity sweep below London low. Risk-reward is 2.24."
    if not use_fixtures and session:
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
    prompt = (f"Symbol: {symbol}\nDirection: {decision}\n"
              f"Confluence Score: {confluence}/14\nPriced-In Score: {priced_in}/10\n"
              f"Invalidation: {invalidation}\nEntry context: {entry_zone}\n"
              f"SL: {sl}  TP: {tp}\n\n"
              f"Full Rationale:\n{rationale[:3500]}\n\n"
              "Find the STRONGEST argument against this specific trade. hard_block=true only for objective "
              "defects (mathematical error, self-contradiction, missing invalidation). recommend_block=true "
              "for significant non-fatal risk.")
    return BenchmarkCase(symbol, "risk", "You are a skeptical risk-desk reviewer conducting a final "
                          "pre-trade challenge.", prompt, schema=_ADVERSARIAL_SCHEMA,
                          role_kwargs=dict(max_tokens=1200, thinking="medium"), context_summary=prompt)


# =========================================================================
# NEWS -- classification / verifier / digest, mode json/text, data live
# =========================================================================
async def _get_news_items_list(session, settings, limit: int = 6):
    use_fixtures = settings.get("_use_fixtures", False)
    if not use_fixtures and session:
        try:
            return await recent_news(session, limit=limit)
        except Exception:
            pass
    raw_fixtures = get_synthetic_news_items()
    from collections import namedtuple
    NewsMock = namedtuple("NewsMock", ["title", "summary", "fetched_at", "impact"])
    items = []
    for item in raw_fixtures[:limit]:
        items.append(NewsMock(
            title=item.get("title", ""),
            summary=item.get("summary", ""),
            fetched_at=item.get("fetched_at", "2026-09-25T08:00:00Z"),
            impact=item.get("expected_impact", "HIGH")
        ))
    return items


async def _case_news_classification(session, settings, ex) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=6)
    lines = [f"{i+1}. TITLE: {n.title[:150]}\n   SUMMARY: {(n.summary or '')[:200]}\n   FETCHED: {n.fetched_at}"
             for i, n in enumerate(items)]
    prompt = ("Classify market impact of each news item for FX, Commodities (Gold/Oil), and Crypto (Bitcoin) trading "
              "(BREAKING/HIGH/MEDIUM/LOW/NONE), surprise_magnitude, currencies, sentiments.\n\n" +
              NewsDigestProcessor.CLASSIFICATION_FEW_SHOT_EXAMPLES + "\n\nITEMS:\n" + "\n".join(lines))
    return BenchmarkCase("news_batch", "news", "", prompt, schema=NEWS_CLASSIFICATION_SCHEMA,
                          role_kwargs=dict(max_tokens=2000, thinking="medium"), context_summary=prompt[:5000])


async def _case_news_classification_escalation(session, settings, ex) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=4)
    lines = [f"{i+1}. ORIGINAL_VERDICT=HIGH\n   TITLE: {n.title[:200]}\n   FULL SUMMARY: {(n.summary or '')[:600]}"
             for i, n in enumerate(items)]
    prompt = "Re-evaluate each item from SCRATCH, without bias toward original verdict.\n\nITEMS:\n" + "\n".join(lines)
    return BenchmarkCase("news_escalation", "news", "", prompt, schema=NEWS_CLASSIFICATION_SCHEMA,
                          role_kwargs=dict(max_tokens=2000, thinking="low"), context_summary=prompt[:5000])


async def _case_news_classification_verifier(session, settings, ex) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=6)
    text = "\n\n".join([f"{i+1}. [current=HIGH] {n.title[:150]}\n   {(n.summary or '')[:200]}" for i, n in enumerate(items)])
    schema = {"type": "array", "items": {"type": "object", "properties": {
        "index": {"type": "integer"}, "verdict": {"type": "string", "enum": ["CONFIRM", "PROMOTE_TO_HIGH", "DEMOTE_TO_MEDIUM", "DEMOTE_TO_LOW"]},
        "reason": {"type": "string"}}, "required": ["index", "verdict", "reason"]}}
    prompt = f"HIGH-vs-MEDIUM calibration editor. For each item decide if current tier is appropriate.\n\nITEMS:\n{text}"
    return BenchmarkCase("news_verifier", "news", "", prompt, schema=schema,
                          role_kwargs=dict(max_tokens=600, thinking="low"), context_summary=prompt[:4000])


async def _case_news_digest(session, settings, ex) -> BenchmarkCase:
    items = await _get_news_items_list(session, settings, limit=15)
    text = "\n\n".join([f"[{getattr(n, 'impact', 'HIGH')}] {n.title}\n{(n.summary or '')[:300]}" for n in items])
    prompt = (f"Synthesize the following news into a MACRO OVERVIEW for FX, Commodities (Gold/Oil), and Crypto (Bitcoin) traders.\n\nNEWS:\n{text}\n\n"
              "Cover: [MACRO REGIME], [KEY DRIVERS], [WHAT MARKET IS WAITING FOR], "
              "[WHAT IS PRICED IN vs NOT], [CROSS-CURRENCY IMPLICATIONS]. Each claim MUST cite "
              "concrete numbers/levels/dates from the NEWS above.")
    return BenchmarkCase("news_digest", "news", "", prompt, role_kwargs=dict(max_tokens=3000, thinking="medium"),
                          context_summary=text[:5000])


async def _case_news_digest_macro_overview(session, settings, ex):
    return await _case_news_digest(session, settings, ex)


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
        digest_text = (
            "[MACRO REGIME] Hawkish rate plateau in US with Fed at 3.75-4.00% vs ECB at 2.50%.\n"
            "[KEY DRIVERS] Hormuz naval escalation pushing crude oil to $106/bbl.\n"
            "[CROSS-CURRENCY IMPLICATIONS] Strong USD tailwinds; EUR under pressure due to energy import drag."
        )
    prompt = ("Read this trading news digest and look for glaring contradictions between sections (quote "
              "verbatim both conflicting claims, rate severity material/minor).\n\nDIGEST:\n" +
              digest_text[:6000])
    return BenchmarkCase("digest_verifier", "news", "", prompt, schema=DIGEST_CONSISTENCY_SCHEMA,
                          role_kwargs=dict(max_tokens=800, thinking="low"), context_summary=digest_text[:4000])


async def _case_cot_precompute(session, settings, ex) -> BenchmarkCase:
    use_fixtures = settings.get("_use_fixtures", False)
    cot_signals = None
    if not use_fixtures and session:
        try:
            cot_signals = await MacroPreprocessor(settings=settings).compute_cot_signals(session)
        except Exception:
            cot_signals = None
    if not cot_signals:
        cot_signals = {
            "EUR": {"commercial_net": -45000, "non_commercial_net": 38000, "z_score": 1.45, "bias": "BEARISH_EXTREME"},
            "USD": {"commercial_net": 62000, "non_commercial_net": -51000, "z_score": -1.82, "bias": "BULLISH_EXTREME"},
            "XAU": {"commercial_net": -120000, "non_commercial_net": 115000, "z_score": 2.10, "bias": "OVERBOUGHT_REVERSAL_RISK"}
        }
    prompt = (f"Computed COT data:\n{json.dumps(cot_signals)}\n\n"
              "Produce a 2-3 sentence summary of institutional positioning, highlighting extreme/"
              "overcrowded positions and reversal risk implications. Do not invent new figures.")
    return BenchmarkCase("cot", "news", "You are a concise institutional positioning analyst.",
                          prompt, role_kwargs=dict(max_tokens=1024, thinking="low"), context_summary=prompt)


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
    sysp = ("You are an AI Trading Assistant. Use tools for real-time data. "
            "Answer grounded in data, do not fabricate numbers. Markdown format, concise.")
    return BenchmarkCase(f"chat_{idx}", "chat", sysp, msg, tools=TELEGRAM_TOOLS, history=[],
                          role_kwargs=dict(max_tokens=3000, max_tool_turns=8, thinking="medium"), context_summary=msg)


async def _case_chat_telegram(session, settings, ex): return await _build_chat_case(session, settings, ex, 0)
async def _case_chat_telegram_medium(session, settings, ex): return await _build_chat_case(session, settings, ex, 1)
async def _case_chat_telegram_complex(session, settings, ex): return await _build_chat_case(session, settings, ex, 2)


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
        prompt = (
            "Trade Rationale: EURUSD BUY at 1.1377 targeting 1.1460 based on H1 bullish displacement\n"
            "Decision: BUY (Confidence: 0.85)\n"
            "Outcome: Loss (-$250.00)\n"
            "Exit Reason: SL_HIT (Violent news wick triggered stop before resumption)\n"
            "Holding: 3.5h\n"
            "Enrichment Data: {\"vix_at_entry\": 15.68, \"vix_at_exit\": 24.10, \"breaking_news\": \"Hormuz strike headline\"}"
        )
        return BenchmarkCase("synthetic_reflection_01", "reflection",
                              "You are a trading post-mortem analyst. Use ONLY tags from enum. Concrete, not generic.",
                              prompt, schema=REFLECTION_SCHEMA, role_kwargs=dict(max_tokens=1500, thinking="medium"),
                              context_summary=prompt[:5000])
    outcome_str = f"Outcome: {'Profitable' if reflection.was_profitable else 'Loss'} (${reflection.outcome_pnl_usd})"
    prompt = (f"Trade Rationale: {reflection.rationale_summary}\nDecision: {reflection.decision} "
              f"(Confidence: {reflection.confidence})\n{outcome_str}\nExit Reason: {reflection.exit_reason}\n"
              f"Holding: {reflection.holding_hours}h\nEnrichment Data: {json.dumps(enrichment, default=str)}")
    return BenchmarkCase(str(reflection.id), "reflection",
                          "You are a trading post-mortem analyst. Use ONLY tags from enum. Concrete, not generic.",
                          prompt, schema=REFLECTION_SCHEMA, role_kwargs=dict(max_tokens=1500, thinking="medium"),
                          context_summary=prompt[:5000])


_HARNESS_HALLUCINATION_SCHEMA = {
    "type": "object",
    "properties": {
        "contradictions_detected": {"type": "array", "items": {"type": "string"}},
        "is_consistent": {"type": "boolean"},
        "severity": {"type": "string", "enum": ["none", "low", "medium", "high"]},
        "reasoning": {"type": "string"}
    },
    "required": ["contradictions_detected", "is_consistent", "severity", "reasoning"]
}

async def _case_harness_hallucination_detect(session, settings, ex) -> BenchmarkCase:
    contradictory_brief = {
        "currency_bias": {"USD": "bullish", "EUR": "bullish", "AUD": "bullish"},
        "dxy_trend": "strengthening +1.2%",
        "vix": 34.5,
        "risk_sentiment": "risk-on",
        "treasury_10y_yield": "4.65% (rising)",
        "fedwatch_cut_prob": "92%"
    }
    prompt = (
        "Audit this macro brief data for internal contradictions and hallucination risks:\n\n"
        f"{json.dumps(contradictory_brief, indent=2)}\n\n"
        "Identify ALL contradictions (e.g. VIX > 30 vs risk-on, DXY rising vs EUR/AUD bullish simultaneously, "
        "yields rising vs 92% rate cut expectation). Output JSON matching schema."
    )
    return BenchmarkCase(
        "stage1_shadow_check", "macro",
        "You are an adversarial quantitative auditor detecting internal contradictions and hallucination risks.",
        prompt,
        schema=_HARNESS_HALLUCINATION_SCHEMA,
        role_kwargs=dict(max_tokens=600, thinking="medium"),
        context_summary=prompt
    )

async def _case_harness_context_efficiency(session, settings, ex) -> BenchmarkCase:
    from utils.llm.prompt_compressor import ContextCompressor
    compressor = ContextCompressor(settings)
    raw_data = "Sample market structure text with extensive descriptions.\n" * 50
    compressed = compressor.compress_stage1_bundle(raw_data, max_tokens=200)
    prompt = (
        f"Analyze this compressed context and extract key market bias:\n\n{compressed}\n\n"
        "Provide a concise 1-paragraph summary with directional bias."
    )
    return BenchmarkCase(
        "news_digest", "macro",
        "You are a concise trading analyst.",
        prompt,
        role_kwargs=dict(max_tokens=400, thinking="low"),
        context_summary=prompt
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
        "stage2_prescreen", "trade_decision",
        "You are a disciplined trade execution validator.",
        prompt,
        schema={"type": "object", "properties": {"decision": {"type": "string"}, "entry": {"type": "number"}, "stop_loss": {"type": "number"}, "take_profit": {"type": "number"}, "reasoning": {"type": "string"}}, "required": ["decision", "entry", "stop_loss", "take_profit"]},
        role_kwargs=dict(max_tokens=400, thinking="low"),
        context_summary=prompt
    )


# =========================================================================
# SYSTEM ONE & EXPANDED TASK IMPLEMENTATIONS
# =========================================================================

async def _case_jev_news_realtime(session, settings, ex) -> BenchmarkCase:
    fix = load_fixture_json("s1_news_breaking_iran.json")
    state = fix.get("state", {
        "title": "BREAKING: Iran IRGC launches cruise missile strike on oil tankers in Strait of Hormuz",
        "summary": "Three commercial crude oil tankers struck in the Strait of Hormuz. Brent crude surges +7.5% to $114/bbl.",
        "open_positions": ["XAUUSD", "EURUSD", "USDJPY"]
    })
    questions = fix.get("questions", [
        {"name": "market_sentiment", "type": "Score", "range": [1, 5], "description": "1: Risk-off panic, 5: Risk-on euphoria"},
        {"name": "threatens_positions", "type": "Noul", "description": "Does headline introduce immediate sharp adverse volatility threat to open positions?"},
        {"name": "requires_circuit_breaker", "type": "Noul", "description": "Is this an extreme systemic shock requiring emergency circuit breaker or stop tightening?"}
    ])
    expected = fix.get("expected_answers", {
        "market_sentiment": 1,
        "threatens_positions": True,
        "threatens_positions_confidence_min": 0.85,
        "requires_circuit_breaker": True,
        "requires_circuit_breaker_confidence_min": 0.90
    })
    return BenchmarkCase(
        "jev_news_realtime", "news",
        user_prompt="Evaluate breaking news shock in real time against open positions.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        fixture_data=fix,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0)
    )


async def _case_jev_trigger_validator(session, settings, ex) -> BenchmarkCase:
    fix = load_fixture_json("s1_trigger_stale_eurusd.json")
    state = fix.get("state", {
        "symbol": "EURUSD",
        "trigger_type": "breakout_buy",
        "trigger_condition": {"level": 1.1460, "timeframe": "M15"},
        "current_price": 1.1377,
        "age_hours": 18.5,
        "macro_context": "Hawkish Fed hike + DXY break above 101.20 has shifted market structure to bearish H1."
    })
    questions = fix.get("questions", [
        {"name": "is_still_valid", "type": "Noul", "description": "Is this trade trigger still structurally valid and actionable given price action and elapsed time?"},
        {"name": "invalidation_risk", "type": "Score", "range": [1, 4], "description": "Rate risk that trigger is invalidated: 1: None, 2: Low, 3: Moderate, 4: High"}
    ])
    expected = fix.get("expected_answers", {
        "is_still_valid": False,
        "is_still_valid_confidence_min": 0.85,
        "invalidation_risk": 4
    })
    return BenchmarkCase(
        "jev_trigger_validator", "trade_decision",
        user_prompt="Validate trade trigger validity against current price action.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        fixture_data=fix,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0)
    )


async def _case_jev_position_guard(session, settings, ex) -> BenchmarkCase:
    fix = load_fixture_json("s1_position_guard_xauusd.json")
    state = fix.get("state", {
        "symbol": "XAUUSD",
        "direction": "BUY",
        "entry_price": 4275.00,
        "current_price": 4260.00,
        "sl": 4252.00,
        "tp": 4320.00,
        "volume": 0.5,
        "adverse_move_pips": 1500,
        "current_momentum": "sharp_bearish_impulse"
    })
    questions = fix.get("questions", [
        {"name": "adverse_momentum", "type": "Noul", "description": "Is there strong adverse momentum against our BUY position in XAUUSD?"},
        {"name": "sl_threat_level", "type": "Score", "range": [1, 4], "description": "1: Safe, 2: Normal, 3: Elevated, 4: Critical"},
        {"name": "should_tighten_stop", "type": "Noul", "description": "Should trailing stop be tightened?"}
    ])
    expected = fix.get("expected_answers", {
        "adverse_momentum": True,
        "adverse_momentum_confidence_min": 0.85,
        "sl_threat_level": 4,
        "should_tighten_stop": True
    })
    return BenchmarkCase(
        "jev_position_guard", "risk",
        user_prompt="Evaluate position risk and adverse momentum in real time.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        fixture_data=fix,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0)
    )


async def _case_jev_exit_prescreen(session, settings, ex) -> BenchmarkCase:
    fix = load_fixture_json("s1_exit_prescreen_gbpusd.json")
    state = fix.get("state", {
        "symbol": "GBPUSD",
        "direction": "BUY",
        "entry_price": 1.3320,
        "sl": 1.3250,
        "tp": 1.3450,
        "current_price": 1.3217,
        "holding_hours": 14.2,
        "structural_breakdown": True,
        "adverse_move_pips": 103
    })
    questions = fix.get("questions", [
        {"name": "thesis_still_valid", "type": "Noul", "description": "Is original trading thesis still structurally valid?"},
        {"name": "exit_urgency", "type": "Score", "range": [1, 5], "description": "1: No urgency, 3: Moderate, 5: Critical"}
    ])
    expected = fix.get("expected_answers", {
        "thesis_still_valid": False,
        "thesis_still_valid_confidence_min": 0.90,
        "exit_urgency": 4
    })
    return BenchmarkCase(
        "jev_exit_prescreen", "risk",
        user_prompt="Prescreen open position for early thesis invalidation exit.",
        state=state,
        questions=questions,
        expected_answers=expected,
        latency_target_ms=100.0,
        fixture_data=fix,
        role_kwargs=dict(max_tokens=512, thinking="none", temperature=0.0)
    )


async def _case_deep_research(session, settings, ex) -> BenchmarkCase:
    prompt = (
        "Conduct a deep macroeconomic research report analyzing the divergence between US Fed (+25bps hike to 3.75-4.00%) "
        "and ECB (+25bps to 2.50%) against the backdrop of the Middle East energy shock ($106 Brent). "
        "Evaluate the net impact on EUR/USD cross-asset liquidity and institutional positioning."
    )
    return BenchmarkCase(
        "deep_research", "macro",
        system_prompt="You are a Senior Quantitative Macro Researcher. Provide in-depth analysis citing specific yields, spreads, and liquidity dynamics.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=8192, thinking="high"),
        context_summary=prompt
    )


async def _case_report_synthesizer(session, settings, ex) -> BenchmarkCase:
    prompt = "Synthesize an end-of-cycle executive portfolio brief across EURUSD, GBPUSD, USDJPY, and XAUUSD based on today's session."
    return BenchmarkCase(
        "report_synthesizer", "macro",
        system_prompt="You are an Executive Trading Desk Synthesizer.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=4096, thinking="medium"),
        context_summary=prompt
    )


async def _case_context_compaction(session, settings, ex) -> BenchmarkCase:
    prompt = "Compress the following 12-page economic calendar and news transcript into a strict 400-token high-signal fact sheet."
    return BenchmarkCase(
        "context_compaction", "macro",
        system_prompt="You are a lossless context compression engine. Retain all exact numbers, rates, and quotes.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=1024, thinking="low"),
        context_summary=prompt
    )


async def _case_summarizer(session, settings, ex) -> BenchmarkCase:
    prompt = "Provide a 3-bullet progressive summary of the latest FOMC press conference transcript."
    return BenchmarkCase(
        "summarizer", "macro",
        system_prompt="You are an ultra-concise financial summarizer.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=512, thinking="low"),
        context_summary=prompt
    )


async def _case_macro_analyst(session, settings, ex) -> BenchmarkCase:
    prompt = "Investigate the real-yield divergence anomaly between US TIPS and German Bunds during the recent crude oil spike."
    return BenchmarkCase(
        "macro_analyst", "macro",
        system_prompt="You are a Macro Anomaly Specialist.",
        user_prompt=prompt,
        role_kwargs=dict(max_tokens=4096, thinking="high"),
        context_summary=prompt
    )


async def _case_sentiment_analyst(session, settings, ex) -> BenchmarkCase:
    prompt = "Extract directional sentiment, positioning bias, and fear/greed score from the institutional commentary feed."
    return BenchmarkCase(
        "sentiment_analyst", "specialist",
        system_prompt="You are a Sentiment and Positioning Specialist.",
        user_prompt=prompt,
        schema={"type": "object", "properties": {"sentiment_score": {"type": "number"}, "bias": {"type": "string"}, "institutional_positioning": {"type": "string"}}, "required": ["sentiment_score", "bias"]},
        role_kwargs=dict(max_tokens=1024, thinking="low"),
        context_summary=prompt
    )


async def _case_risk_gate_task(session, settings, ex) -> BenchmarkCase:
    prompt = "Evaluate the proposed EURUSD BUY order for subagent risk compliance against current portfolio heat (4.8%) and daily loss limit (-2.5%)."
    return BenchmarkCase(
        "risk_gate", "risk",
        system_prompt="You are a Subagent Risk Gate Auditor.",
        user_prompt=prompt,
        schema={"type": "object", "properties": {"approved": {"type": "boolean"}, "veto_reason": {"type": "string"}, "multiplier": {"type": "number"}}, "required": ["approved", "multiplier"]},
        role_kwargs=dict(max_tokens=1024, thinking="medium"),
        context_summary=prompt
    )


# =========================================================================
# REGISTRY -- 45 task, satu-satu dipetakan ke task_roles settings.yaml
# =========================================================================
TASKS: dict[str, TaskSpec] = {
    "stage1_fundamental": TaskSpec("stage1_fundamental", "macro", "agent", _case_stage1_fundamental),
    "stage1_escalation": TaskSpec("stage1_escalation", "macro", "agent", _case_stage1_escalation),
    "stage1_shadow_check": TaskSpec("stage1_shadow_check", "macro", "json", _case_stage1_shadow_check),
    "fundamental_verifier": TaskSpec("fundamental_verifier", "macro", "json", _case_fundamental_verifier),

    "stage2_per_asset_primary": TaskSpec("stage2_per_asset_primary", "trade_decision", "agent", _case_stage2_primary),
    "stage2_per_asset_secondary": TaskSpec("stage2_per_asset_secondary", "trade_decision", "agent", _case_stage2_secondary),
    "stage2_session_trigger": TaskSpec("stage2_session_trigger", "trade_decision", "agent", _case_stage2_session_trigger),
    "stage2_prescreen": TaskSpec("stage2_prescreen", "trade_decision", "json", _case_stage2_prescreen),

    "specialist_technical": TaskSpec("specialist_technical", "specialist", "json", _case_specialist_technical),
    "specialist_sentiment": TaskSpec("specialist_sentiment", "specialist", "json", _case_specialist_sentiment),
    "specialist_macro": TaskSpec("specialist_macro", "specialist", "json", _case_specialist_macro),

    "debate_bull": TaskSpec("debate_bull", "debate", "custom", _case_debate_bull),
    "debate_bear": TaskSpec("debate_bear", "debate", "custom", _case_debate_bear),
    "debate_judge": TaskSpec("debate_judge", "debate", "custom", _case_debate_judge),
    "stage2_adjudicator": TaskSpec("stage2_adjudicator", "debate", "json", _case_stage2_adjudicator),
    "adversarial_check": TaskSpec("adversarial_check", "risk", "json", _case_adversarial_check),

    "risk_gate_conservative": TaskSpec("risk_gate_conservative", "risk", "custom", _case_risk_gate_conservative),
    "risk_gate_aggressive": TaskSpec("risk_gate_aggressive", "risk", "custom", _case_risk_gate_aggressive),
    "risk_gate_neutral": TaskSpec("risk_gate_neutral", "risk", "custom", _case_risk_gate_neutral),
    "portfolio_manager_per_trade": TaskSpec("portfolio_manager_per_trade", "risk", "custom", _case_portfolio_manager_per_trade),
    "portfolio_synthesis": TaskSpec("portfolio_synthesis", "risk", "json", _case_portfolio_synthesis),

    "news_classification": TaskSpec("news_classification", "news", "json", _case_news_classification),
    "news_classification_escalation": TaskSpec("news_classification_escalation", "news", "json", _case_news_classification_escalation),
    "news_classification_verifier": TaskSpec("news_classification_verifier", "news", "json", _case_news_classification_verifier),
    "news_digest": TaskSpec("news_digest", "news", "text", _case_news_digest),
    "news_digest_macro_overview": TaskSpec("news_digest_macro_overview", "news", "text", _case_news_digest_macro_overview),
    "news_digest_verifier": TaskSpec("news_digest_verifier", "news", "json", _case_news_digest_verifier),
    "cot_precompute": TaskSpec("cot_precompute", "news", "text", _case_cot_precompute),

    "chat_telegram": TaskSpec("chat_telegram", "chat", "chat", _case_chat_telegram),
    "chat_telegram_medium": TaskSpec("chat_telegram_medium", "chat", "chat", _case_chat_telegram_medium),
    "chat_telegram_complex": TaskSpec("chat_telegram_complex", "chat", "chat", _case_chat_telegram_complex),

    "trade_reflection": TaskSpec("trade_reflection", "reflection", "json", _case_trade_reflection),

    # Harness Quality Benchmarks
    "harness_hallucination_detect": TaskSpec("harness_hallucination_detect", "macro", "json", _case_harness_hallucination_detect),
    "harness_context_efficiency": TaskSpec("harness_context_efficiency", "macro", "text", _case_harness_context_efficiency),
    "harness_self_correction": TaskSpec("harness_self_correction", "trade_decision", "json", _case_harness_self_correction),

    # System One Decision Tasks
    "jev_news_realtime": TaskSpec("jev_news_realtime", "news", "system_one", _case_jev_news_realtime),
    "jev_trigger_validator": TaskSpec("jev_trigger_validator", "trade_decision", "system_one", _case_jev_trigger_validator),
    "jev_position_guard": TaskSpec("jev_position_guard", "risk", "system_one", _case_jev_position_guard),
    "jev_exit_prescreen": TaskSpec("jev_exit_prescreen", "risk", "system_one", _case_jev_exit_prescreen),

    # Deep Research & Subagents
    "deep_research": TaskSpec("deep_research", "macro", "agent", _case_deep_research),
    "report_synthesizer": TaskSpec("report_synthesizer", "macro", "text", _case_report_synthesizer),
    "context_compaction": TaskSpec("context_compaction", "macro", "text", _case_context_compaction),
    "summarizer": TaskSpec("summarizer", "macro", "text", _case_summarizer),
    "macro_analyst": TaskSpec("macro_analyst", "macro", "agent", _case_macro_analyst),
    "sentiment_analyst": TaskSpec("sentiment_analyst", "specialist", "json", _case_sentiment_analyst),
    "risk_gate": TaskSpec("risk_gate", "risk", "json", _case_risk_gate_task),
}
