# ==============================================================================
# File: analysis/tools/handlers/macro/central_banks.py
# ==============================================================================

"""
Central bank policy rates, rate expectations (FedWatch, OIS), and central bank doc differ handlers.
"""

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select

import monika.core.primitives.clock as clock
from monika.application.analysis.tools.handlers.macro.base import _get_macro_context, _safe_execute
from monika.infrastructure.database.models import (
    CentralBankRateExpectation,
    FedWatchProbability,
    InterestRate,
)


def _parse_iso_or_str_dt(dt_val: Any) -> Optional[datetime]:
    """Parse ISO or human-readable date/time string to timezone-aware UTC datetime."""
    if isinstance(dt_val, datetime):
        return dt_val.replace(tzinfo=timezone.utc) if dt_val.tzinfo is None else dt_val
    if not dt_val or not isinstance(dt_val, str):
        return None
    try:
        import dateutil.parser as dparser

        dt = dparser.parse(dt_val.strip())
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except Exception:
        return None


def _extract_fedwatch_action_probs(probs_dict: Any) -> Dict[str, float]:
    """Extract action -> probability mapping uniformly from probabilities_json."""
    if not isinstance(probs_dict, dict):
        return {}
    res: Dict[str, float] = {}
    if "probabilities" in probs_dict and isinstance(probs_dict["probabilities"], dict):
        for range_key, pdata in probs_dict["probabilities"].items():
            if isinstance(pdata, dict):
                act = str(pdata.get("action", range_key)).upper()
                p_val = float(pdata.get("probability", 0.0))
                res[act] = round(res.get(act, 0.0) + p_val, 2)
            elif isinstance(pdata, (int, float)):
                res[str(range_key).upper()] = float(pdata)
        return res
    for k, v in probs_dict.items():
        if isinstance(v, (int, float)):
            res[str(k).upper()] = float(v)
    return res


