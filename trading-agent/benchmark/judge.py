import logging
from typing import Optional
from .invoker import make_client, _attach_usage_capture

logger = logging.getLogger("Benchmark.Judge")

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "grounding_score": {"type": "integer", "minimum": 0, "maximum": 10},
        "accuracy_score": {"type": "integer", "minimum": 0, "maximum": 10},
        "actionability_score": {"type": "integer", "minimum": 0, "maximum": 10},
        "consistency_score": {"type": "integer", "minimum": 0, "maximum": 10},
        "hallucination_risk": {"type": "string", "enum": ["none", "low", "medium", "high"]},
        "notes": {"type": "string"},
    },
    "required": ["grounding_score", "accuracy_score", "actionability_score",
                 "consistency_score", "hallucination_risk", "notes"],
}

RUBRICS: dict[str, str] = {
    "macro": ("Nilai sebuah macro/fundamental brief FX. grounding_score: apakah setiap klaim "
              "melacak ke angka konkret (level DXY, VIX, yield, % FedWatch, COT) di context, bukan "
              "pernyataan kabur? accuracy_score: apakah hubungan yang dinyatakan (DXY vs bias USD, "
              "VIX vs risk sentiment) konsisten & arahnya benar? actionability_score: apakah ada bias "
              "per-currency dengan invalidation yang falsifiable? consistency_score: narasi vs tabel "
              "bias tidak kontradiktif. hallucination_risk: angka/kejadian yang TIDAK ada di context."),
    "trade_decision": ("Nilai keputusan trading teknikal per-aset (SMC/ICT). grounding_score: entry/"
                        "SL/TP terikat ke level struktural nyata (OB/FVG/S-R/swing) di data, bukan "
                        "harga karangan. accuracy_score: matematika R:R benar, SL/TP di sisi yang "
                        "benar terhadap entry, ADR-band masuk akal. actionability_score: keputusan "
                        "spesifik & langsung bisa dieksekusi dengan invalidation jelas. "
                        "consistency_score: confluence_factors yang disebut cocok dengan "
                        "confluence_score yang diklaim. hallucination_risk: harga/indikator yang "
                        "tidak bisa diturunkan dari context."),
    "debate": ("Nilai satu sisi debat bull/bear/judge atas sebuah proposal trade. grounding_score: "
               "argumen mengacu angka nyata di fact sheet. accuracy_score: logis, bukan strawman. "
               "actionability_score: verdict/severity tegas & berdasar. consistency_score: koheren "
               "internal. hallucination_risk: fakta karangan."),
    "risk": ("Nilai rekomendasi veto/sizing risk-manager. grounding_score: multiplier & veto "
             "mengikuti aturan numerik yang diberikan terhadap state portofolio nyata. "
             "accuracy_score: aritmatika/logika benar. actionability_score: output jelas & bisa "
             "dipakai. consistency_score: teks asesmen cocok dengan verdict numerik. "
             "hallucination_risk: angka portofolio karangan."),
    "news": ("Nilai klasifikasi/digest dampak berita. grounding_score: level impact cocok definisi "
             "yang diberikan (BREAKING butuh <90mnt + surprise + tanpa kata reaksi pasar). "
             "accuracy_score: tag currency & sentiment benar untuk isinya. actionability_score: "
             "berguna buat trader yg scan cepat. consistency_score: tidak kontradiksi antar item. "
             "hallucination_risk: angka/kejadian karangan."),
    "specialist": ("Nilai laporan specialist satu-domain (technical-only / sentiment-only / "
                   "macro-only). grounding_score: ketat hanya pakai data domainnya sendiri. "
                   "accuracy_score: directional_bias cocok bukti. actionability_score: label "
                   "confidence cocok kekuatan bukti. consistency_score: tidak ada leakage domain "
                   "(mis. laporan technical mengutip COT). hallucination_risk: level karangan."),
    "chat": ("Nilai balasan asisten trading Telegram. grounding_score: setiap angka yang dikutip "
             "(harga, PnL, SL/TP) didukung tool call nyata di transkrip, tidak pernah dikarang. "
             "accuracy_score: menjawab pertanyaan user dengan benar. actionability_score: ringkas, "
             "terstruktur, berguna. consistency_score: tidak kontradiksi diri sendiri. "
             "hallucination_risk: klaim harga/PnL dengan nol tool call."),
    "reflection": ("Nilai refleksi post-mortem sebuah trade. grounding_score: lesson terkait data "
                   "enrichment nyata (confluence factors, verdict adversarial, outcome). "
                   "accuracy_score: process_was_sound/outcome_process_classification cocok logika "
                   "narasi. actionability_score: next_trade_adjustment konkret, bukan generik "
                   "('lebih hati-hati'). consistency_score: tag cocok narasi. hallucination_risk: "
                   "detail trade karangan."),
}


JUDGE_PERSONAS = {
    "macro_economist": (
        "You are a Senior Macroeconomic Strategist and Central Bank Policy Specialist. "
        "Evaluate the candidate trading decision strictly from a macroeconomic perspective: monetary policy alignment, "
        "interest rate differentials, inflation trajectory, and macroeconomic news grounding. "
        "Heavily penalize outputs that misinterpret central bank forward guidance or make unfounded macroeconomic claims."
    ),
    "technical_analyst": (
        "You are a Chartered Market Technician and Institutional Orderflow / ICT Specialist. "
        "Evaluate the candidate decision on market structure, liquidity sweeps, order blocks, multi-timeframe alignment, "
        "and risk-to-reward realism (SL/TP placement). Deduct heavily for vague invalidation criteria or chasing extended moves."
    ),
    "risk_officer": (
        "You are a Chief Risk Officer and Quantitative QA Auditor. "
        "Evaluate the candidate output for numerical grounding, hallucination risk, portfolio heat, correlation exposure, "
        "and strict compliance with risk limits. Deduct severely for any hallucinated numbers, price levels not in context, "
        "or asymmetric downside risk."
    ),
    "portfolio_risk_assessor": (
        "You are a Portfolio Risk Assessor and Multi-Asset Exposure Specialist. "
        "Evaluate trading decisions specifically for portfolio concentration, cross-currency correlation, "
        "drawdown headroom, and risk-adjusted positioning. Deduct score if the setup stacks risk "
        "on already-overexposed currency blocks without idiosyncratic justification."
    ),
    "general": "You are a strict, skeptical trading-desk QA reviewer.",
}


