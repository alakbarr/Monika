import json
from dataclasses import dataclass, field
from typing import Callable, Optional, Awaitable
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


@dataclass
class TaskSpec:
    task_id: str
    category: str
    mode: str  # "agent" | "json" | "text" | "chat" | "custom"
    build_case: Callable[[AsyncSession, dict, BenchmarkToolExecutor], Awaitable[BenchmarkCase]]


def _sym(settings: dict) -> str:
    return settings.get("_benchmark_symbol") or settings["trading"]["asset_universe"][0]


# =========================================================================
# STAGE 1 (macro) -- mode agent, pakai skill loader ASLI + bundle prefetch ASLI
# =========================================================================
def _stage1_system_prompt(settings: dict) -> str:
    skills = ["macro_analysis_framework", "market_dynamics_framework", "performance_notes", "fundamental_performance_notes"]
    if settings.get("trading", {}).get("caveman_mode", False):
        skills.append("caveman_mode")
    return compose_system_prompt(*skills)


async def _case_stage1_fundamental(session, settings, ex) -> BenchmarkCase:
    bundle, _, _ = await Stage1DataBundler(session, settings).prefetch_all_data()
    user_msg = STAGE1_USER_MESSAGE_TEXT + f"\n\n[PRE-FETCHED DATA]\n{bundle}"
    return BenchmarkCase("stage1", "macro", _stage1_system_prompt(settings), user_msg,
                          tools=STAGE1_TOOLS, stage_name="benchmark_stage1_fundamental",
                          role_kwargs=dict(max_tokens=12000, max_tool_turns=8, thinking="high"),
                          context_summary=bundle)


async def _case_stage1_escalation(session, settings, ex) -> BenchmarkCase:
    bundle, _, _ = await Stage1DataBundler(session, settings).prefetch_all_data()
    try:
        prior_json = (await latest_brief(session)).structured_json or "{}"
    except RuntimeError:
        prior_json = "{}"
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
    bundle, _, _ = await Stage1DataBundler(session, settings).prefetch_all_data()
    try:
        declared_bias = json.loads((await latest_brief(session)).structured_json or "{}").get("currency_bias", {})
    except RuntimeError:
        declared_bias = {}
    prompt = ("Independen dari brief manapun, tentukan bias USD/EUR/GBP/JPY/AUD/XAU "
              "(bullish/bearish/neutral) HANYA dari data mentah berikut:\n" + bundle[:6000] +
              f"\n\nBrief yang sedang diverifikasi menyimpulkan: {json.dumps(declared_bias)}\n"
              "Hitung agreement_pct dan sebutkan flagged_currencies yang berbeda.")
    return BenchmarkCase("stage1_shadow_check", "macro", "", prompt, schema=_SHADOW_SCHEMA,
                          role_kwargs=dict(max_tokens=800, thinking="low"), context_summary=bundle[:4000])