async def handle_get_interest_rates(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for interest rates"}

    raw_rates = await _safe_execute(
        session,
        select(InterestRate)
        .where(InterestRate.effective_date <= clock.now())
        .order_by(InterestRate.bank, InterestRate.effective_date.desc()),
    )
    rows = raw_rates.scalars().all() if raw_rates is not None else []

    # Ambil ekspektasi suku bunga terbaru dari CentralBankRateExpectation
    raw_exp = await _safe_execute(
        session,
        select(CentralBankRateExpectation).order_by(
            CentralBankRateExpectation.bank,
            CentralBankRateExpectation.fetched_at.desc(),
            CentralBankRateExpectation.id.desc(),
        ),
    )
    exp_rows = raw_exp.scalars().all() if raw_exp is not None else []
    latest_exp = {}
    for er in exp_rows:
        eb = getattr(er, "bank", "").upper()
        if eb and eb not in latest_exp:
            latest_exp[eb] = {
                "meeting_date": getattr(er, "meeting_date", None),
                "current_rate_pct": getattr(er, "current_rate", None),
                "prob_hike": getattr(er, "prob_hike", 0.0),
                "prob_hold": getattr(er, "prob_hold", 0.0),
                "prob_cut": getattr(er, "prob_cut", 0.0),
            }

    seen_banks = set()
    rates = []
    for r in rows:
        bank_name = getattr(r, "bank", None)
        if bank_name and bank_name not in seen_banks:
            seen_banks.add(bank_name)
            eff_dt = getattr(r, "effective_date", None)
            eff_str = (
                eff_dt.strftime("%Y-%m-%d") if eff_dt is not None and hasattr(eff_dt, "strftime") else str(eff_dt or "")
            )
            nxt_dt = getattr(r, "next_meeting_date", None)
            nxt_str = (
                nxt_dt.strftime("%Y-%m-%d")
                if nxt_dt is not None and hasattr(nxt_dt, "strftime")
                else (str(nxt_dt) if nxt_dt else None)
            )

            # Jika next_meeting_date kosong, coba lengkapi dari latest_exp
            b_up = bank_name.upper()
            if not nxt_str and b_up in latest_exp:
                nxt_str = latest_exp[b_up].get("meeting_date")

            exp_data = latest_exp.get(b_up)

            # Jika data InterestRate usang (>180 hari) dan latest_exp memiliki rate terkini
            rate_val = getattr(r, "rate_percent", None)
            if exp_data and exp_data.get("current_rate_pct") is not None and eff_dt is not None:
                eff_utc = eff_dt if getattr(eff_dt, "tzinfo", None) else eff_dt.replace(tzinfo=timezone.utc)
                now_dt_check = clock.now()
                if now_dt_check.tzinfo is None:
                    now_dt_check = now_dt_check.replace(tzinfo=timezone.utc)
                if (now_dt_check - eff_utc).days > 180:
                    rate_val = exp_data.get("current_rate_pct")

            rates.append(
                {
                    "bank": bank_name,
                    "rate_pct": rate_val,
                    "effective_date": eff_str,
                    "next_meeting_date": nxt_str,
                    "market_expectations": exp_data,
                }
            )

    # Lengkapi bank yang ada di latest_exp namun belum ada di tabel InterestRate (e.g. RBA)
    for eb, exp_info in latest_exp.items():
        if eb and eb not in seen_banks and exp_info.get("current_rate_pct") is not None:
            seen_banks.add(eb)
            now_str = clock.now().strftime("%Y-%m-%d")
            rates.append(
                {
                    "bank": eb,
                    "rate_pct": exp_info.get("current_rate_pct"),
                    "effective_date": now_str,
                    "next_meeting_date": exp_info.get("meeting_date"),
                    "market_expectations": exp_info,
                }
            )

    valid_eff_dates = [
        r.effective_date for r in rows if isinstance(getattr(r, "effective_date", None), (datetime, date))
    ]
    latest_eff = max(valid_eff_dates, default=None)
    data_age_days = None
    if isinstance(latest_eff, (datetime, date)):
        if isinstance(latest_eff, datetime):
            eff_dt = latest_eff.replace(tzinfo=timezone.utc) if latest_eff.tzinfo is None else latest_eff
        else:
            eff_dt = datetime(latest_eff.year, latest_eff.month, latest_eff.day, tzinfo=timezone.utc)
        now_dt = clock.now()
        if now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc)
        data_age_days = (now_dt - eff_dt).days

    # Map bank rates by key for differential computation
    bank_rates = {r["bank"].upper(): r["rate_pct"] for r in rates if r.get("rate_pct") is not None}
    differentials = {}
    if "ECB" in bank_rates and "FED" in bank_rates:
        differentials["EURUSD"] = {
            "base": "EUR (ECB)",
            "quote": "USD (FED)",
            "spread_pct": round(bank_rates["ECB"] - bank_rates["FED"], 2),
            "advantage": "EUR" if bank_rates["ECB"] > bank_rates["FED"] else "USD",
        }
    if "BOE" in bank_rates and "FED" in bank_rates:
        differentials["GBPUSD"] = {
            "base": "GBP (BOE)",
            "quote": "USD (FED)",
            "spread_pct": round(bank_rates["BOE"] - bank_rates["FED"], 2),
            "advantage": "GBP" if bank_rates["BOE"] > bank_rates["FED"] else "USD",
        }
    if "RBA" in bank_rates and "FED" in bank_rates:
        differentials["AUDUSD"] = {
            "base": "AUD (RBA)",
            "quote": "USD (FED)",
            "spread_pct": round(bank_rates["RBA"] - bank_rates["FED"], 2),
            "advantage": "AUD" if bank_rates["RBA"] > bank_rates["FED"] else "USD",
        }
    if "FED" in bank_rates and "BOJ" in bank_rates:
        differentials["USDJPY"] = {
            "base": "USD (FED)",
            "quote": "JPY (BOJ)",
            "spread_pct": round(bank_rates["FED"] - bank_rates["BOJ"], 2),
            "advantage": "USD",
            "carry_trade_context": "JPY acts as primary funding currency; wide spread incentivizes carry trade until risk-off unwind occurs.",
        }

    mandate_profiles = {
        "FED": {
            "mandate": "Dual (Max Employment + Price Stability 2% Core PCE)",
            "key_focus": "Core PCE vs NFP/Claims",
        },
        "ECB": {"mandate": "Single (Price Stability 2% HICP medium-term)", "key_focus": "HICP & Two-Pillar M3 credit"},
        "BOE": {
            "mandate": "Tiered (Price Stability 2% CPI remit primary; growth secondary)",
            "key_focus": "MPC voting split & Gilt sensitivity",
        },
        "BOJ": {
            "mandate": "Deflation Exit / Sound Economic Development",
            "key_focus": "Shunto wage growth & Core-core CPI",
        },
        "RBA": {
            "mandate": "Triple (2-3% range, Full Employment, Public Welfare)",
            "key_focus": "Trimmed Mean CPI & Iron Ore terms of trade",
        },
    }

    return {
        "count": len(rates),
        "rates": rates,
        "rate_differentials": differentials,
        "mandate_profiles": mandate_profiles,
        "data_age_days": data_age_days,
    }


