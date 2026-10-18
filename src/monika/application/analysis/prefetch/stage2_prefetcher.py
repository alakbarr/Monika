# ==============================================================================
# File: analysis/stage2_prefetcher.py
# ==============================================================================

"""
Stage 2 Data Bundler (Prefetcher).

Fungsi: Menarik data teknikal dasar (SMC, OHLCV, dll.) sebelum AI Stage 2 berjalan.
Tujuan: Menghemat token & waktu dengan mengubah belasan panggilan tool menjadi satu teks ringkasan (bundle).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy.ext.asyncio import AsyncSession

import monika.core.primitives.clock as clock
from monika.application.analysis.calculators.confluence_calculator import (
    calculate_confluence,
    calculate_priced_in_subscores,
)
from monika.application.analysis.tools.tool_executor import ToolExecutor

logger = logging.getLogger("TradingAgent.Stage2Prefetcher")

# Tool yang akan di pre-fetch
# Ini mencakup alur Tahap 2 standar yang biasanya dipanggil manual oleh model
STANDARD_FETCH_TASKS = [
    ("get_fundamental_brief", {}),
    ("get_market_session", {}),
    ("get_dxy", {"days_back": 5}),
    ("get_vix", {"days_back": 5}),
    ("get_open_positions", {}),
    ("get_risk_state", {}),
    ("get_economic_calendar", {"impact_filter": "high_and_medium", "hours_ahead": 168, "hours_behind": 24}),
]

SYMBOL_FETCH_TASKS = [
    # (tool_name, extra_inp) — symbol will be injected
    ("get_technical_indicators", {"timeframe": "D1"}),
    ("get_technical_indicators", {"timeframe": "H4"}),
    ("get_technical_indicators", {"timeframe": "H1"}),
    ("get_technical_indicators", {"timeframe": "M15"}),
    ("get_atr", {"timeframe": "H4"}),
    ("get_price_history", {"timeframe": "H4", "limit": 25}),
    ("get_price_history", {"timeframe": "H1", "limit": 24}),
    ("get_price_history", {"timeframe": "M15", "limit": 20}),
    ("get_swing_points", {"timeframe": "D1", "limit": 4}),
    ("get_swing_points", {"timeframe": "H4", "limit": 6}),
    ("get_swing_points", {"timeframe": "M15", "limit": 6}),
    ("get_structure_breaks", {"timeframe": "D1"}),
    ("get_structure_breaks", {"timeframe": "H4"}),
    ("get_structure_breaks", {"timeframe": "M15"}),
    ("get_smc_zones", {"timeframe": "H4"}),
    ("get_smc_zones", {"timeframe": "M15"}),
    ("get_fibonacci_levels", {"timeframe": "H4"}),
    ("get_liquidity_sweep_context", {}),
    ("get_macro_bias_score", {}),
    ("get_volume_profile_context", {}),
    ("get_volatility_regime", {"timeframe": "H4"}),
]


class Stage2DataBundler:
    """Engine penyusun (bundler) data teknikal untuk 1 simbol ke dalam format teks tunggal."""

    _PRICE_PRECISION = {
        "EURUSD": 5,
        "GBPUSD": 5,
        "AUDUSD": 5,
        "NZDUSD": 5,
        "USDCAD": 5,
        "USDCHF": 5,
        "USDJPY": 3,
        "EURJPY": 3,
        "GBPJPY": 3,
        "AUDJPY": 3,
        "XAUUSD": 2,
        "XAGUSD": 3,
        "XTIUSD": 3,
        "XBRUSD": 3,
        "BTCUSD": 1,
        "ETHUSD": 2,
    }

    def __init__(self, session: AsyncSession, settings: Optional[dict] = None):
        self.settings = settings or {}
        self.executor = ToolExecutor(session, self.settings)

    def _compress_history(self, history: Any, symbol: Optional[str] = None) -> str:
        """Kompresi data OHLCV menjadi teks yang sangat ringkas dengan presisi dinamis."""
        if not history:
            return ""

        bars: list = []
        sym: str = symbol or ""
        if isinstance(history, list):
            bars = history
        elif isinstance(history, dict):
            bars = history.get("bars", [])
            sym = symbol or history.get("symbol", "")
        else:
            return ""

        if not bars or not isinstance(bars, list):
            return ""

        prec = self._PRICE_PRECISION.get(sym, 5 if "USD" in sym and sym not in ("XAUUSD", "BTCUSD") else 4)

        # Gunakan format CSV minimal: time,O,H,L,C,V
        lines = ["time,O,H,L,C,V"]
        for b in bars[-30:]:  # Batasi 30 bar terakhir
            if not isinstance(b, dict):
                continue
            raw_t = str(b.get("time", ""))
            if "T" in raw_t:
                parts = raw_t.split("T")
                t = parts[0][5:] + " " + parts[1][:5]
            elif " " in raw_t:
                parts = raw_t.split(" ")
                t = parts[0][5:] + " " + parts[1][:5]
            else:
                t = raw_t[-11:]

            try:
                o = float(b.get("open", 0.0))
                h = float(b.get("high", 0.0))
                l = float(b.get("low", 0.0))
                c = float(b.get("close", 0.0))
                v = int(b.get("tick_volume", b.get("volume", 0)))
                lines.append(f"{t},{o:.{prec}f},{h:.{prec}f},{l:.{prec}f},{c:.{prec}f},{v}")
            except Exception:
                continue

        return "\n".join(lines)

    def _format_technical_readable(self, value: dict) -> str:
        """Format indicators as human-readable summary with direction/delta context."""
        if not isinstance(value, dict):
            return self._compress_json(value)
        indicators = value.get("indicators", value)
        if not isinstance(indicators, dict):
            return self._compress_json(value)

        lines = []
        tf = value.get("timeframe", "")
        ts = value.get("timestamp", "")
        if ts:
            lines.append(f"Snapshot ({tf}): {ts}")

        for name, item in indicators.items():
            if not isinstance(item, dict):
                lines.append(f"• {name}: {item}")
                continue

            val = item.get("value")
            prev = item.get("prev")
            direction = item.get("direction")
            arrow = "▲" if direction == "rising" else "▼" if direction == "falling" else "→"
            dir_str = f" [{arrow} {direction}]" if direction else ""

            series = item.get("series")
            series_str = ""
            if series and isinstance(series, list) and len(series) > 1:
                if all(isinstance(s, (int, float)) for s in series):
                    compact_s = [str(s) for s in series[-10:]]
                    series_str = f" | {len(series)}-bar trend: [{', '.join(compact_s)}]"
                elif all(isinstance(s, dict) for s in series):
                    k0 = next(iter(series[0].keys()), "")
                    if k0:
                        compact_s = [f"{s.get(k0)}" for s in series[-10:]]
                        series_str = f" | {len(series)}-bar {k0}: [{', '.join(compact_s)}]"

            if isinstance(val, dict):
                parts = []
                for k, v in val.items():
                    if v is not None:
                        parts.append(f"{k}={v}")
                lines.append(f"• {name}: {', '.join(parts)}{dir_str}{series_str}")
            elif isinstance(val, (int, float)):
                prev_str = f" (prev: {prev})" if prev is not None else ""
                lines.append(f"• {name}: {val}{prev_str}{dir_str}{series_str}")
            else:
                lines.append(f"• {name}: {val}{dir_str}{series_str}")

        return "\n".join(lines)

    def _compress_json(self, data: dict) -> str:
        """Hapus whitespace dan key yang tidak penting."""
        if not data:
            return "{}"

        try:
            import re

            data_str = json.dumps(data, separators=(",", ":"))
            # Hapus milidetik dan zone offset
            data_str = re.sub(r"T(\d{2}:\d{2}):\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?", r" \1", data_str)
            return data_str
        except Exception:
            return json.dumps(data, separators=(",", ":"))

    def _check_bundle_freshness(self, data: dict, now: datetime) -> list[str]:
        """Validate timestamps of fetched data."""
        warnings = []
        is_forex_closed = False
        try:
            from monika.core.validation.data_validator import is_forex_market_closed

            is_forex_closed = is_forex_market_closed(now)
        except Exception:
            pass

        # Monday morning D1 tolerance: Friday close bar is ~72-84h old
        d1_max_age = 84.0 if now.weekday() == 0 else 36.0
        check_configs = [("M15", 1.5), ("H1", 3.0), ("H4", 6.0), ("D1", d1_max_age)]

        for check_tf, max_age_hours in check_configs:
            ohlcv_key = (
                f"get_price_history_{check_tf}"
                if f"get_price_history_{check_tf}" in data
                else (f"price_history_{check_tf}_recent" if f"price_history_{check_tf}_recent" in data else None)
            )
            if ohlcv_key and ohlcv_key in data:
                raw_entry = data[ohlcv_key]
                bars = (
                    raw_entry.get("bars", [])
                    if isinstance(raw_entry, dict)
                    else (raw_entry if isinstance(raw_entry, list) else [])
                )
                if bars and isinstance(bars[-1], dict):
                    last_bar_time_str = bars[-1].get("time", "")
                    try:
                        last_bar_time = datetime.fromisoformat(last_bar_time_str.replace("Z", "+00:00"))
                        if last_bar_time.tzinfo is None:
                            last_bar_time = last_bar_time.replace(tzinfo=timezone.utc)
                        age_hours = (now - last_bar_time).total_seconds() / 3600
                        # Skip staleness warning if market is closed (weekend) for non-crypto
                        if age_hours > max_age_hours and not is_forex_closed:
                            warnings.append(
                                f"[PERINGATAN] {check_tf} OHLCV last bar is {age_hours:.1f}h old "
                                f"(limit={max_age_hours}h) — MT5 may be disconnected!"
                            )
                    except Exception:
                        pass
        return warnings

    async def fetch_bundle(self, symbol: str, cot_code: Optional[str] = None) -> tuple[str, dict]:
        """Menarik seluruh dataset yang dibutuhkan dan memformatnya menjadi string konteks. Mengembalikan `("", {})` jika gagal total."""
        if not cot_code:
            from monika.domain.market.instrument_identity import KNOWN_INSTRUMENTS

            inst = KNOWN_INSTRUMENTS.get(symbol)
            if inst and inst.cot_code and inst.asset_class != "CRYPTO":
                cot_code = inst.cot_code

        # NEW: Validate core shared data first (SSVP insight)
        core_data_issues = []
        core_is_valid = True
        try:
            from monika.application.analysis.validators.core_data_validator import CoreDataValidator

            validator = CoreDataValidator(self.executor.session, self.settings or self.executor.settings or {})
            core_is_valid, core_data, issues = await validator.validate_and_fetch_core_data()
            if issues:
                core_data_issues = issues
            if not core_is_valid:
                dxy_or_vix_fatal = any("implausible" in iss and ("DXY" in iss or "VIX" in iss) for iss in issues)
                if dxy_or_vix_fatal:
                    logger.error(f"[{symbol}] Core market data invalid: {issues}. Fetch bundle aborted.")
                    return (
                        f"[PERINGATAN] CORE DATA INVALID: {'; '.join(issues)}\nPlease WAIT until data is resolved.",
                        {},
                    )
                else:
                    logger.warning(
                        f"[{symbol}] Core data validation issues: {issues}. Continuing bundle generation in degraded mode."
                    )
        except Exception as e:
            logger.debug(f"CoreDataValidator failed (non-fatal): {e}")

        # Validate pipeline data freshness
        freshness_warnings = []
        try:
            from monika.core.validation.data_validator import validate_data_freshness

            freshness = await validate_data_freshness(
                self.executor.session, [symbol], ["M15", "H1", "H4", "D1"], require_macro_data=False
            )
            if not freshness.get("ready", True):
                freshness_warnings = freshness.get("errors", []) + freshness.get("warnings", [])
            elif freshness.get("warnings"):
                freshness_warnings = freshness.get("warnings", [])
        except Exception as e:
            logger.debug(f"Data freshness check failed (non-fatal): {e}")

        data = {}
        if core_data_issues:
            data["core_data_warnings"] = core_data_issues
            if not core_is_valid:
                data["core_data_critical_warnings"] = core_data_issues
        if freshness_warnings:
            data["data_freshness_warnings"] = freshness_warnings
        fetch_errors = []

        # Task standar (tidak perlu spesifik simbol)
        for tool_name, inp in STANDARD_FETCH_TASKS:
            inp = dict(inp)
            try:
                result = await self.executor.execute(tool_name, inp)
                if "error" not in result:
                    data[tool_name] = result
            except Exception as e:
                fetch_errors.append(f"{tool_name}: {str(e)[:40]}")

        for tool_name, extra_inp in SYMBOL_FETCH_TASKS:
            inp = {"symbol": symbol, **extra_inp}
            tf = extra_inp.get("timeframe")
            task_key = f"{tool_name}_{tf}" if tf else tool_name
            try:
                result = await self.executor.execute(tool_name, inp)
                if "error" not in result:
                    data[task_key] = result
            except Exception as e:
                fetch_errors.append(f"{task_key}: {str(e)[:40]}")

        # D1 price history untuk seluruh aset (pola mingguan dan struktur makro)
        try:
            result = await self.executor.execute(
                "get_price_history", {"symbol": symbol, "timeframe": "D1", "limit": 40}
            )
            if "error" not in result:
                data["price_history_D1_recent"] = result
        except Exception as e:
            fetch_errors.append(f"price_history_D1: {str(e)[:40]}")

        # IMP-3: Market regime detection
        try:
            regime_result = await self.executor.execute("get_market_regime", {"symbols": [symbol], "timeframe": "D1"})
            if "error" not in regime_result:
                data["market_regime"] = regime_result
        except Exception as e:
            fetch_errors.append(f"market_regime: {str(e)[:40]}")

        # Always fetch both D1 structure breaks and SMC zones for macro structural context
        try:
            r_sb = await self.executor.execute("get_structure_breaks", {"symbol": symbol, "timeframe": "D1"})
            if "error" not in r_sb:
                data["structure_breaks_D1"] = r_sb
        except Exception as e:
            logger.debug(f"[{symbol}] Failed to fetch structure_breaks_D1: {e}")

        try:
            r_smc = await self.executor.execute("get_smc_zones", {"symbol": symbol, "timeframe": "D1"})
            if "error" not in r_smc:
                data["smc_zones_D1"] = r_smc
        except Exception as e:
            logger.debug(f"[{symbol}] Failed to fetch smc_zones_D1: {e}")

        # Task 2.2: Add asset-specific sentiment tools
        try:
            if symbol == "BTCUSD":
                res1 = await self.executor.execute("get_fear_greed_index", {})
                if "error" not in res1:
                    data["fear_greed_index"] = res1
                res2 = await self.executor.execute("get_funding_rate", {"symbol": "BTC"})
                if "error" not in res2:
                    data["funding_rate"] = res2
                res3 = await self.executor.execute("get_retail_sentiment", {"symbol": "BTCUSD"})
                if "error" not in res3:
                    data["binance_sentiment"] = res3
            elif symbol in ("XTIUSD", "XBRUSD"):
                res = await self.executor.execute("get_fxssi_sentiment", {"symbol": symbol})
                if "error" not in res:
                    data["fxssi_sentiment"] = res
                res_eia = await self.executor.execute("get_eia_oil_inventory", {})
                if "error" not in res_eia:
                    data["eia_oil_inventory"] = res_eia
            elif symbol not in ("BTCUSD", "XTIUSD", "XBRUSD"):
                res = await self.executor.execute("get_retail_sentiment", {"symbol": symbol})
                if "error" not in res:
                    data["retail_sentiment"] = res
        except Exception as e:
            fetch_errors.append(f"asset_sentiment: {str(e)[:40]}")

        # Data COT (opsional)
        if cot_code:
            try:
                result = await self.executor.execute("get_cot_report", {"market_codes": [cot_code]})
                if "error" not in result:
                    data["cot_report"] = result
            except Exception as e:
                fetch_errors.append(f"cot_report: {str(e)[:40]}")

        try:
            from monika.application.protocol.context_coherence import get_base_quote_tags

            currency_filter = get_base_quote_tags(symbol)
            news_res = await self.executor.execute(
                "get_news_items",
                {
                    "currency": currency_filter,
                    "currency_filter": currency_filter,
                    "symbol": symbol,
                    "hours_back": 12,
                    "limit": 8,
                },
            )
            if "error" not in news_res:
                import textwrap
                import unicodedata

                compact_news = []
                raw_items = news_res.get("news") or news_res.get("items") or news_res.get("news_items") or []
                for n in raw_items[:8]:
                    import html as _html
                    import re as _re

                    raw_str = unicodedata.normalize("NFKC", str(n.get("title", "")))
                    cleaned_title = _re.sub(
                        r"<\/?untrusted_external_content[^>]*>", "", raw_str, flags=_re.IGNORECASE
                    ).strip()
                    escaped_title = _html.escape(cleaned_title)
                    short_title = (
                        textwrap.shorten(escaped_title, width=150, placeholder="...")
                        if len(escaped_title) > 150
                        else escaped_title
                    )
                    safe_title = f"<untrusted_external_content>{short_title}</untrusted_external_content>"
                    compact_news.append(
                        {
                            "title": safe_title,
                            "sentiment_tags": n.get("currency_tags", ""),
                            "source": n.get("source", ""),
                        }
                    )
                data["recent_news"] = {"count": len(compact_news), "items": compact_news}
        except Exception as e:
            fetch_errors.append(f"recent_news: {str(e)[:40]}")

        # TimesFM 3.0 Multivariate Forecast fetch
        try:
            from monika.infrastructure.ml.timesfm_engine import TimesFMEngine

            tfm_engine = TimesFMEngine(self.settings)
            tfm_fc = await tfm_engine.get_latest_forecast(
                self.executor.session, symbol, timeframe="H1", max_age_hours=8.0
            )
            if tfm_fc:
                data["timesfm_forecast"] = tfm_fc
        except Exception as e:
            fetch_errors.append(f"timesfm_forecast: {str(e)[:40]}")

        if fetch_errors:
            logger.warning(f"[{symbol}] Stage2 fetch errors: {', '.join(fetch_errors)}")

        if not data:
            logger.warning(f"[{symbol}] Stage2 pre-bundle completely failed — AI will use tools")
            return "", {}

        # Setelah fetch, periksa apakah data OHLCV usang (stale)
        now = clock.now()
        staleness_warnings = self._check_bundle_freshness(data, now)

        # Format ke dalam bundel yang mudah dibaca (clean markdown tanpa unicode box-drawing overhead)
        ts = now.strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"### PRE-FETCHED DATA BUNDLE: {symbol}",
            "TEMPORAL CONSISTENCY LOCK: All data below fetched in consistent cycle window. DO NOT re-fetch existing types.",
            "",
        ]

        if staleness_warnings:
            lines.append("── DATA STALENESS WARNINGS ──")
            lines.extend(staleness_warnings)
            lines.append("Consider calling get_price_history manually to check, or use WAIT decision.")
            lines.append("")

        # Phase 5: Bypass data coherence check if cost_mode is 'lite'
        settings = self.executor.settings if hasattr(self.executor, "settings") else {}
        cost_mode = settings.get("trading", {}).get("cost_mode", "standard")

        if cost_mode != "lite":
            from monika.core.validation.data_validator import check_data_coherence

            active_settings = self.settings or settings or {}
            coherence = await check_data_coherence(
                self.executor.session,
                symbol,
                max_ohlcv_age_hours=active_settings.get("data_quality", {}).get("max_ohlcv_age_hours"),
                max_indicator_age_hours=active_settings.get("data_quality", {}).get("max_indicator_age_hours"),
            )

            if not coherence["coherent"]:
                coherence_warning = "[PERINGATAN] DATA COHERENCE ISSUES DETECTED:\n"
                for issue in coherence["issues"]:
                    coherence_warning += f"  • {issue}\n"
                coherence_warning += "Consider submitting WAIT decision until data is refreshed.\n"
                lines.append("── DATA COHERENCE CHECK ──")
                lines.append(coherence_warning)
                lines.append("")
        else:
            lines.append("── DATA COHERENCE CHECK (BYPASSED - LITE MODE) ──\n")

        # IMP-10: Temporal consistency check
        try:
            from monika.core.validation.data_temporal_validator import DataTemporalValidator

            temporal_warning = await DataTemporalValidator.validate_and_warn(self.executor.session, symbol)
            if temporal_warning:
                lines.append("── TEMPORAL DATA COHERENCE ──")
                lines.append(temporal_warning)
                lines.append("")
        except Exception as e:
            logger.debug(f"Temporal validation failed (non-fatal): {e}")
        # === CROSS-DATA COHERENCE CHECK (SSVP-inspired) ===
        try:
            from monika.application.protocol.context_coherence import compute_bundle_coherence_issues

            coherence_issues = compute_bundle_coherence_issues(data)
            if coherence_issues:
                lines.append("── [PERINGATAN]  CROSS-DATA COHERENCE ALERTS (READ BEFORE PROCEEDING) ──")
                lines.append("These contradictions were detected across multiple data sources in this bundle.")
                lines.append("You MUST explicitly address each one before submitting your final decision.")
                lines.append("")
                for i, issue in enumerate(coherence_issues, 1):
                    lines.append(f"  ALERT {i}: {issue}")
                lines.append("")
                lines.append(
                    "Resolution options: (A) Trust the more current/specific source, "
                    "(B) WAIT for contradiction to resolve, (C) Apply strict interpretation."
                )
                lines.append("Do NOT proceed to submit BUY/SELL with unresolved coherence alerts.")
                lines.append("")
        except Exception as _coh_err:
            logger.debug(f"Bundle coherence check failed (non-fatal): {_coh_err}")
        # === END COHERENCE CHECK ===

        # Multi-timeframe trend alignment summary
        d1_ind = data.get("get_technical_indicators_D1", {}).get("indicators", {})
        h4_ind = data.get("get_technical_indicators_H4", {}).get("indicators", {})
        if d1_ind or h4_ind:
            lines.append("── MULTI-TIMEFRAME TREND ALIGNMENT ──")

            def _get_trend_bias(ind_dict):
                bull = 0
                bear = 0
                rsi_data = ind_dict.get("RSI_14", {})
                rsi_val = rsi_data.get("value") if isinstance(rsi_data, dict) else rsi_data
                if isinstance(rsi_val, dict):
                    rsi_val = rsi_val.get("rsi", 50)
                if isinstance(rsi_val, (int, float)):
                    if rsi_val > 55:
                        bull += 1
                    elif rsi_val < 45:
                        bear += 1

                macd_data = ind_dict.get("MACD", {})
                macd_val = macd_data.get("value") if isinstance(macd_data, dict) else macd_data
                if isinstance(macd_val, dict):
                    hist = macd_val.get("histogram")
                    if hist is not None:
                        if hist > 0:
                            bull += 1
                        elif hist < 0:
                            bear += 1

                sma20 = (
                    ind_dict.get("SMA_20", {}).get("value")
                    if isinstance(ind_dict.get("SMA_20"), dict)
                    else ind_dict.get("SMA_20")
                )
                sma50 = (
                    ind_dict.get("SMA_50", {}).get("value")
                    if isinstance(ind_dict.get("SMA_50"), dict)
                    else ind_dict.get("SMA_50")
                )
                if isinstance(sma20, (int, float)) and isinstance(sma50, (int, float)):
                    if sma20 > sma50:
                        bull += 1
                    elif sma20 < sma50:
                        bear += 1

                if bull > bear:
                    return "BULLISH"
                if bear > bull:
                    return "BEARISH"
                return "NEUTRAL"

            d1_bias = _get_trend_bias(d1_ind)
            h4_bias = _get_trend_bias(h4_ind)
            align_status = (
                "ALIGNED"
                if d1_bias == h4_bias and d1_bias != "NEUTRAL"
                else "CONFLICTING"
                if (d1_bias in ("BULLISH", "BEARISH") and h4_bias in ("BULLISH", "BEARISH") and d1_bias != h4_bias)
                else "NEUTRAL/PARTIAL"
            )
            lines.append(f"D1 Technical Bias: {d1_bias} | H4 Technical Bias: {h4_bias} | Alignment: {align_status}")
            if align_status == "CONFLICTING":
                lines.append("[PERINGATAN] WARNING: D1 trend and H4 entry timeframe are CONFLICTING. Prefer WAIT.")
            lines.append("")

        for key, value in data.items():
            if key == "timesfm_forecast":
                continue  # Formatted cleanly in dedicated statistical distribution block below
            label = key.upper().replace("_", " ")
            lines.append(f"── {label} ──")
            if "GET PRICE HISTORY" in label:
                lines.append(self._compress_history(value, symbol))
            elif "GET TECHNICAL INDICATORS" in label:
                lines.append(self._format_technical_readable(value))
            elif "GET FUNDAMENTAL BRIEF" in label and isinstance(value, dict):
                matrix = value.get("per_asset_macro_matrix", {})
                sym_ctx = matrix.get(symbol) or matrix.get(symbol.replace("/", ""))
                if sym_ctx:
                    lines.append(f"🎯 TARGET SYMBOL MACRO ANCHOR ({symbol}):")
                    lines.append(
                        f"  • Bias: {sym_ctx.get('directional_bias', '').upper()} (Confidence: {sym_ctx.get('confidence')})"
                    )
                    lines.append(f"  • Structural Driver: {sym_ctx.get('structural_driver')}")
                    lines.append(f"  • Tactical Catalyst: {sym_ctx.get('tactical_catalyst')}")
                    lines.append(f"  • Invalidation: {sym_ctx.get('invalidation_level')}")
                    pi_score = value.get("asset_priced_in_scores", {}).get(symbol)
                    if pi_score is not None:
                        lines.append(f"  • Asset Priced-In Score: {pi_score}/10")
                    lines.append("")
                lines.append(self._compress_json(value))
            else:
                lines.append(self._compress_json(value))
            lines.append("")

        if fetch_errors:
            lines.append("── FAILED FETCHES (call these tools manually if needed) ──")
            lines.extend(f"  • {e}" for e in fetch_errors)
            lines.append("")

        asset_sentiments = ""
        if symbol == "BTCUSD":
            asset_sentiments = ", get_fear_greed_index, get_funding_rate, get_retail_sentiment"
        elif symbol in ("EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "XAUUSD"):
            asset_sentiments = ", get_retail_sentiment"
        elif symbol in ("XTIUSD", "XBRUSD"):
            asset_sentiments = ", get_fxssi_sentiment, get_eia_oil_inventory"

        cot_msg = ", get_cot_report" if cot_code and "cot_report" in data else ""
        # Build explicit allowed/blocked tool list
        always_allowed = ["get_news_items", "get_economic_calendar"]
        asset_specific_allowed = []
        if symbol in ("XTIUSD", "XBRUSD") and "eia_oil_inventory" not in data:
            asset_specific_allowed.append("get_eia_oil_inventory (MANDATORY for oil analysis)")

        failed_tools_allowed = [e.split(":")[0].strip() for e in fetch_errors] if fetch_errors else []

        all_allowed = always_allowed + asset_specific_allowed + failed_tools_allowed

        eia_blocked = ", get_eia_oil_inventory" if "eia_oil_inventory" in data else ""
        lines.append(f"""