def _score(js: dict) -> float:
    if not js:
        return 0.0
    base = ((float(js.get("grounding_score") or 0)) +
            (float(js.get("accuracy_score") or 0)) +
            (float(js.get("actionability_score") or 0)) +
            (float(js.get("consistency_score") or 0))) / 4.0
    penalty = {"none": 0.0, "low": 0.5, "medium": 1.5, "high": 3.5}.get(js.get("hallucination_risk", "low"), 0.5)
    return max(0.0, base - penalty)


async def judge_output(judge_model: str, settings: dict, category: str, context_summary: str,
                        candidate_output, max_context_chars: int = 32000, persona: str = "general") -> tuple[dict, float, int, int]:
    rubric = RUBRICS.get(category, RUBRICS["trade_decision"])
    client = make_client(judge_model, settings, max_tokens=1200, temperature=0.0, thinking="low")
    usage = _attach_usage_capture(client)
    system_prompt = JUDGE_PERSONAS.get(persona, JUDGE_PERSONAS["general"])
    prompt = (f"RUBRIC:\n{rubric}\n\n"
              f"--- CONTEXT PROVIDED TO MODEL ---\n{str(context_summary)[:max_context_chars]}\n\n"
              f"--- CANDIDATE OUTPUT BEING EVALUATED ---\n{str(candidate_output)[:max_context_chars]}\n\n"
              f"EVALUATOR ROLE: {persona.upper()}\n"
              "Evaluate strictly according to your specialized persona. Deduct score for any claim that cannot be traced back to the context.")
    try:
        js = await client.classify_json(prompt, system_prompt=system_prompt,
                                         schema=JUDGE_SCHEMA)
    except Exception as e:
        logger.warning(f"Judge call gagal ({judge_model} [{persona}]): {e}")
        js = None
    return (js or {}, _score(js) if js else 0.0, usage.get("input_tokens", 0), usage.get("output_tokens", 0))


async def judge_output_ensemble(
    judge_models: list[str],
    settings: dict,
    category: str,
    context_summary: str,
    candidate_output,
    max_context_chars: int = 32000,
    personas: Optional[list[str]] = None,
) -> tuple[dict, float, int, int]:
    """
    Evaluasi multi-judge ensemble (mis. Claude + GPT + DeepSeek) dengan diversifikasi persona
    (Macro Economist, Technical Analyst, Risk Officer) untuk mengurangi bias single-model.
    """
    import asyncio
    if not judge_models:
        default_judges = settings.get("benchmark", {}).get("default_judges")
        if default_judges and isinstance(default_judges, list):
            judge_models = default_judges
        else:
            judge_models = [settings.get("benchmark", {}).get("default_judge", "claude-sonnet-5")]

    CATEGORY_PERSONA_MAP = {
        "macro": ["macro_economist", "portfolio_risk_assessor", "general"],
        "trade_decision": ["technical_analyst", "risk_officer", "portfolio_risk_assessor"],
        "debate": ["technical_analyst", "macro_economist", "portfolio_risk_assessor"],
        "risk": ["risk_officer", "portfolio_risk_assessor", "general"],
        "news": ["macro_economist", "general", "portfolio_risk_assessor"],
        "specialist": ["technical_analyst", "macro_economist", "risk_officer"],
        "chat": ["general", "macro_economist", "technical_analyst"],
        "reflection": ["risk_officer", "general", "portfolio_risk_assessor"],
    }
    if not personas:
        available_personas = CATEGORY_PERSONA_MAP.get(
            category,
            ["macro_economist", "technical_analyst", "risk_officer", "portfolio_risk_assessor"],
        )
        personas = [available_personas[i % len(available_personas)] for i in range(len(judge_models))]

    tasks = [
        judge_output(m, settings, category, context_summary, candidate_output, max_context_chars, persona=p)
        for m, p in zip(judge_models, personas)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    valid_scores = []
    valid_verdicts = []
    total_in = 0
    total_out = 0

    for i, res in enumerate(results):
        if isinstance(res, tuple) and len(res) == 4:
            js, score, in_tok, out_tok = res
            if js:
                js_copy = dict(js)
                js_copy["judge_persona"] = personas[i]
                js_copy["judge_model"] = judge_models[i]
                valid_scores.append(score)
                valid_verdicts.append(js_copy)
            total_in += in_tok
            total_out += out_tok

    if not valid_scores:
        return ({}, 0.0, total_in, total_out)

    # Consensus score across distinct personas
    consensus_score = round(sum(valid_scores) / len(valid_scores), 2)
    best_idx = min(range(len(valid_scores)), key=lambda i: abs(valid_scores[i] - consensus_score))
    consensus_verdict = dict(valid_verdicts[best_idx])
    consensus_verdict["ensemble_scores"] = valid_scores
    consensus_verdict["ensemble_consensus_score"] = consensus_score
    consensus_verdict["ensemble_verdicts"] = valid_verdicts

    return (consensus_verdict, consensus_score, total_in, total_out)