async def handle_get_central_bank_expectations(args: dict, **ctx) -> dict:
    """
    Mengembalikan ekspektasi keputusan suku bunga pasar untuk FED, ECB, BOE, BOJ, RBA.
    Mencakup probabilitas Hike %, Hold %, Cut %, tanggal rapat, komparasi sebelum vs sesudah event, dan derajat priced-in (1-10).
    """
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {"error": "Database session required for central bank rate expectations"}

    target_bank = (args.get("bank") or "").strip().upper()
    compare_hours_ago = args.get("compare_hours_ago")
    event_time_arg = args.get("event_time") or args.get("as_of")
    include_history = bool(args.get("include_history", False))

    ref_time = None
    if compare_hours_ago is not None:
        try:
            ref_time = clock.now() - timedelta(hours=float(compare_hours_ago))
        except ValueError, TypeError:
            pass
    elif event_time_arg:
        ref_time = _parse_iso_or_str_dt(event_time_arg)

    query = select(CentralBankRateExpectation).order_by(
        CentralBankRateExpectation.bank,
        CentralBankRateExpectation.fetched_at.desc(),
        CentralBankRateExpectation.id.desc(),
    )
    if target_bank:
        query = query.where(CentralBankRateExpectation.bank == target_bank)

    fetch_limit = 200 if (include_history or ref_time) else 50
    rows = (await _safe_execute(session, query.limit(fetch_limit))).scalars().all()
    if not rows:
        return {
            "expectations": {},
            "fallback_tool": "web_search",
            "suggested_queries": {
                "ECB": "ECB rate expectations OIS Euribor futures upcoming meeting",
                "BOE": "Bank of England rate expectations SONIA futures upcoming MPC",
                "BOJ": "Bank of Japan rate expectations OIS TONA upcoming meeting",
                "RBA": "RBA cash rate expectations ASX 30-Day Interbank futures",
            },
            "note": "Belum ada rekaman ekspektasi di database. Jalankan scraper atau gunakan web_search.",
        }

    latest_by_bank = {}
    history_by_bank = {}

    for r in rows:
        b = r.bank.upper()
        probs = {
            "hike": float(r.prob_hike or 0.0),
            "hold": float(r.prob_hold or 0.0),
            "cut": float(r.prob_cut or 0.0),
        }
        dom_action = max(probs, key=lambda k: probs[k])
        dom_prob = probs[dom_action]

        # Hitung Priced-In Score (1-10)
        if dom_prob >= 90:
            pi_score = 9
            pi_label = "Fully Priced In"
        elif dom_prob >= 75:
            pi_score = 7
            pi_label = "Largely Priced In"
        elif dom_prob >= 55:
            pi_score = 5
            pi_label = "Partially Priced In"
        elif dom_prob >= 35:
            pi_score = 4
            pi_label = "Weakly Priced In"
        else:
            pi_score = 2
            pi_label = "NOT Priced In (Surprise Risk)"

        item = {
            "id": r.id,
            "bank": b,
            "current_rate_pct": r.current_rate,
            "next_meeting_date": r.meeting_date,
            "probabilities": probs,
            "dominant_expected_action": dom_action,
            "dominant_probability_pct": dom_prob,
            "priced_in_score": pi_score,
            "priced_in_label": pi_label,
            "source": r.source,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
        }

        r_fetched_tz = (
            r.fetched_at.replace(tzinfo=timezone.utc)
            if (r.fetched_at and r.fetched_at.tzinfo is None)
            else r.fetched_at
        )
        if include_history or ref_time:
            history_by_bank.setdefault(b, []).append((r_fetched_tz, item))

        if b not in latest_by_bank:
            latest_by_bank[b] = item

    result = {
        "count": len(latest_by_bank),
        "expectations": latest_by_bank,
        "interpretation_guide": (
            "Probabilitas > 80% = LARGELY/FULLY PRICED IN (risiko sell-the-news tinggi). "
            "Probabilitas 50-80% = PARTIALLY PRICED IN (moderate uncertainty). "
            "Probabilitas < 50% = NOT PRICED IN (potensi kejutan besar jika terealisasi)."
        ),
    }

    # Perhitungan komparasi jika ref_time diberikan
    if ref_time:
        bank_comparisons = []
        for b, s_list in history_by_bank.items():
            pre_candidates = [s for s in s_list if s[0] and s[0] <= ref_time]
            post_candidates = [s for s in s_list if s[0] and s[0] >= ref_time]

            pre_snap = pre_candidates[0][1] if pre_candidates else (s_list[-1][1] if s_list else None)
            post_snap = post_candidates[0][1] if post_candidates else (s_list[0][1] if s_list else None)

            if pre_snap and post_snap and pre_snap["id"] != post_snap["id"]:
                p0 = pre_snap["probabilities"]
                p1 = post_snap["probabilities"]

                def _to_p(v):
                    return v * 100.0 if abs(v) <= 1.0 else float(v)

                h0, h1 = _to_p(p0.get("hike", 0.0)), _to_p(p1.get("hike", 0.0))
                hd0, hd1 = _to_p(p0.get("hold", 0.0)), _to_p(p1.get("hold", 0.0))
                c0, c1 = _to_p(p0.get("cut", 0.0)), _to_p(p1.get("cut", 0.0))
                deltas = {
                    "hike": round(h1 - h0, 1),
                    "hold": round(hd1 - hd0, 1),
                    "cut": round(c1 - c0, 1),
                }
                summary = (
                    f"Pergeseran suku bunga {b} (ref: {ref_time.strftime('%Y-%m-%d %H:%M UTC')}): "
                    f"Hike {h0:.1f}% -> {h1:.1f}% ({deltas['hike']:+.1f}%), "
                    f"Hold {hd0:.1f}% -> {hd1:.1f}% ({deltas['hold']:+.1f}%), "
                    f"Cut {c0:.1f}% -> {c1:.1f}% ({deltas['cut']:+.1f}%)."
                )
                deltas_pct = {k.upper(): round(v, 1) for k, v in deltas.items()}
                comp_item = {
                    "bank": b,
                    "reference_time": ref_time.isoformat(),
                    "comparison_mode": "pre_vs_post_event" if event_time_arg else "temporal_delta",
                    "current_probabilities": p1,
                    "prior_probabilities": p0,
                    "pre_event": pre_snap,
                    "post_event": post_snap,
                    "deltas": deltas,
                    "deltas_pct": deltas_pct,
                    "summary": summary,
                    "narrative_summary": summary,
                }
                bank_comparisons.append(comp_item)
                if b in latest_by_bank:
                    latest_by_bank[b]["comparison"] = comp_item
        if bank_comparisons:
            result["comparisons"] = bank_comparisons
            result["comparison_summary"] = "\n".join(bc["summary"] for bc in bank_comparisons)

    if include_history:
        result["history"] = {b: [s[1] for s in s_list[:10]] for b, s_list in history_by_bank.items()}

    return result