# EFFICIENCY PROTOCOL — READ BEFORE CALLING ANY TOOL

ALLOWED TOOLS (not in bundle):
{chr(10).join(f"  - {t}" for t in all_allowed)}

DO NOT CALL — DATA ALREADY LOADED ABOVE:
  - get_fundamental_brief, get_market_session, get_dxy, get_vix
  - get_open_positions, get_risk_state, get_technical_indicators
  - get_atr, get_price_history, get_smc_zones, get_structure_breaks
  - get_swing_points, get_fibonacci_levels{cot_msg}{f", get_fear_greed_index, get_funding_rate, get_retail_sentiment" if symbol == "BTCUSD" else ""}{f", get_retail_sentiment" if symbol in ("EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "XAUUSD") else ""}{f", get_fxssi_sentiment" if symbol in ("XTIUSD", "XBRUSD") else ""}{eia_blocked}

Calling blocked tools wastes tokens on duplicate data and reduces analysis time budget.
""")

        # Inject computed confluence potential
        try:
            calc_res = await calculate_confluence(self.executor.session, symbol, settings=self.executor.settings)
            lines.append("── COMPUTED CONFLUENCE SCORE (PRE-HOC) ──")
            lines.append(f"Base BUY potential score: {calc_res.get('buy_potential_score', 0)}")
            lines.append(f"Base SELL potential score: {calc_res.get('sell_potential_score', 0)}")
            lines.append(f"Reference entry price for potential: {calc_res.get('reference_price', 0)}")
            lines.append(
                "NOTE: This is just a base computation. The final score depends on your specific R:R and entry."
            )
            lines.append("")

            # Inject priced-in subscores
            pi_scores = await calculate_priced_in_subscores(self.executor.session, symbol)
            data["priced_in_subscores"] = pi_scores
            data["confluence_precompute"] = calc_res

            try:
                from monika.application.analysis.calculators.daily_range_calculator import compute_daily_range_context

                adr_ctx = await compute_daily_range_context(self.executor.session, symbol, self.executor.settings)
                if "error" not in adr_ctx:
                    lines.append("── DAILY RANGE CONTEXT (ADR) — MANDATORY INTRADAY TP/SL TARGET BAND ──")
                    lines.append(f"{adr_ctx['lookback_days']}-day ADR: {adr_ctx['adr']:.5f}")
                    lines.append(
                        f"Today's range so far: {adr_ctx['today_range_so_far']:.5f} ({adr_ctx['today_range_pct_of_adr']:.0%} of ADR)"
                    )
                    lines.append(
                        f"Room remaining today: {adr_ctx['room_remaining_pct']:.0%} ({adr_ctx['session_recommendation']})"
                    )
                    lines.append(
                        f"MANDATORY TP distance band: {adr_ctx['target_tp_min_distance']:.5f} to {adr_ctx['target_tp_max_distance']:.5f} (50%-80% of ADR)"
                    )
                    lines.append(f"MANDATORY SL max distance: {adr_ctx['target_sl_max_distance']:.5f} (35% of ADR)")
                    lines.append(
                        "Your submit_asset_analysis call will be REJECTED if TP falls outside this band or SL exceeds the max."
                    )
                    lines.append("")
                    data["daily_range_context"] = adr_ctx
                else:
                    lines.append(f"── DAILY RANGE CONTEXT (ADR) — UNAVAILABLE ({adr_ctx.get('error')}) ──")
                    lines.append("ADR-band gating skipped this cycle; standard ATR-based SL sizing still applies.")
                    lines.append("")
            except Exception as e:
                logger.error(f"Failed to compute daily range context for {symbol}: {e}")

            # TimesFM 3.0 Statistical Distribution Block
            if "timesfm_forecast" in data and data["timesfm_forecast"]:
                tfm = data["timesfm_forecast"]
                q_dict = tfm.get("quantiles", {})
                q10 = round(q_dict["q10"][-1], 5) if ("q10" in q_dict and q_dict["q10"]) else "N/A"
                q50 = round(q_dict["q50"][-1], 5) if ("q50" in q_dict and q_dict["q50"]) else "N/A"
                q90 = round(q_dict["q90"][-1], 5) if ("q90" in q_dict and q_dict["q90"]) else "N/A"
                lines.append("── GOOGLE TIMESFM 3.0 MULTIVARIATE STATISTICAL DISTRIBUTION (24H) ──")
                lines.append(
                    f"Expected 24h Range: {tfm.get('expected_range')} | Volatility Expansion: {tfm.get('volatility_expansion_ratio')}x"
                )
                lines.append(
                    f"Quantile Skew: {tfm.get('quantile_skew')} | Key Distribution Bounds (Q10/Q50/Q90): {q10} / {q50} / {q90}"
                )
                lines.append(
                    "MANDATORY GROUNDING: Proposed TP must be statistically reachable (BUY TP <= Q90, SELL TP >= Q10)."
                )
                lines.append("")

            # Historical Pattern Similarity Screening Block
            try:
                ps_cfg = self.settings.get("pattern_similarity", {})
                if ps_cfg.get("enabled", True) and ps_cfg.get("inject_to_prefetch", True):
                    from monika.domain.indicators.pattern_similarity import PatternSimilarityEngine
                    from monika.infrastructure.database.models import PatternScreeningCache

                    ps_engine = PatternSimilarityEngine(session=self.executor.session, settings=self.settings)
                    ps_result = await ps_engine.screen(
                        symbol=symbol, llm_client=getattr(self.executor, "llm_client", None)
                    )

                    if ps_result:
                        lines.append(ps_result.format_for_prompt())
                        lines.append("")
                        data["pattern_similarity"] = ps_result

                        if ps_result.has_significant_results() or ps_result.overall_bias != "neutral":
                            cache_entry = PatternScreeningCache(
                                symbol=symbol,
                                screened_at=ps_result.screening_timestamp,
                                overall_bias=ps_result.overall_bias,
                                confidence=ps_result.confidence,
                                consensus_bullish_pct=ps_result.consensus_bullish_pct,
                                consensus_bearish_pct=ps_result.consensus_bearish_pct,
                                has_timeframe_conflict=ps_result.has_timeframe_conflict,
                                significant_timeframes_json=json.dumps(ps_result.significant_timeframes),
                                per_timeframe_json=json.dumps(
                                    {
                                        tf: {
                                            "match_count": res.match_count,
                                            "avg_similarity": res.avg_similarity,
                                            "bias": res.statistics.directional_bias,
                                            "p_value": res.statistics.p_value,
                                        }
                                        for tf, res in ps_result.per_timeframe.items()
                                    }
                                ),
                            )
                            self.executor.session.add(cache_entry)
                            await self.executor.session.commit()
            except Exception as e:
                logger.debug(f"Failed to prefetch pattern similarity for {symbol}: {e}")

            lines.append("── AUTOMATED PRICED-IN SUBSCORES ──")
            lines.append(f"Method 1 (FedWatch): {pi_scores['fedwatch']}/3")
            lines.append(f"Method 2 (COT Extreme): {pi_scores['cot']}/3")
            lines.append(f"Method 3 (Price vs ATR Momentum): {pi_scores['momentum']}/3")
            lines.append(f"Total Automated Score: {pi_scores['total_auto']}/9")
            lines.append(
                "INSTRUCTION: For your final `priced_in_score`, take this Total Automated Score and add Method 4 (News Saturation) based on get_news_items:"
            )
            lines.append(
                "  Method 4 score: +2 if heavy saturation (5+ headlines on same theme), +1 if moderate (2-4 headlines), 0 if low/none."
            )
            lines.append("  Final priced_in_score = Total Automated Score + Method 4 score (min 1, max 10).")
            lines.append("")

            # Persist automated PI score for enforcement in tool_executor
            try:
                auto_pi_key = f"auto_pi_score_{symbol}"
                auto_pi_data = json.dumps(
                    {
                        "total_auto": pi_scores["total_auto"],
                        "breakdown": {
                            "fedwatch": pi_scores["fedwatch"],
                            "cot": pi_scores["cot"],
                            "momentum": pi_scores["momentum"],
                        },
                        "computed_at": datetime.now(timezone.utc).isoformat(),
                        "symbol": symbol,
                    }
                )
                from sqlalchemy import select

                from monika.infrastructure.database.models import SystemConfig

                existing_pi_cfg = (
                    await self.executor.session.execute(select(SystemConfig).where(SystemConfig.key == auto_pi_key))
                ).scalar_one_or_none()
                if existing_pi_cfg:
                    existing_pi_cfg.value = auto_pi_data
                else:
                    self.executor.session.add(SystemConfig(key=auto_pi_key, value=auto_pi_data))
                await self.executor.session.commit()
            except Exception as e:
                logger.warning(f"[{symbol}] Failed to persist auto-PI score: {e}")
        except Exception as e:
            logger.error(f"Failed to calculate pre-hoc confluence: {e}")

        # Inject alpha lessons
        try:
            from sqlalchemy import desc, select

            from monika.infrastructure.database.models import DecisionReflection

            stmt = (
                select(DecisionReflection)
                .where(
                    DecisionReflection.symbol == symbol,
                    DecisionReflection.status == "resolved",
                    DecisionReflection.alpha_lesson.is_not(None),
                    DecisionReflection.alpha_lesson != "",
                )
                .order_by(desc(DecisionReflection.resolved_at))
                .limit(3)
            )

            recent_lessons = (await self.executor.session.execute(stmt)).scalars().all()
            if recent_lessons:
                data["recent_alpha_lessons"] = [
                    rl.alpha_lesson for rl in recent_lessons if getattr(rl, "alpha_lesson", None)
                ]
                lines.append("── RECENT ALPHA LESSONS ──")
                for rl in recent_lessons:
                    date_str = (
                        rl.resolved_at.strftime("%Y-%m-%d")
                        if rl.resolved_at
                        else (rl.created_at.strftime("%Y-%m-%d") if getattr(rl, "created_at", None) else "Recent")
                    )
                    alpha_str = f"{rl.alpha_return:.2f}%" if rl.alpha_return is not None else "N/A"
                    bench_str = f" vs {rl.benchmark_name}" if rl.benchmark_name else ""
                    lines.append(f"[{date_str}] Alpha: {alpha_str}{bench_str}")
                    lines.append(f"Lesson: {rl.alpha_lesson}")
                lines.append("")
        except Exception as e:
            logger.error(f"Failed to fetch alpha lessons: {e}")

        # Quantitative Playbook Signal Screener (Pillar 1: Institutional Screener)
        try:
            from monika.domain.market.playbook_screener import PlaybookScreener

            h1_data = data.get("get_price_history_H1", {})
            h1_bars = (
                h1_data.get("bars", []) if isinstance(h1_data, dict) else (h1_data if isinstance(h1_data, list) else [])
            )
            if not h1_bars:
                h4_data = data.get("get_price_history_H4", {})
                h1_bars = (
                    h4_data.get("bars", [])
                    if isinstance(h4_data, dict)
                    else (h4_data if isinstance(h4_data, list) else [])
                )

            h1_tech = data.get("get_technical_indicators_H1", {})
            h1_indicators = h1_tech.get("indicators", h1_tech) if isinstance(h1_tech, dict) else {}

            macro_bias = None
            if isinstance(data.get("get_fundamental_brief"), dict):
                macro_bias = data.get("get_fundamental_brief", {}).get("macro_bias")

            cooldown_set = set()
            try:
                from monika.application.analysis.memory.playbook_lifecycle import (
                    PlaybookLifecycleManager,
                    PlaybookState,
                )

                plm = PlaybookLifecycleManager()
                for pb_name, pb_meta in plm.list_all_playbooks().items():
                    if getattr(pb_meta, "state", None) in (PlaybookState.STALE, PlaybookState.ARCHIVED):
                        cooldown_set.add(pb_name)
            except Exception as plm_err:
                logger.debug(f"[{symbol}] Failed to read playbook cooldown state (non-fatal): {plm_err}")

            screening_report = PlaybookScreener.screen(
                symbol=symbol,
                bars=h1_bars,
                indicators=h1_indicators,
                now_utc=now,
                macro_regime=macro_bias,
                cooldown_playbooks=cooldown_set,
            )
            data["playbook_screening"] = screening_report
            if screening_report.active_signals:
                data["active_playbook_id"] = screening_report.active_signals[0].playbook_name

            lines.append(screening_report.format_for_prompt())
            lines.append("")
        except Exception as pb_screen_err:
            logger.debug(f"[{symbol}] Playbook screener execution non-fatal: {pb_screen_err}")

        # Inject snapshot timestamp into bundle tail metadata
        lines.append(f"── BUNDLE METADATA ──\nData snapshot time: {ts}\n")

        # Pengecekan ukuran memori (token limit protection):
        raw_bundle = "\n".join(lines)

        max_bundle_chars = 180000
        if hasattr(self, "executor") and hasattr(self.executor, "settings") and self.executor.settings:
            max_bundle_chars = self.executor.settings.get("analysis", {}).get("stage2_max_bundle_chars", 180000)

        if len(raw_bundle) > max_bundle_chars:
            dropped_sections = []
            logger.info(
                f"[{symbol}] Bundle size {len(raw_bundle)} chars exceeds threshold ({max_bundle_chars}). Compressing..."
            )

            # Priority: Remove price history bars first (most verbose), keep SMC zones 100% intact
            # Step 1: Compress price history to last 10 bars instead of 30
            def compress_price_history_section(text: str, keep_bars: int = 10) -> str:
                """Compress OHLCV section to last N bars."""
                lines_list = text.split("\n")
                in_price_section = False
                other_lines = []
                price_data_lines = []

                for line in lines_list:
                    if "── GET PRICE HISTORY" in line.upper():
                        in_price_section = True
                        other_lines.append(line)
                        price_data_lines = []
                    elif in_price_section and line.startswith("──"):
                        # Keep last keep_bars price data lines
                        if price_data_lines:
                            header = price_data_lines[0] if price_data_lines else "time,O,H,L,C"
                            kept = (
                                price_data_lines[-keep_bars:] if len(price_data_lines) > keep_bars else price_data_lines
                            )
                            other_lines.extend([header] + kept)
                        in_price_section = False
                        price_data_lines = []
                        other_lines.append(line)
                    elif in_price_section:
                        price_data_lines.append(line)
                    else:
                        other_lines.append(line)

                if in_price_section and price_data_lines:
                    header = price_data_lines[0] if price_data_lines else "time,O,H,L,C"
                    kept = price_data_lines[-keep_bars:] if len(price_data_lines) > keep_bars else price_data_lines
                    other_lines.extend([header] + kept)

                return "\n".join(other_lines)

            raw_bundle = compress_price_history_section("\n".join(lines), keep_bars=10)
            dropped_sections.append("price_history (dikompresi ke 10 bar terakhir)")

            # Step 2: Jika masih terlalu besar, remove retail sentiment (less critical than SMC structure)
            if len(raw_bundle) > max_bundle_chars:
                raw_bundle_lines = raw_bundle.split("\n")
                filtered_lines = [
                    l
                    for l in raw_bundle_lines
                    if not any(x in l.upper() for x in ["RETAIL SENTIMENT", "FXSSI", "BINANCE SENTIMENT"])
                ]
                raw_bundle = "\n".join(filtered_lines)
                dropped_sections.append("retail/FXSSI/Binance sentiment (dihapus)")

            # Step 3: Jika masih terlalu besar, pangkas recent news ke 4 headline teratas
            if len(raw_bundle) > max_bundle_chars:

                def compress_news_section(text: str) -> str:
                    lines_list = text.split("\n")
                    in_news = False
                    news_lines = []
                    res_lines = []
                    for line in lines_list:
                        if "── RECENT NEWS" in line.upper():
                            in_news = True
                            res_lines.append(line)
                            news_lines = []
                        elif in_news and line.startswith("──"):
                            if news_lines:
                                try:
                                    import json

                                    news_data = json.loads("\n".join(news_lines))
                                    if isinstance(news_data, dict) and "items" in news_data:
                                        news_data["items"] = news_data["items"][:4]
                                        news_data["count"] = len(news_data["items"])
                                        res_lines.append(json.dumps(news_data, separators=(",", ":")))
                                    else:
                                        res_lines.extend(news_lines[:5])
                                except Exception:
                                    res_lines.extend(news_lines[:5])
                            in_news = False
                            news_lines = []
                            res_lines.append(line)
                        elif in_news:
                            news_lines.append(line)
                        else:
                            res_lines.append(line)
                    return "\n".join(res_lines)

                raw_bundle = compress_news_section(raw_bundle)
                dropped_sections.append("recent news (dipangkas ke 4 headline teratas)")

            # Step 4: Last resort - remove D1 swing points (H4 swing points dan SMC zones TETAP UTUH)
            if len(raw_bundle) > max_bundle_chars:
                raw_bundle_lines = raw_bundle.split("\n")
                filtered_lines = [l for l in raw_bundle_lines if "SWING POINTS D1" not in l.upper()]
                raw_bundle = "\n".join(filtered_lines)
                dropped_sections.append("swing points D1 (dihapus total)")

            if dropped_sections:
                raw_bundle += (
                    f"\n\n[PERINGATAN] BUNDLE COMPRESSION NOTICE: Bagian berikut dipotong/dihapus karena batas ukuran: "
                    f"{', '.join(dropped_sections)}. Jika data ini krusial untuk keputusanmu, panggil tool "
                    f"terkait secara manual sebelum submit.\n"
                )

            # NOTE: Hard warning only if bundle is extremely large (> 200000 chars)
            if len(raw_bundle) > 200000:
                logger.warning(
                    f"[{symbol}] Bundle unusually large ({len(raw_bundle)} chars) after compression — proceeding anyway"
                )

        bundle = raw_bundle
        try:
            from monika.infrastructure.llm.prompt_compressor import PromptBundleCompressor as ContextCompressor

            compressor = ContextCompressor(self.executor.settings if hasattr(self, "executor") else self.settings)
            bundle = compressor.compress_stage2_bundle(bundle, symbol=symbol, max_tokens=64000)
        except Exception:
            pass
        logger.info(f"[{symbol}] Stage2 bundle ready: {len(data)} datasets, {len(bundle)} chars")
        return bundle, data