async def _case_fundamental_verifier(session, settings, ex) -> BenchmarkCase:
    brief = await latest_brief(session)
    st = json.loads(brief.structured_json or "{}")
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
    cot_code = SYMBOL_TO_COT.get(symbol, "")
    threshold, _ = await compute_unified_confluence_threshold(session, symbol, settings)
    sysp = _stage2_system_prompt(settings, symbol, cot_code, threshold)
    bundled = await Stage2DataBundler(session, settings).fetch_bundle(symbol, cot_code=cot_code or None)
    bundle_text = bundled[0] if isinstance(bundled, tuple) else (bundled or "")
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
    vix = await ex.execute("get_vix", {})
    risk_state = await ex.execute("get_risk_state", {})
    prompt = (f"Quick trading opportunity check untuk {symbol}.\n"
              f"VIX: {(vix.get('latest') or {}).get('close')}\nRisk paused: {risk_state.get('trading_paused')}\n"
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
    cot_code = SYMBOL_TO_COT.get(symbol, "")
    bundled = await Stage2DataBundler(session, settings).fetch_bundle(symbol, cot_code=cot_code or None)
    _text, raw = bundled if isinstance(bundled, tuple) else ("", {})
    keys = PerAssetStage._SPECIALIST_KEY_MAP.get(role, [])
    view = {k: v for k, v in raw.items() if k in keys and v is not None}
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
async def _case_debate_bull(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    analysis = await pick_asset_analysis(session, symbol)
    ctx = entry_context(analysis)
    fs = await build_fact_sheet(session, analysis.id)
    return BenchmarkCase(symbol, "debate", custom_fn=generate_bull_advocacy, custom_args=(symbol, ctx, fs),
                          role_kwargs=dict(max_tokens=1500, thinking="medium"),
                          context_summary=json.dumps({"context": ctx, "fact_sheet": fs}, default=str)[:5000])


async def _case_debate_bear(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    analysis = await pick_asset_analysis(session, symbol)
    ctx = entry_context(analysis)
    fs = await build_fact_sheet(session, analysis.id)
    ref = make_client(settings["_benchmark_reference_model"], settings, max_tokens=1500, thinking="medium")
    bull_claim = await generate_bull_advocacy(ref, symbol, ctx, fs)
    return BenchmarkCase(symbol, "debate", custom_fn=generate_bear_dissent, custom_args=(symbol, ctx, bull_claim, fs),
                          role_kwargs=dict(max_tokens=1500, thinking="medium"),
                          context_summary=json.dumps({"context": ctx, "bull_claim": bull_claim, "fact_sheet": fs}, default=str)[:5000])


async def _case_debate_judge(session, settings, ex) -> BenchmarkCase:
    symbol = _sym(settings)
    analysis = await pick_asset_analysis(session, symbol)
    ctx = entry_context(analysis)
    fs = await build_fact_sheet(session, analysis.id)
    ref = make_client(settings["_benchmark_reference_model"], settings, max_tokens=1500, thinking="medium")
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
    analysis = await pick_asset_analysis(session, symbol)
    biases_row = json.loads(analysis.specialist_biases_json) if analysis.specialist_biases_json else {}
    prompt = ("Rules: IF Technical=BULLISH AND Macro=BULLISH -> HIGH conf BUY. IF Technical=BEARISH AND "
              "Macro=BEARISH -> HIGH conf SELL. IF Technical vs Macro conflict -> WAIT kecuali technical "
              "trust_weight>0.8. IF semua NEUTRAL/MIXED -> WAIT.\n\n"
              f"Specialist biases {symbol}: {json.dumps(biases_row.get('biases', {}))}\n"
              f"Specialist confidence: {json.dumps(biases_row.get('confidence', {}))}\n"
              f"Keputusan final: {analysis.decision}\nRationale: {(analysis.rationale or '')[:1500]}\n\n"
              "Apakah keputusan final mengikuti aturan dengan benar berdasarkan bias-bias ini?")
    return BenchmarkCase(symbol, "debate", "", prompt, schema=_ADJUDICATION_SCHEMA,
                          role_kwargs=dict(max_tokens=800, thinking="medium"), context_summary=prompt)


# =========================================================================
# RISK -- risk_gate_* & portfolio_manager_per_trade = mode custom (fungsi ASLI)
# =========================================================================
async def _build_strict_risk_context(session, settings, ex, symbol) -> tuple[dict, object]:
    analysis = await pick_asset_analysis(session, symbol)
    ctx = entry_context(analysis)
    risk_state = await ex.execute("get_risk_state", {})
    open_pos = await ex.execute("get_open_positions", {})
    entry_price = ctx.get("entry_price")
    rr = None
    if entry_price and analysis.stop_loss and analysis.take_profit:
        sl_d, tp_d = abs(entry_price - analysis.stop_loss), abs(entry_price - analysis.take_profit)
        rr = (tp_d / sl_d) if sl_d else None
    strict_context = {"symbol": symbol, "decision": ctx["decision"], "confluence_score": analysis.confluence_score,
                       "priced_in_score": analysis.priced_in_score, "rr_ratio": rr, "sl_beyond_structure": True,
                       "actual_risk_state": {"daily_pnl_pct": risk_state.get("daily_pnl_pct", 0.0),
                                              "open_positions": open_pos.get("count", 0),
                                              "portfolio_heat_pct": 0.0}}
    return strict_context, analysis


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
    risk_debate_states = {"conservative": analyze_risk_conservative(strict_context),
                           "aggressive": analyze_risk_aggressive(strict_context, min_rr_ratio=min_rr),
                           "neutral": analyze_risk_neutral(strict_context, min_rr_ratio=min_rr)}
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
    from sqlalchemy import select as _sel
    from database.models import AssetAnalysis as _AA
    rows = (await session.execute(_sel(_AA).where(_AA.decision.in_(["buy", "sell"]))
            .order_by(_AA.generated_at.desc()).limit(3))).scalars().all()
    if len(rows) < 2:
        raise RuntimeError("Butuh >=2 baris AssetAnalysis buy/sell terbaru untuk benchmark portfolio_synthesis.")
    summaries = [f"- {r.symbol} {r.decision.upper()}: confidence={r.confidence:.0%}" for r in rows]
    brief = await latest_brief(session)
    vix = await ex.execute("get_vix", {})
    prompt = (f"Portfolio Review: {len(rows)} trade diusulkan bersamaan.\n\nProposed Trades:\n" + "\n".join(summaries) +
              f"\n\nRisk sentiment: {brief.risk_sentiment}\nBrief confidence: {brief.confidence}\n"
              f"VIX: {(vix.get('latest') or {}).get('close')}\n\n"
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
    analysis = await pick_asset_analysis(session, symbol)
    prompt = (f"Symbol: {analysis.symbol}\nDirection: {(analysis.decision or '').upper()}\n"
              f"Confluence Score: {analysis.confluence_score}/14\nPriced-In Score: {analysis.priced_in_score}/10\n"
              f"Invalidation: {analysis.invalidation}\nEntry context: {analysis.entry_zone}\n"
              f"SL: {analysis.stop_loss}  TP: {analysis.take_profit}\n\n"
              f"Full Rationale:\n{(analysis.rationale or '')[:3500]}\n\n"
              "Find the STRONGEST argument against this specific trade. hard_block=true only for objective "
              "defects (mathematical error, self-contradiction, missing invalidation). recommend_block=true "
              "for significant non-fatal risk.")
    return BenchmarkCase(symbol, "risk", "You are a skeptical risk-desk reviewer conducting a final "
                          "pre-trade challenge.", prompt, schema=_ADVERSARIAL_SCHEMA,
                          role_kwargs=dict(max_tokens=1200, thinking="medium"), context_summary=prompt)


# =========================================================================
# NEWS -- classification / verifier / digest, mode json/text, data live
# =========================================================================
async def _case_news_classification(session, settings, ex) -> BenchmarkCase:
    items = await recent_news(session, limit=6)
    lines = [f"{i+1}. TITLE: {n.title[:150]}\n   SUMMARY: {(n.summary or '')[:200]}\n   FETCHED: {n.fetched_at}"
             for i, n in enumerate(items)]
    prompt = ("Classify market impact of each news item for FX, Commodities (Gold/Oil), and Crypto (Bitcoin) trading "
              "(BREAKING/HIGH/MEDIUM/LOW/NONE), surprise_magnitude, currencies, sentiments.\n\n" +
              NewsDigestProcessor.CLASSIFICATION_FEW_SHOT_EXAMPLES + "\n\nITEMS:\n" + "\n".join(lines))
    return BenchmarkCase("news_batch", "news", "", prompt, schema=NEWS_CLASSIFICATION_SCHEMA,
                          role_kwargs=dict(max_tokens=2000, thinking="medium"), context_summary=prompt[:5000])


async def _case_news_classification_escalation(session, settings, ex) -> BenchmarkCase:
    items = await recent_news(session, limit=4)
    lines = [f"{i+1}. ORIGINAL_VERDICT=HIGH\n   TITLE: {n.title[:200]}\n   FULL SUMMARY: {(n.summary or '')[:600]}"
             for i, n in enumerate(items)]
    prompt = "Re-evaluate each item from SCRATCH, without bias toward original verdict.\n\nITEMS:\n" + "\n".join(lines)
    return BenchmarkCase("news_escalation", "news", "", prompt, schema=NEWS_CLASSIFICATION_SCHEMA,
                          role_kwargs=dict(max_tokens=2000, thinking="low"), context_summary=prompt[:5000])


async def _case_news_classification_verifier(session, settings, ex) -> BenchmarkCase:
    items = await recent_news(session, limit=6)
    text = "\n\n".join([f"{i+1}. [current=HIGH] {n.title[:150]}\n   {(n.summary or '')[:200]}" for i, n in enumerate(items)])
    schema = {"type": "array", "items": {"type": "object", "properties": {
        "index": {"type": "integer"}, "verdict": {"type": "string", "enum": ["CONFIRM", "PROMOTE_TO_HIGH", "DEMOTE_TO_MEDIUM", "DEMOTE_TO_LOW"]},
        "reason": {"type": "string"}}, "required": ["index", "verdict", "reason"]}}
    prompt = f"HIGH-vs-MEDIUM calibration editor. For each item decide if current tier is appropriate.\n\nITEMS:\n{text}"
    return BenchmarkCase("news_verifier", "news", "", prompt, schema=schema,
                          role_kwargs=dict(max_tokens=600, thinking="low"), context_summary=prompt[:4000])


async def _case_news_digest(session, settings, ex) -> BenchmarkCase:
    items = await recent_news(session, limit=15)
    text = "\n\n".join([f"[{n.impact or '?'}] {n.title}\n{(n.summary or '')[:300]}" for n in items])
    prompt = (f"Synthesize the following news into a MACRO OVERVIEW for FX, Commodities (Gold/Oil), and Crypto (Bitcoin) traders.\n\nNEWS:\n{text}\n\n"
              "Cover: [MACRO REGIME], [KEY DRIVERS], [WHAT MARKET IS WAITING FOR], "
              "[WHAT IS PRICED IN vs NOT], [CROSS-CURRENCY IMPLICATIONS]. Each claim MUST cite "
              "concrete numbers/levels/dates from the NEWS above.")
    return BenchmarkCase("news_digest", "news", "", prompt, role_kwargs=dict(max_tokens=3000, thinking="medium"),
                          context_summary=text[:5000])


async def _case_news_digest_macro_overview(session, settings, ex):
    # Task role produksi ini memakai gaya prompt & artifact sama seperti
    # news_digest (bedanya cuma model roster) -> pakai ulang case yang sama.
    return await _case_news_digest(session, settings, ex)


async def _case_news_digest_verifier(session, settings, ex) -> BenchmarkCase:
    digest = await latest_digest(session)
    if digest is None:
        raise RuntimeError("Belum ada NewsDigest di DB.")
    prompt = ("Read this trading news digest and look for glaring contradictions between sections (quote "
              "verbatim both conflicting claims, rate severity material/minor).\n\nDIGEST:\n" +
              digest.digest_text[:6000])
    return BenchmarkCase("digest_verifier", "news", "", prompt, schema=DIGEST_CONSISTENCY_SCHEMA,
                          role_kwargs=dict(max_tokens=800, thinking="low"), context_summary=digest.digest_text[:4000])


async def _case_cot_precompute(session, settings, ex) -> BenchmarkCase:
    cot_signals = await MacroPreprocessor(settings=settings).compute_cot_signals(session)
    if not cot_signals:
        raise RuntimeError("Belum ada data COT di DB.")
    prompt = (f"Computed COT data:\n{json.dumps(cot_signals)}\n\n"
              "Produce a 2-3 sentence summary of institutional positioning, highlighting extreme/"
              "overcrowded positions and reversal risk implications. Do not invent new figures.")
    return BenchmarkCase("cot", "news", "You are a concise institutional positioning analyst.",
                          prompt, role_kwargs=dict(max_tokens=1024, thinking="low"), context_summary=prompt)


# =========================================================================
# CHAT -- Telegram assistant, mode chat. Pertanyaan diambil dari histori
# TelegramConversation asli kalau ada, fallback ke pertanyaan representatif
# kalau DB percakapan kosong.
# =========================================================================
_FALLBACK_CHAT_QUESTIONS = [
    "What is the current account status and open positions?",
    "Summarize the latest fundamental brief and its implications for XAUUSD.",
    "What is current VIX and how does it affect our risk sentiment?",
]


async def _build_chat_case(session, settings, ex, idx: int) -> BenchmarkCase:
    msg = await latest_user_message(session) or _FALLBACK_CHAT_QUESTIONS[idx % len(_FALLBACK_CHAT_QUESTIONS)]
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
    reflection = await resolved_reflection(session)
    if reflection is None:
        raise RuntimeError("Belum ada DecisionReflection status=resolved di DB.")
    enrichment = await TradeReflector(settings)._fetch_enrichment_context(session, reflection)
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
# REGISTRY -- 35 task, satu-satu dipetakan ke task_roles settings.yaml
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
}