async def handle_get_fedwatch_probabilities(args: dict, **ctx) -> dict:
    session, _, _ = _get_macro_context(args, ctx)
    if not session:
        return {
            "error": "Database session required for fedwatch",
            "fallback_tool": "web_search",
            "suggested_query": "CME FedWatch target rate probabilities upcoming FOMC meeting",
            "note": (
                "Database session tidak tersedia untuk fedwatch. "
                "SARAN TINDAKAN: Gunakan tool 'web_search' dengan kueri: "
                "'CME FedWatch target rate probabilities upcoming FOMC meeting' untuk mendapatkan probabilitas terkini."
            ),
        }

    meeting_filter = (args.get("meeting_date") or "").strip()
    compare_hours_ago = args.get("compare_hours_ago")
    event_time_arg = args.get("event_time") or args.get("as_of")
    include_history = bool(args.get("include_history", False))

    limit = args.get("limit")
    if limit is None or str(limit).strip().lower() in ("none", "null", ""):
        limit = 4
    else:
        try:
            limit = int(limit)
        except ValueError, TypeError:
            limit = 4

    # Determine reference comparison time if requested
    ref_time = None
    if compare_hours_ago is not None:
        try:
            ref_time = clock.now() - timedelta(hours=float(compare_hours_ago))
        except ValueError, TypeError:
            pass
    elif event_time_arg:
        ref_time = _parse_iso_or_str_dt(event_time_arg)

    base_query = select(FedWatchProbability).where(FedWatchProbability.fetched_at <= clock.now())
    if meeting_filter:
        base_query = base_query.where(FedWatchProbability.meeting_date.ilike(f"%{meeting_filter}%"))

    query_limit = 200 if (include_history or ref_time) else max(limit * 2, 8)
    rows = (
        (
            await session.execute(
                base_query.order_by(FedWatchProbability.fetched_at.desc(), FedWatchProbability.id.desc()).limit(
                    query_limit
                )
            )
        )
        .scalars()
        .all()
    )

    meetings_by_date = {}
    history_by_date = {}
    for r in rows:
        try:
            probs = json.loads(r.probabilities_json)
        except Exception:
            probs = {"error": "Malformed JSON in database"}
        fetched_tz = r.fetched_at.replace(tzinfo=timezone.utc) if r.fetched_at.tzinfo is None else r.fetched_at
        age_hours = round((clock.now() - fetched_tz).total_seconds() / 3600, 1)

        snapshot_item = {
            "id": r.id,
            "meeting_date": r.meeting_date,
            "probabilities": probs,
            "fetched_at": r.fetched_at.isoformat(),
            "data_age_hours": age_hours,
        }

        if include_history or ref_time:
            history_by_date.setdefault(r.meeting_date, []).append((fetched_tz, snapshot_item))

        if r.meeting_date not in meetings_by_date:
            meetings_by_date[r.meeting_date] = {
                "meeting_date": r.meeting_date,
                "probabilities": probs,
                "fetched_at": r.fetched_at.isoformat(),
                "data_age_hours": age_hours,
            }

    meetings = list(meetings_by_date.values())
    meetings.sort(key=lambda m: str(m.get("meeting_date", "")))
    meetings = meetings[:limit]

    result = {
        "count": len(meetings),
        "meetings": meetings,
    }

    if not meetings:
        result["note"] = (
            "Data lokal CME FedWatch tidak tersedia di database. "
            "SARAN TINDAKAN OTOMATIS: Gunakan tool 'web_search' dengan kueri: "
            "'CME FedWatch target rate probabilities upcoming FOMC meeting' atau "
            "'FedWatch tool probabilities' untuk mendapatkan probabilitas terkini."
        )
        result["fallback_tool"] = "web_search"
        result["suggested_query"] = "CME FedWatch target rate probabilities upcoming FOMC meeting"
        return result

    # Compute comparison if ref_time is provided
    if ref_time:
        comparisons = []
        target_dates = (
            [meeting_filter]
            if meeting_filter and meeting_filter in history_by_date
            else list(history_by_date.keys())[:limit]
        )
        for m_date in target_dates:
            snapshots = history_by_date.get(m_date, [])
            if not snapshots:
                continue

            pre_candidates = [s for s in snapshots if s[0] <= ref_time]
            post_candidates = [s for s in snapshots if s[0] >= ref_time]

            pre_snap = pre_candidates[0][1] if pre_candidates else (snapshots[-1][1] if snapshots else None)
            post_snap = post_candidates[0][1] if post_candidates else (snapshots[0][1] if snapshots else None)

            if pre_snap and post_snap and pre_snap["id"] != post_snap["id"]:
                pre_actions = _extract_fedwatch_action_probs(pre_snap["probabilities"])
                post_actions = _extract_fedwatch_action_probs(post_snap["probabilities"])

                all_actions = sorted(list(set(pre_actions.keys()) | set(post_actions.keys())))
                deltas = {}
                shifts_text = []
                for act in all_actions:
                    p0 = pre_actions.get(act, 0.0)
                    p1 = post_actions.get(act, 0.0)
                    d = round(p1 - p0, 3)
                    deltas[act] = d
                    p0_pct = p0 * 100 if p0 <= 1.0 else p0
                    p1_pct = p1 * 100 if p1 <= 1.0 else p1
                    d_pct = d * 100 if abs(d) <= 1.0 else d
                    if abs(d_pct) >= 0.5:
                        sign = "+" if d_pct > 0 else ""
                        shifts_text.append(f"{act} {p0_pct:.1f}% -> {p1_pct:.1f}% ({sign}{d_pct:.1f}%)")

                shift_summary = f"Pergeseran ekspektasi rapat {m_date}: " + (
                    ", ".join(shifts_text) if shifts_text else "Relatif stabil."
                )

                deltas_pct = {k: round(v * 100, 1) if abs(v) <= 1.0 else round(v, 1) for k, v in deltas.items()}
                comp_obj = {
                    "meeting_date": m_date,
                    "reference_time": ref_time.isoformat(),
                    "comparison_mode": "pre_vs_post_event" if event_time_arg else "temporal_delta",
                    "current_probabilities": post_actions,
                    "prior_probabilities": pre_actions,
                    "pre_event": {
                        "fetched_at": pre_snap["fetched_at"],
                        "probabilities": pre_actions,
                        "data_age_hours": pre_snap["data_age_hours"],
                    },
                    "post_event": {
                        "fetched_at": post_snap["fetched_at"],
                        "probabilities": post_actions,
                        "data_age_hours": post_snap["data_age_hours"],
                    },
                    "deltas": deltas,
                    "deltas_pct": deltas_pct,
                    "summary": shift_summary,
                    "narrative_summary": shift_summary,
                }
                comparisons.append(comp_obj)

        if comparisons:
            result["comparisons"] = comparisons
            result["comparison_summary"] = "\n".join(c["summary"] for c in comparisons)
            for c in comparisons:
                for m in meetings:
                    if m.get("meeting_date") == c.get("meeting_date"):
                        m["comparison"] = c

    if include_history:
        history_out = {}
        for m_date, s_list in history_by_date.items():
            history_out[m_date] = [
                {
                    "fetched_at": s[1]["fetched_at"],
                    "data_age_hours": s[1]["data_age_hours"],
                    "probabilities": _extract_fedwatch_action_probs(s[1]["probabilities"]),
                }
                for s in s_list[:10]
            ]
        result["history"] = history_out
        for m in meetings:
            if m.get("meeting_date") in history_out:
                m["history"] = history_out[m["meeting_date"]]

    return result


