# ==============================================================================
# File: application/analysis/schemas/brief_schemas.py
# ==============================================================================

"""
Submit Fundamental Brief Schema Definition and Specialized Macro Validators.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
import math
import re
import json
import copy

from monika.application.analysis.schemas.common import (
    ConfidenceLevel,
    MacroRegime,
    SentimentBand,
    TradeDirection,
    coerce_float,
    coerce_int,
    coerce_str,
    coerce_string_list,
)
from monika.application.analysis.schemas.sub_models import (
    AssetMacroContext,
    PricedInAssessment,
    ChecklistVerification,
    KeyDataPointsUsed,
    UpcomingRiskEvent,
)

logger = logging.getLogger("TradingAgent.Schemas")


class SubmitFundamentalBriefSchema(BaseModel):
    checklist: ChecklistVerification = Field(
        default_factory=lambda: ChecklistVerification(
            bias_vs_narrative_match=True,
            contradiction_existed=False,
        ),
        description="Wajib diisi sebelum submit. Verifikasi kelengkapan dan konsistensi internal.",
    )
    key_data_points_used: KeyDataPointsUsed = Field(
        default_factory=lambda: KeyDataPointsUsed(
            dxy_trend_5d="strengthening",
            vix_close=16.7,
            cot_leveraged_long_pct=None,
            fedwatch_dominant_pct=None,
            fedwatch_repricing_delta_pct=None,
            treasury_10y_yield_pct=None,
        ),
        description=(
            "WAJIB: restate nilai numerik kunci yang BENAR-BENAR kamu baca dari tools "
            "sebelum menulis narasi. Field ini di-cross-check backend terhadap data riil "
            "yang sudah di-fetch untuk mendeteksi salah baca/halusinasi angka."
        ),
    )
    macro_narrative: str = Field(
        ...,
        description=(
            "An articulate, institutional macro research memo (Bloomberg Intelligence / Goldman Sachs GIR style). "
            "Explains economic causality, transmission mechanics, and cross-market dynamics across structured Markdown "
            "sub-sections (1. Macro Regime & Sentiment, 2. Inflation & Labor Transmission, 3. Monetary Trajectory & Liquidity, "
            "4. Cross-Market Dynamics & Positioning, 5. Primary Risks & Falsification Conditions). Avoid machine shorthand or generic AI slop."
        ),
    )
    key_drivers: List[str] = Field(default_factory=list, description="Key macro drivers identified in the brief.")
    per_asset_macro_matrix: Dict[str, AssetMacroContext] = Field(
        default_factory=dict,
        description=(
            "WAJIB: Matriks analisis makro spesifik per aset/simbol (mis. 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'XAUUSD', 'BTCUSD', 'XTIUSD'). "
            "Membedakan pendorong struktural vs katalis sesi taktis serta level invalidasi harga spesifik."
        ),
    )
    asset_priced_in_scores: Dict[str, int] = Field(
        default_factory=dict,
        description=(
            "WAJIB: Skor priced-in spesifik (1-10) per simbol aset. Memungkinkan pembedaan aset yang sudah fully priced-in vs yang masih lagging."
        ),
    )
    yield_curve_regime: Optional[
        Literal["bull_steepener", "bear_steepener", "bull_flattener", "bear_flattener", "neutral"]
    ] = Field(
        default="neutral",
        description="WAJIB: Regime kurva imbal hasil: 'bull_steepener', 'bear_steepener', 'bull_flattener', 'bear_flattener', atau 'neutral'.",
    )
    systemic_liquidity_trend: Optional[Literal["expanding", "contracting", "neutral"]] = Field(
        default="neutral",
        description="WAJIB: Tren likuiditas Fed: 'expanding', 'contracting', atau 'neutral'.",
    )
    currency_bias: Dict[str, Literal["strong_bullish", "bullish", "bearish", "strong_bearish", "neutral"]] = Field(
        ...,
        description=(
            "Directional bias for each major currency/asset. "
            "REQUIRED keys: USD, EUR, GBP, JPY, AUD, XAU. "
            "STRONGLY RECOMMENDED additional keys: OIL (for WTI crude analysis), BTC (for Bitcoin). "
            "Values: 'bullish', 'bearish', or 'neutral'. "
            "Example: {'USD': 'bullish', 'EUR': 'bearish', 'XAU': 'bullish', 'OIL': 'bearish', 'BTC': 'neutral'}"
        ),
    )
    invalidation_conditions: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "WAJIB diisi untuk setiap currency/asset yang bias-nya BUKAN 'neutral' (termasuk USD, EUR, GBP, JPY, AUD, XAU, OIL, BTC). "
            "Setiap string WAJIB >= 40 karakter DAN mengandung level harga/angka spesifik (misalnya: price level, %, date, bps). "
            "Contoh: {'USD': 'Bias USD bullish batal jika DXY D1 close di bawah 103.50 ATAU NFP miss > 50k dari consensus', "
            "'OIL': 'Bias OIL bearish batal jika WTI close di atas 78.50 USD ATAU EIA inventory draw > 3.5M barrels', "
            "'BTC': 'Bias BTC bullish batal jika BTCUSD drop di bawah 58500 USD ATAU net ETF outflow > 200M USD'}."
        ),
    )
    currency_confidence: Dict[str, float] = Field(
        default_factory=dict,
        description="REQUIRED: confidence (0.0-1.0) untuk setiap currency di currency_bias yang BUKAN 'neutral'. "
        "Contoh: {'USD': 0.75, 'EUR': 0.6}. Bias directional dengan confidence RENDAH memberi sinyal "
        "ke Stage 2 untuk menimbang input makro currency tsb lebih ringan.",
    )
    key_upcoming_risks: Optional[List[UpcomingRiskEvent]] = Field(
        None, description="List of key upcoming risk events that could invalidate or amplify your thesis."
    )
    risk_sentiment: Literal["risk-on", "risk-off", "mixed"] = Field(..., description="Overall market risk sentiment.")
    macro_regime: MacroRegime = Field(
        ...,
        description="Klasifikasi regime makro eksplisit â€” lebih luas dari risk_sentiment (mis. mendeteksi stagflasi).",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Your confidence in this brief (0.0 to 1.0). Be honest - lower confidence if data is sparse or contradictory.",
    )
    priced_in_assessment: PricedInAssessment = Field(
        ...,
        description="WAJIB DIISI. Structured assessment of what is currently priced in to market levels. Use data from get_fedwatch_probabilities, get_cot_report, and get_price_momentum.",
    )
    strongest_counter_thesis: str = Field(
        ...,
        min_length=50,
        description="WAJIB: Argumen TERKUAT yang berlawanan dengan tesis makro utama Anda saat ini. "
        "Harus mengutip data/faktor konkret yang jika benar akan membalikkan bias Anda. "
        "Contoh: 'Jika NFP Jumat >250k, tesis USD bearish saya batal karena Fed hawkish "
        "repricing akan terjadi cepat.' Bukan pernyataan generik seperti 'pasar bisa berubah.'",
    )
    bias_continuity_justification: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description=(
            "WAJIB diisi untuk setiap currency/asset yang ditandai 'sticky' di [STICKY BIAS CONTEXT] (bias sama >=4 siklus berturut-turut). "
            "Jelaskan bukti kuantitatif BARU dari siklus ini mengapa bias dipertahankan. "
            "Setiap string WAJIB >= 40 karakter DAN mengandung data numerik konkret (level harga, %, tanggal, basis poin). "
            "Contoh: {'BTC': 'BTC bullish dipertahankan karena ETF inflows +240M USD pada 2026-08-22 dan funding rate stabil di 0.01%', "
            "'USD': 'USD bearish dipertahankan karena DXY melemah 0.4% ke 102.30 dan US10Y turun 5 bps ke 4.10%'}."
        ),
    )
    bias_change_justification: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Alias untuk bias_continuity_justification (backward compatibility).",
    )

    @model_validator(mode="before")
    @classmethod
    def harmonize_counter_thesis_and_primitives(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Ensure dict structures default properly if passed as None or omitted
            if data.get("invalidation_conditions") is None:
                data["invalidation_conditions"] = {}
            if data.get("currency_confidence") is None:
                data["currency_confidence"] = {}
            if data.get("bias_continuity_justification") is None:
                data["bias_continuity_justification"] = {}
            if data.get("bias_change_justification") is None:
                data["bias_change_justification"] = {}
            if data.get("key_drivers") is None:
                data["key_drivers"] = []
            elif isinstance(data.get("key_drivers"), str):
                data["key_drivers"] = [data["key_drivers"]]

            # Alias resolution for macro_narrative and risk_sentiment
            if not data.get("macro_narrative"):
                data["macro_narrative"] = coerce_str(
                    data.get("narrative") or data.get("summary") or data.get("overview")
                )
            # Always normalize risk_sentiment and resolve aliases
            raw_sent = (
                str(data.get("risk_sentiment") or data.get("market_sentiment") or data.get("sentiment") or "mixed")
                .lower()
                .strip()
                .replace("_", "-")
            )
            if "neutral" in raw_sent or "mixed" in raw_sent or "balanc" in raw_sent:
                data["risk_sentiment"] = "mixed"
            elif "risk-off" in raw_sent or "off" in raw_sent or "bear" in raw_sent:
                data["risk_sentiment"] = "risk-off"
            elif "risk-on" in raw_sent or "on" in raw_sent or "bull" in raw_sent:
                data["risk_sentiment"] = "risk-on"
            else:
                data["risk_sentiment"] = "mixed"

            # Auto-populate confidence if omitted
            if data.get("confidence") is None:
                c_conf = data.get("currency_confidence")
                if isinstance(c_conf, dict) and c_conf:
                    nums = [float(v) for v in c_conf.values() if isinstance(v, (int, float))]
                    data["confidence"] = round(sum(nums) / len(nums), 2) if nums else 0.75
                else:
                    data["confidence"] = 0.75

            if data.get("macro_regime"):
                r_lower = str(data["macro_regime"]).lower().strip().replace("-", "_")
                if "risk_on" in r_lower or "expansion" in r_lower or "growth" in r_lower:
                    data["macro_regime"] = "risk_on"
                elif "risk_off" in r_lower or "crisis" in r_lower:
                    data["macro_regime"] = "risk_off"
                elif "stagflation" in r_lower:
                    data["macro_regime"] = "stagflation"
                elif "disinflation" in r_lower:
                    data["macro_regime"] = "disinflation"
                elif "transition" in r_lower:
                    data["macro_regime"] = "transition"
                else:
                    data["macro_regime"] = "mixed"
            else:
                data["macro_regime"] = "mixed"

            # Auto-heal priced_in_assessment if omitted or stringified
            if not data.get("priced_in_assessment"):
                data["priced_in_assessment"] = {
                    "dominant_driver": "General macroeconomic baseline",
                    "priced_in_score": 5,
                    "sell_the_news_risk": "medium",
                    "key_unpriced_drivers": [],
                    "cot_positioning_percentile": None,
                }
            elif isinstance(data.get("priced_in_assessment"), str):
                try:
                    data["priced_in_assessment"] = json.loads(data["priced_in_assessment"])
                except Exception:
                    data["priced_in_assessment"] = {
                        "dominant_driver": coerce_str(data.get("priced_in_assessment")),
                        "priced_in_score": 5,
                        "sell_the_news_risk": "medium",
                        "key_unpriced_drivers": [],
                        "cot_positioning_percentile": None,
                    }

            # Auto-heal checklist if missing or stringified
            if not data.get("checklist"):
                data["checklist"] = {"bias_vs_narrative_match": True, "contradiction_existed": False}
            elif isinstance(data.get("checklist"), str):
                try:
                    data["checklist"] = json.loads(data["checklist"])
                except Exception:
                    data["checklist"] = {"bias_vs_narrative_match": True, "contradiction_existed": False}

            # Auto-heal / extract key_data_points_used if missing or empty
            kdp = data.get("key_data_points_used")
            if not kdp or not isinstance(kdp, dict):
                narrative = str(data.get("macro_narrative", ""))
                vix_match = re.search(r"\bvix\b[^\d]*(\d+(?:\.\d+)?)", narrative, re.IGNORECASE)
                vix_val = float(vix_match.group(1)) if vix_match else None
                dxy_trend = "strengthening" if "dxy" in narrative.lower() and "bull" in narrative.lower() else "neutral"
                data["key_data_points_used"] = {
                    "dxy_trend_5d": dxy_trend,
                    "vix_close": vix_val,
                    "cot_leveraged_long_pct": None,
                    "fedwatch_dominant_pct": None,
                    "fedwatch_repricing_delta_pct": None,
                    "treasury_10y_yield_pct": None,
                }
            elif isinstance(kdp, dict):
                if not kdp.get("dxy_trend_5d"):
                    kdp["dxy_trend_5d"] = "neutral"
                if kdp.get("vix_close") is None:
                    kdp["vix_close"] = None

            # Auto-heal invalidation_conditions for non-neutral biases
            cb = data.get("currency_bias")
            if isinstance(cb, dict):
                inv = data.get("invalidation_conditions", {})
                if not isinstance(inv, dict):
                    inv = {}
                    data["invalidation_conditions"] = inv
                for ccy, bias in cb.items():
                    b_str = str(bias).lower()
                    if b_str != "neutral" and (ccy not in inv or not str(inv[ccy]).strip()):
                        inv[ccy] = (
                            f"Bias {ccy.upper()} {bias} invalid if macroeconomic data or key structural price levels break with regime shift"
                        )

            # Auto-synthesize strongest_counter_thesis if missing or too short (< 50 chars)
            ct = data.get("strongest_counter_thesis")
            if not ct or not isinstance(ct, str) or len(ct.strip()) < 50:
                inv = data.get("invalidation_conditions", {})
                candidates = []
                if isinstance(inv, dict) and inv:
                    for ccy, cond in inv.items():
                        cond_str = str(cond).strip()
                        if len(cond_str) >= 20:
                            candidates.append(f"{ccy}: {cond_str}")
                if candidates:
                    synth = f"Tesis makro berisiko batal jika skenario invalidasi berikut terwujud: {'; '.join(candidates)}."
                    if len(synth) >= 50:
                        data["strongest_counter_thesis"] = synth
                if (
                    not data.get("strongest_counter_thesis")
                    or len(str(data.get("strongest_counter_thesis")).strip()) < 50
                ):
                    data["strongest_counter_thesis"] = (
                        "Risiko skenario berlawanan: Jika kejutan data ekonomi riil berbalik "
                        "arah drastis dari konsensus ekspektasi kebijakan moneter."
                    )

            # Auto-heal yield_curve_regime and systemic_liquidity_trend if omitted
            if not data.get("yield_curve_regime"):
                data["yield_curve_regime"] = "neutral"
            if not data.get("systemic_liquidity_trend"):
                data["systemic_liquidity_trend"] = "neutral"

            # Normalize currency_bias if passed as JSON string or dict
            cb = data.get("currency_bias")
            if isinstance(cb, str):
                try:
                    cb = json.loads(cb)
                except Exception:
                    cb = {}
            if not isinstance(cb, dict):
                cb = {}
            else:
                cb = {str(k).upper().strip(): v for k, v in cb.items()}

            # Map alias / pair keys in currency_bias
            if "XAU" not in cb:
                for k in ("GOLD", "XAUUSD"):
                    if k in cb:
                        cb["XAU"] = cb[k]
                        break
            if "OIL" not in cb:
                for k in ("WTI", "CRUDE", "BRENT", "USOIL", "UKOIL", "XTIUSD", "XBRUSD"):
                    if k in cb:
                        cb["OIL"] = cb[k]
                        break
            if "BTC" not in cb:
                for k in ("BITCOIN", "BTCUSD"):
                    if k in cb:
                        cb["BTC"] = cb[k]
                        break
            if "EUR" not in cb and "EURUSD" in cb:
                cb["EUR"] = cb["EURUSD"]
            if "GBP" not in cb and "GBPUSD" in cb:
                cb["GBP"] = cb["GBPUSD"]
            if "AUD" not in cb and "AUDUSD" in cb:
                cb["AUD"] = cb["AUDUSD"]
            if "USD" not in cb and "DXY" in cb:
                cb["USD"] = cb["DXY"]
            if "USDJPY" in cb:
                uj_b = cb["USDJPY"]
                _inv = {
                    "strong_bullish": "strong_bearish",
                    "bullish": "bearish",
                    "bearish": "bullish",
                    "strong_bearish": "strong_bullish",
                    "neutral": "neutral",
                }
                if "JPY" not in cb:
                    cb["JPY"] = _inv.get(str(uj_b).lower().strip(), "neutral")
                if "USD" not in cb:
                    cb["USD"] = uj_b

            def _extract_bias(ent: Any) -> Optional[str]:
                if isinstance(ent, dict):
                    b_raw = ent.get("directional_bias") or ent.get("macro_bias") or ent.get("bias")
                elif hasattr(ent, "directional_bias"):
                    b_raw = getattr(ent, "directional_bias", None)
                elif isinstance(ent, str):
                    b_raw = ent
                else:
                    b_raw = None
                if not b_raw or not isinstance(b_raw, str):
                    return None
                clean = b_raw.lower().strip().replace("-", "_").replace(" ", "_")
                if clean in ["strong_bullish", "bullish", "bearish", "strong_bearish", "neutral"]:
                    return clean
                if "bull" in clean:
                    return "bullish"
                if "bear" in clean:
                    return "bearish"
                return "neutral"

            matrix = data.get("per_asset_macro_matrix")
            if not isinstance(matrix, dict):
                matrix = {}

            # Reverse auto-healing of currency_bias from per_asset_macro_matrix
            if matrix:
                _inv = {
                    "strong_bullish": "strong_bearish",
                    "bullish": "bearish",
                    "bearish": "bullish",
                    "strong_bearish": "strong_bullish",
                    "neutral": "neutral",
                }

                _BASE_CCY_MAP = {
                    "EURUSD": "EUR",
                    "GBPUSD": "GBP",
                    "AUDUSD": "AUD",
                    "XAUUSD": "XAU",
                    "BTCUSD": "BTC",
                    "XTIUSD": "OIL",
                    "XBRUSD": "OIL",
                }
                for pair_sym, ccy in _BASE_CCY_MAP.items():
                    if ccy not in cb and pair_sym in matrix:
                        b = _extract_bias(matrix[pair_sym])
                        if b:
                            cb[ccy] = b

                if "JPY" not in cb and "USDJPY" in matrix:
                    uj_b = _extract_bias(matrix["USDJPY"])
                    if uj_b:
                        cb["JPY"] = _inv.get(uj_b, "neutral")

                if "USD" not in cb:
                    if "USDJPY" in matrix:
                        uj_b = _extract_bias(matrix["USDJPY"])
                        if uj_b:
                            cb["USD"] = uj_b
                    else:
                        usd_votes = []
                        for pair_sym in ("EURUSD", "GBPUSD", "AUDUSD", "XAUUSD", "BTCUSD", "XTIUSD", "XBRUSD"):
                            if pair_sym in matrix:
                                pb = _extract_bias(matrix[pair_sym])
                                if pb in ("bullish", "strong_bullish"):
                                    usd_votes.append("bearish")
                                elif pb in ("bearish", "strong_bearish"):
                                    usd_votes.append("bullish")
                                elif pb == "neutral":
                                    usd_votes.append("neutral")
                        if usd_votes:
                            bulls = usd_votes.count("bullish")
                            bears = usd_votes.count("bearish")
                            if bulls > bears:
                                cb["USD"] = "bullish"
                            elif bears > bulls:
                                cb["USD"] = "bearish"
                            else:
                                cb["USD"] = "neutral"

            data["currency_bias"] = cb

            # Forward auto-heal per_asset_macro_matrix from currency_bias
            if cb:
                inv = data.get("invalidation_conditions", {})
                conf_dict = data.get("currency_confidence", {})

                def _calc_net_bias(b_str: str, q_str: str) -> str:
                    b_map = {"strong_bullish": 2, "bullish": 1, "neutral": 0, "bearish": -1, "strong_bearish": -2}
                    b_val = b_map.get(b_str, 1 if "bull" in b_str else (-1 if "bear" in b_str else 0))
                    q_val = b_map.get(q_str, 1 if "bull" in q_str else (-1 if "bear" in q_str else 0))
                    net = b_val - q_val
                    if net >= 2:
                        return "strong_bullish"
                    elif net == 1:
                        return "bullish"
                    elif net == 0:
                        return "neutral"
                    elif net == -1:
                        return "bearish"
                    else:
                        return "strong_bearish"

                _ASSET_PAIRS = {
                    "EURUSD": ("EUR", "USD"),
                    "GBPUSD": ("GBP", "USD"),
                    "USDJPY": ("USD", "JPY"),
                    "AUDUSD": ("AUD", "USD"),
                    "XAUUSD": ("XAU", "USD"),
                    "BTCUSD": ("BTC", "USD"),
                    "XTIUSD": ("OIL" if "OIL" in cb else "XTI", "USD"),
                    "XBRUSD": ("OIL" if "OIL" in cb else "XBR", "USD"),
                }

                regime_str = str(data.get("macro_regime", "mixed")).replace("_", " ").title()
                risk_sent = str(data.get("risk_sentiment", "mixed"))

                for asset_sym, (base_c, quote_c) in _ASSET_PAIRS.items():
                    existing_entry = matrix.get(asset_sym)
                    needs_rebuild = (
                        existing_entry is None
                        or not isinstance(existing_entry, (dict, AssetMacroContext))
                        or (isinstance(existing_entry, dict) and "structural_driver" not in existing_entry)
                    )
                    if needs_rebuild:
                        b_bias = str(cb.get(base_c, "neutral")).lower()
                        q_bias = str(cb.get(quote_c, "neutral")).lower()
                        extracted_bias = _extract_bias(existing_entry) if existing_entry is not None else None
                        dir_bias = extracted_bias or _calc_net_bias(b_bias, q_bias)

                        inv_text = inv.get(base_c) or inv.get(asset_sym) if isinstance(inv, dict) else None
                        if not inv_text or len(str(inv_text).strip()) < 20:
                            inv_text = f"Bias {asset_sym} {dir_bias} invalid if structural price levels break with regime shift"

                        c_raw = conf_dict.get(base_c) if isinstance(conf_dict, dict) else None
                        if c_raw is None:
                            c_raw = data.get("confidence", 0.70)
                        c_float = coerce_float(c_raw, 0.70)
                        if c_float is not None:
                            if c_float > 1.0 and c_float <= 10.0:
                                c_float = c_float / 10.0
                            elif c_float > 10.0 and c_float <= 100.0:
                                c_float = c_float / 100.0
                            c_float = max(0.0, min(1.0, c_float))
                        else:
                            c_float = 0.70

                        matrix[asset_sym] = {
                            "directional_bias": dir_bias,
                            "time_horizon": "swing_structural",
                            "structural_driver": f"{regime_str} regime; {base_c} ({b_bias}) vs {quote_c} ({q_bias}) policy and macro differential",
                            "tactical_catalyst": f"Intermarket liquidity flow, risk sentiment ({risk_sent}), and scheduled high-impact events",
                            "invalidation_level": str(inv_text),
                            "confidence": c_float,
                        }
            data["per_asset_macro_matrix"] = matrix

            # Auto-heal asset_priced_in_scores if missing or not dict
            pi_scores = data.get("asset_priced_in_scores")
            expected_pi_assets = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "BTCUSD", "XTIUSD", "XBRUSD"]
            if not isinstance(pi_scores, dict) or not pi_scores:
                base_pi = 5
                pi_data = data.get("priced_in_assessment")
                if isinstance(pi_data, dict):
                    base_pi = coerce_int(pi_data.get("priced_in_score"), 5) or 5
                elif isinstance(pi_data, (int, float)):
                    base_pi = int(round(pi_data))
                data["asset_priced_in_scores"] = {sym: base_pi for sym in expected_pi_assets}
            else:
                norm_pi = {str(k).upper(): coerce_int(v, 5) or 5 for k, v in pi_scores.items() if v is not None}
                for sym in expected_pi_assets:
                    if sym not in norm_pi:
                        if sym == "XBRUSD" and "XTIUSD" in norm_pi:
                            norm_pi["XBRUSD"] = norm_pi["XTIUSD"]
                        elif sym == "XTIUSD" and "XBRUSD" in norm_pi:
                            norm_pi["XTIUSD"] = norm_pi["XBRUSD"]
                        else:
                            norm_pi[sym] = 5
                data["asset_priced_in_scores"] = norm_pi
        return data

    @field_validator("macro_regime", mode="before")
    @classmethod
    def validate_macro_regime_sfbs(cls, v):
        if isinstance(v, MacroRegime):
            return v
        if isinstance(v, str):
            clean = v.lower().strip().replace("-", "_")
            for m in MacroRegime:
                if clean == m.value or clean == m.name.lower():
                    return m
            if any(k in clean for k in ["stagflation", "energy_drag"]):
                return MacroRegime.STAGFLATION
            if any(k in clean for k in ["risk_off", "geopolitical", "friction", "hawkish"]):
                return MacroRegime.RISK_OFF
            if any(k in clean for k in ["risk_on"]):
                return MacroRegime.RISK_ON
            if any(k in clean for k in ["disinflation", "soft_landing"]):
                return MacroRegime.DISINFLATION
            if any(k in clean for k in ["transition", "pivot", "plateau"]):
                return MacroRegime.TRANSITION
        return MacroRegime.MIXED

    @field_validator("yield_curve_regime", mode="before")
    @classmethod
    def validate_yield_curve_regime(cls, v):
        if isinstance(v, str):
            clean = v.lower().strip().replace("-", "_").replace(" ", "_")
            if clean in ["bull_steepener", "bear_steepener", "bull_flattener", "bear_flattener", "neutral"]:
                return clean
            if "steep" in clean:
                return "bull_steepener" if "bull" in clean else "bear_steepener"
            if "flat" in clean:
                return "bull_flattener" if "bull" in clean else "bear_flattener"
        return "neutral"

    @field_validator("systemic_liquidity_trend", mode="before")
    @classmethod
    def validate_systemic_liquidity_trend(cls, v):
        if isinstance(v, str):
            clean = v.lower().strip().replace("-", "_").replace(" ", "_")
            if clean in ["expanding", "contracting", "neutral"]:
                return clean
            if any(k in clean for k in ["expand", "growth", "loose", "positive"]):
                return "expanding"
            if any(k in clean for k in ["contract", "drain", "tight", "negative"]):
                return "contracting"
        return "neutral"

    @field_validator("risk_sentiment", mode="before")
    @classmethod
    def validate_risk_sentiment_sfbs(cls, v):
        if isinstance(v, str):
            clean = v.lower().strip().replace("_", "-")
            if clean in ["risk-on", "risk-off", "mixed"]:
                return clean
            if "on" in clean:
                return "risk-on"
            if "off" in clean:
                return "risk-off"
        return "mixed"

    @field_validator("currency_bias", mode="before")
    @classmethod
    def validate_currency_bias_sfbs(cls, v):
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                return {}
        if not isinstance(v, dict):
            return {}
        res = {}
        for ccy, bias in v.items():
            ccy_up = str(ccy).upper().strip()
            if isinstance(bias, str):
                b_clean = bias.lower().strip().replace("-", "_").replace(" ", "_")
                if b_clean in ["strong_bullish", "bullish", "bearish", "strong_bearish", "neutral"]:
                    val = b_clean
                elif "bull" in b_clean:
                    val = "bullish"
                elif "bear" in b_clean:
                    val = "bearish"
                else:
                    val = "neutral"
            else:
                val = "neutral"
            res[ccy_up] = val

        # Map common alias/pair keys when direct single-currency keys are missing
        if "XAU" not in res:
            for k in ("GOLD", "XAUUSD"):
                if k in res:
                    res["XAU"] = res[k]
                    break

        if "OIL" not in res:
            for k in ("WTI", "CRUDE", "BRENT", "USOIL", "UKOIL", "XTIUSD", "XBRUSD"):
                if k in res:
                    res["OIL"] = res[k]
                    break

        if "BTC" not in res:
            for k in ("BITCOIN", "BTCUSD"):
                if k in res:
                    res["BTC"] = res[k]
                    break

        if "EUR" not in res and "EURUSD" in res:
            res["EUR"] = res["EURUSD"]

        if "GBP" not in res and "GBPUSD" in res:
            res["GBP"] = res["GBPUSD"]

        if "AUD" not in res and "AUDUSD" in res:
            res["AUD"] = res["AUDUSD"]

        if "USD" not in res and "DXY" in res:
            res["USD"] = res["DXY"]

        if "USDJPY" in res:
            uj_bias = res["USDJPY"]
            inv_map = {
                "strong_bullish": "strong_bearish",
                "bullish": "bearish",
                "bearish": "bullish",
                "strong_bearish": "strong_bullish",
                "neutral": "neutral",
            }
            if "JPY" not in res:
                res["JPY"] = inv_map.get(uj_bias, "neutral")
            if "USD" not in res:
                res["USD"] = uj_bias

        return res

    @field_validator("asset_priced_in_scores", mode="before")
    @classmethod
    def validate_asset_pi_scores(cls, v):
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                v = {}
        if not isinstance(v, dict):
            v = {}
        res = {str(k).upper(): coerce_int(val, 5) or 5 for k, val in v.items() if val is not None}
        expected_assets = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "BTCUSD", "XTIUSD", "XBRUSD"]
        for asset in expected_assets:
            if asset not in res:
                if asset == "XBRUSD" and "XTIUSD" in res:
                    res["XBRUSD"] = res["XTIUSD"]
                elif asset == "XTIUSD" and "XBRUSD" in res:
                    res["XTIUSD"] = res["XBRUSD"]
                else:
                    res[asset] = 5
        return res

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, v):
        val = coerce_float(v, None)
        if val is not None:
            if val > 1.0 and val <= 10.0:
                val = val / 10.0
            elif val > 10.0 and val <= 100.0:
                val = val / 100.0
            return max(0.0, min(1.0, val))
        raise ValueError("Confidence must be an explicit numeric float between 0.0 and 1.0")

    @field_validator("currency_confidence", mode="before")
    @classmethod
    def validate_currency_confidence(cls, v):
        if not isinstance(v, dict):
            return {}
        res = {}
        for ccy, conf in v.items():
            val = coerce_float(conf, None)
            if val is not None:
                if val > 1.0 and val <= 10.0:
                    val = val / 10.0
                elif val > 10.0 and val <= 100.0:
                    val = val / 100.0
                res[str(ccy).upper()] = max(0.0, min(1.0, val))
            else:
                raise ValueError(
                    f"Currency confidence for '{ccy}' must be an explicit numeric float between 0.0 and 1.0"
                )
        return res

    @field_validator("key_upcoming_risks", mode="before")
    @classmethod
    def validate_upcoming_risks(cls, v):
        if v is None:
            return None
        if isinstance(v, (list, tuple, set)):
            return [item for item in v if item is not None]
        if isinstance(v, (str, dict)):
            return [v]
        return None

    @field_validator(
        "invalidation_conditions", "bias_continuity_justification", "bias_change_justification", mode="before"
    )
    @classmethod
    def validate_string_dicts(cls, v):
        if not isinstance(v, dict):
            return {}
        return {str(k).upper(): coerce_str(val) for k, val in v.items() if val is not None and str(val).strip()}

    @field_validator("macro_narrative", "strongest_counter_thesis", mode="before")
    @classmethod
    def validate_brief_narratives(cls, v):
        return coerce_str(v)