async def handle_diff_central_bank_documents(args: dict, **ctx) -> dict:
    session = ctx.get("session")
    if not session:
        return {"status": "unavailable", "message": "Database session required"}
    from monika.application.analysis.calculators.universal_cb_differ import UniversalCentralBankDiffer

    differ = UniversalCentralBankDiffer(session)
    bank = args.get("bank", "FED")
    doc_type = args.get("doc_type", "MINUTES")
    return await differ.diff_cb_documents(bank=bank, doc_type=doc_type)


async def handle_get_macro_cross_report_synthesis(args: dict, **ctx) -> dict:
    session = ctx.get("session")
    if not session:
        return {"status": "unavailable", "message": "Database session required"}
    from monika.application.analysis.calculators.universal_macro_analyzer import UniversalMacroAnalyzer

    analyzer = UniversalMacroAnalyzer(session)
    currency = args.get("currency", "USD")
    lookback = int(args.get("lookback_days", 30))
    return await analyzer.analyze_cross_report_synthesis(currency=currency, lookback_days=lookback)


async def handle_get_g10_macro_divergence(args: dict, **ctx) -> dict:
    session = ctx.get("session")
    if not session:
        return {"status": "unavailable", "message": "Database session required"}
    from monika.application.analysis.calculators.universal_macro_analyzer import UniversalMacroAnalyzer

    analyzer = UniversalMacroAnalyzer(session)
    pair = args.get("pair", "EURUSD")
    return await analyzer.analyze_g10_macro_divergence(pair=pair)


async def handle_get_fed_net_liquidity_and_stress(args: dict, **ctx) -> dict:
    session = ctx.get("session")
    if not session:
        return {"status": "unavailable", "message": "Database session required"}
    from monika.application.analysis.calculators.universal_liquidity_analyzer import UniversalLiquidityAnalyzer

    analyzer = UniversalLiquidityAnalyzer(session)
    lookback = int(args.get("lookback_weeks", 8))
    liq = await analyzer.analyze_fed_net_liquidity(lookback_weeks=lookback)
    stress = await analyzer.analyze_credit_and_funding_stress()
    return {
        "fed_net_liquidity": liq,
        "market_credit_and_funding_stress": stress,
    }


async def handle_get_ecb_qt_progress(args: dict, **ctx) -> dict:
    session = ctx.get("session")
    if not session:
        return {"status": "unavailable", "message": "Database session required"}
    from monika.application.analysis.calculators.universal_liquidity_analyzer import UniversalLiquidityAnalyzer

    analyzer = UniversalLiquidityAnalyzer(session)
    lookback = int(args.get("lookback_weeks", 8))
    return await analyzer.analyze_ecb_balance_sheet_and_qt(lookback_weeks=lookback)


async def handle_get_global_pmi_trend(args: dict, **ctx) -> dict:
    session = ctx.get("session")
    if not session:
        return {"status": "unavailable", "message": "Database session required"}
    from monika.infrastructure.data_ingestion.sources.leading_survey_fetcher import LeadingSurveyFetcher

    fetcher = LeadingSurveyFetcher(session)
    period = args.get("period")
    return await fetcher.get_global_pmi_summary(period=period)
