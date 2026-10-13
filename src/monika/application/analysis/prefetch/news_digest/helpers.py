# ==============================================================================
# File: application/analysis/prefetch/news_digest/helpers.py
# ==============================================================================

"""
Text normalization, similarity, numeric claim parsing, and classification helpers.
"""

from __future__ import annotations

import re
import re as _re
import string as _string
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from monika.domain.market.news_impact_keywords import (
    DEESCALATION_KEYWORDS,
    HIGH_IMPACT_KEYWORDS,
    REHASH_KEYWORDS,
    SHOCK_KEYWORDS,
)
from monika.infrastructure.database.models import NewsItem
from monika.application.analysis.prefetch.news_digest.constants import (
    _FINANCIAL_SHORT_TOKENS,
    _NUMERIC_TOKEN_PATTERN,
    _POLARITY_GROUPS,
    _SENTIMENT_SET,
    _STRUCTURAL_NUMBERS,
    SENTIMENT_TAXONOMY,
)


def _get_polarity_group(toks: set) -> Optional[str]:
    for group, words in _POLARITY_GROUPS.items():
        if toks & words:
            return group
    return None


def _jaccard_title_similarity(title_a: str, title_b: str) -> float:
    def _clean_tokens(title: str) -> set:
        toks = set()
        for raw in (title or "").lower().split():
            clean = raw.strip(_string.punctuation)
            if len(clean) > 3 or clean in _FINANCIAL_SHORT_TOKENS:
                toks.add(clean)
        return toks

    tokens_a = _clean_tokens(title_a)
    tokens_b = _clean_tokens(title_b)
    if not tokens_a or not tokens_b:
        return 0.0

    # Polarity conflict guard: if titles have truly opposing semantic polarity, reject duplicate
    grp_a = _get_polarity_group(tokens_a)
    grp_b = _get_polarity_group(tokens_b)
    if grp_a and grp_b and grp_a != grp_b:
        return 0.0

    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


def _extract_numeric_claims(text: str) -> list[str]:
    """Extract raw numeric token strings from text (handles thousands separators, decimals, %, bps, currency, etc.)."""
    if not text:
        return []
    raw_matches = _NUMERIC_TOKEN_PATTERN.findall(text)
    cleaned = []
    for m in raw_matches:
        s = m.strip(" \t\n\r:;()[]{}*`\"'")
        if s and any(c.isdigit() for c in s):
            cleaned.append(s)
    return cleaned


def _format_news_item_for_prompt(item, max_summary_chars: int = 1500) -> str:
    """Format a news item cleanly for prompt injection, retaining full summary and key_data_point."""
    pub_time = item.published_at.strftime("%H:%M UTC") if getattr(item, "published_at", None) else "?"
    impact = getattr(item, "impact", "UNKNOWN")
    title = (getattr(item, "title", "") or "").strip()

    summary = (getattr(item, "summary", "") or "").strip()
    if summary and len(summary) > max_summary_chars:
        # Smart sentence boundary truncation
        period_idx = summary.rfind(".", 0, max_summary_chars)
        if period_idx > int(max_summary_chars * 0.7):
            summary = summary[: period_idx + 1]
        else:
            summary = summary[:max_summary_chars] + "..."

    key_dp = (getattr(item, "key_data_point", "") or "").strip()

    import html

    # Sanitize brackets in untrusted title, summary, and key_data_point to prevent spoofing internal system alert headers
    clean_title = title.replace("[", "(").replace("]", ")")
    clean_summary = summary.replace("[", "(").replace("]", ")") if summary else ""
    clean_key_dp = key_dp.replace("[", "(").replace("]", ")") if key_dp else ""
    key_dp_str = f" (Data Point: {clean_key_dp})" if clean_key_dp else ""
    body = (
        f"[{pub_time}] {clean_title}{key_dp_str}\n{clean_summary}"
        if clean_summary
        else f"[{pub_time}] {clean_title}{key_dp_str}"
    )
    safe_impact = html.escape(str(impact), quote=True)
    safe_body = html.escape(body, quote=False)
    return f"<untrusted_news_item impact='{safe_impact}'>\n{safe_body}\n</untrusted_news_item>"


def _normalize_num_variants(n_str: str) -> set[float]:
    """Return all plausible float representations/scales for a numeric token."""
    variants = set()
    if not n_str:
        return variants

    s = n_str.strip().lower()
    # Strip currency symbols, signs, prefixes, and markdown formatting
    s = _re.sub(r"^[+\-±~><$€£¥₣₩₹\s]+", "", s)
    s = s.strip(" \t\n\r:;()[]{}*`\"'")

    mult = 1.0
    is_percent = False
    is_bps = False

    # Check for unit / multiplier suffixes (longest match first with anchor)
    if _re.search(r"\s*(?:basis\s*points?|bps?|bp)$", s):
        is_bps = True
        s = _re.sub(r"\s*(?:basis\s*points?|bps?|bp)$", "", s).strip()
    elif _re.search(r"\s*(?:percentage\s*points?|percent|percentage|pct|pp|%)$", s):
        is_percent = True
        s = _re.sub(r"\s*(?:percentage\s*points?|percent|percentage|pct|pp|%)$", "", s).strip()
    elif _re.search(r"\s*(?:pips?|points?|pts?|years?|yrs?|months?|weeks?|days?|hours?|hrs?|sigma|[xX])$", s):
        s = _re.sub(
            r"\s*(?:pips?|points?|pts?|years?|yrs?|months?|weeks?|days?|hours?|hrs?|sigma|[xX])$", "", s
        ).strip()
    elif _re.search(r"\s*(?:trillions?|tril|\u5146|tn|t)$", s):
        mult = 1_000_000_000_000.0
        s = _re.sub(r"\s*(?:trillions?|tril|\u5146|tn|t)$", "", s).strip()
    elif _re.search(r"\s*(?:billions?|bil|blns?|bns?|b)$", s):
        mult = 1_000_000_000.0
        s = _re.sub(r"\s*(?:billions?|bil|blns?|bns?|b)$", "", s).strip()
    elif _re.search(r"\s*(?:millions?|mlns?|mios?|mm|mn|m)$", s):
        mult = 1_000_000.0
        s = _re.sub(r"\s*(?:millions?|mlns?|mios?|mm|mn|m)$", "", s).strip()
    elif _re.search(r"\s*\u5104$", s):
        mult = 100_000_000.0
        s = _re.sub(r"\s*\u5104$", "", s).strip()
    elif _re.search(r"\s*(?:thousands?|thou|kilo|k)$", s):
        mult = 1_000.0
        s = _re.sub(r"\s*(?:thousands?|thou|kilo|k)$", "", s).strip()

    # Remove commas
    clean = s.replace(",", "").strip()
    try:
        val = float(clean) * mult
        variants.add(round(val, 6))

        # Add scaled equivalents for cross-scale matching
        if mult >= 1_000_000_000_000.0:
            variants.add(round(val / 1e12, 6))
        elif mult >= 1_000_000_000.0:
            variants.add(round(val / 1e9, 6))
        elif mult >= 1_000_000.0:
            variants.add(round(val / 1e6, 6))
        elif mult >= 1_000.0:
            variants.add(round(val / 1e3, 6))

        if is_bps:
            # e.g., 50 bps -> 50.0 (bps value), 0.5 (% value), 0.005 (decimal)
            variants.add(round(val / 100.0, 6))
            variants.add(round(val / 10000.0, 8))
        elif is_percent:
            # e.g., 50% -> 50.0 (percentage), 0.5 (decimal proportion), 5000.0 (bps)
            variants.add(round(val / 100.0, 6))
            variants.add(round(val * 100.0, 4))
        else:
            # If plain decimal <= 1.0 (e.g. 0.5, 0.2, 0.9), also consider % equivalent (50.0, 20.0, 90.0) and bps
            if 0.0 < val <= 1.0:
                variants.add(round(val * 100.0, 4))
                variants.add(round(val * 10000.0, 2))
            # If value looks like percentage points (e.g. 5.0, 25.0, 50.0), also add decimal proportion
            if 1.0 < val <= 100.0:
                variants.add(round(val / 100.0, 6))
    except Exception:
        pass

    return variants


def _flag_ungrounded_numbers(section_text: str, source_news_text: str, extra_context_text: str = "") -> list[str]:
    """Flag numeric claims in section_text that cannot be grounded in source text or context."""
    if not section_text:
        return []

    claimed_tokens = _extract_numeric_claims(section_text)
    if not claimed_tokens:
        return []

    # Build reference numbers from source news and extra context
    source_tokens = _extract_numeric_claims(source_news_text)
    if extra_context_text:
        source_tokens.extend(_extract_numeric_claims(extra_context_text))

    # Also build raw string reference pool for verbatim presence checks
    ref_raw_text = f"{source_news_text or ''} {extra_context_text or ''}".lower()

    # Precompute all valid source float variants
    source_floats = set()
    for s_tok in source_tokens:
        source_floats.update(_normalize_num_variants(s_tok))

    ungrounded = []
    seen_tokens = set()

    for token in claimed_tokens:
        tok_clean = token.strip(" \t\n\r:;()[]{}*`\"'")
        if not tok_clean or tok_clean in seen_tokens:
            continue
        seen_tokens.add(tok_clean)

        # Check verbatim substring presence in raw text
        tok_lower = tok_clean.lower()
        tok_lower_stripped = _re.sub(r"^[+\-±~><$€£¥₣₩₹\s]+", "", tok_lower).strip(" \t\n\r:;()[]{}*`\"'")
        if tok_lower_stripped and tok_lower_stripped in ref_raw_text:
            continue

        tok_variants = _normalize_num_variants(tok_clean)
        if not tok_variants:
            continue

        # Check structural whitelist ONLY for unscaled base numbers (e.g. 1..10, years, horizons)
        # Scaled financial claims like $2B, 25bps, or 5.0% must be grounded in source text!
        has_multiplier = bool(
            _re.search(
                r"(?:[0-9]+(?:\.[0-9]+)?\s*(?:[kmb\u5146\u5104]|thousand|million|billion|trillion|mio|bln|bn|tn|bps|bp|%|percent|pct)|(?:\$|€|£|¥)\s*[0-9]+|\b(?:usd|eur|gbp)\b)",
                tok_lower,
            )
        )
        if not has_multiplier and any(v in _STRUCTURAL_NUMBERS for v in tok_variants):
            continue

        # Check if any variant matches source floats with tolerance
        is_grounded = False
        for cv in tok_variants:
            if cv in source_floats:
                is_grounded = True
                break
            for sf in source_floats:
                # Absolute tolerance for FX rates / small numbers
                if abs(cv - sf) < 0.005:
                    is_grounded = True
                    break
                # Relative tolerance of 1% (e.g. 4550 vs 4552 or rounding)
                denom = max(abs(sf), abs(cv), 1e-6)
                if abs(cv - sf) / denom < 0.01:
                    is_grounded = True
                    break
            if is_grounded:
                break

        if not is_grounded:
            ungrounded.append(tok_clean)

    return ungrounded


def _deduplicate_items_by_title(items: list, threshold: float = 0.78) -> list:
    unique = []
    for item in items:
        title = item.title or ""
        if not any(_jaccard_title_similarity(title, (u.title or "")) > threshold for u in unique):
            unique.append(item)
    return unique


def _keyword_fallback_classify(title: str, summary: str) -> dict:
    text = f"{title} {summary or ''}".lower()
    shock_hits = sum((1 for k in SHOCK_KEYWORDS if k in text))
    high_hits = sum((1 for k in HIGH_IMPACT_KEYWORDS if k in text))
    reaction_words = ["surges", "tumbles", "rallies", "spikes", "slumps", "falls", "jumps", "plunges"]
    has_reaction_word = any((w in text for w in reaction_words))
    # CRITICAL FIX: Keyword fallback TIDAK BOLEH menghasilkan BREAKING.
    # BREAKING memerlukan LLM yang berhasil menjalankan MANDATORY_BREAKING_CHECKLIST penuh.
    # Keyword fallback digunakan hanya saat LLM gagal 2x berturut-turut —
    # justru kondisi paling tidak reliable untuk assign impact tertinggi.
    # Max output fallback = HIGH, yang sudah cukup untuk trigger escalation re-verify.
    if shock_hits >= 1 and (not has_reaction_word):
        impact = "HIGH"  # Was BREAKING — downgrade ke HIGH, LLM akan re-verify jika diperlukan
    elif shock_hits >= 1 or high_hits >= 2:
        impact = "HIGH"
    elif high_hits >= 1:
        impact = "MEDIUM"
    else:
        impact = "LOW"
    from monika.infrastructure.database.adapters import extract_currency_tags

    tags_str = extract_currency_tags(f"{title} {summary or ''}")
    currencies = [c for c in (tags_str.split(",") if tags_str else []) if c] or ["NON"]
    # FIX (P0): sertakan confidence RENDAH secara eksplisit. Tanpa field ini,
    # `item_result.get('confidence') or 1.0` di _detect_under_classification_candidates
    # akan mengevaluasi ke 1.0 ("percaya diri penuh") justru saat kualitas
    # data paling rendah (LLM classifier gagal 2x berturut-turut), sehingga
    # item hasil fallback keyword LOLOS dari re-verifikasi otomatis --
    # bertentangan dengan requirement zero-tolerance misklasifikasi. Nilai
    # 0.35 sengaja di bawah threshold 0.6 agar item ini juga otomatis
    # kena DOWNGRADE_MAP di _validate_classification_batch (BREAKING->HIGH
    # dst.) selain dikirim ke jalur reverify.
    return {
        "impact": impact,
        "confidence": 0.35,
        "surprise_magnitude": "none",
        "currencies": currencies,
        "sentiments": [],
        "_fallback_method": "keyword_weighted",
    }


def _is_zero_based_series(results: list, batch_len: int) -> bool:
    """Detect if the result list uses 0-based indexing (0..batch_len-1)."""
    if not results or not isinstance(results, list):
        return False
    parsed_indices = []
    for r in results:
        if isinstance(r, dict) and "index" in r:
            try:
                c_str = str(r["index"]).strip().rstrip(".:)")
                parsed_indices.append(int(c_str))
            except ValueError, TypeError:
                pass
    return 0 in parsed_indices and batch_len not in parsed_indices


def _resolve_item_index(item_result: dict, batch: list, is_zero_based: bool = False) -> Optional[int]:
    """
    Resolve which item in `batch` corresponds to `item_result`.
    Tolerates:
    - news_id / id matching
    - String indices like "1", "1.", "1)"
    - 0-based vs 1-based index series
    - Out of bounds / invalid data
    Returns 0-based index (0 <= idx < len(batch)) or None if cannot be resolved.
    """
    if not isinstance(item_result, dict) or not batch:
        return None

    # 1. Match via explicit news_id / id if provided
    raw_id = item_result.get("news_id") or item_result.get("id")
    if raw_id is not None:
        try:
            target_id = int(raw_id)
            for i, b_item in enumerate(batch):
                if getattr(b_item, "id", None) == target_id:
                    return i
        except ValueError, TypeError:
            pass

    # 2. Extract raw index
    raw_idx = item_result.get("index")
    if raw_idx is None:
        return None
    try:
        clean_str = str(raw_idx).strip().rstrip(".:)")
        idx_val = int(float(clean_str))
    except ValueError, TypeError:
        return None

    actual_idx = idx_val if is_zero_based else (idx_val - 1)
    if 0 <= actual_idx < len(batch):
        return actual_idx
    return None


def _normalize_contradictions(raw_contradictions: Any) -> list[dict]:
    """
    Normalisasi defensif untuk struktur list kontradiksi dari output LLM verifier.
    Menangani berbagai variasi kunci (claim_a, claimA, claim_1, dsb.) dan memastikan
    tidak ada KeyError saat diakses di downstream formatting/reconciliation.
    """
    if not isinstance(raw_contradictions, list):
        return []
    normalized = []
    for c in raw_contradictions:
        if not isinstance(c, dict):
            continue
        claim_a = (
            c.get("claim_a")
            or c.get("claimA")
            or c.get("claim_1")
            or c.get("claim1")
            or c.get("statement_a")
            or c.get("statement1")
            or c.get("claim")
            or ""
        )
        claim_b = (
            c.get("claim_b")
            or c.get("claimB")
            or c.get("claim_2")
            or c.get("claim2")
            or c.get("statement_b")
            or c.get("statement2")
            or ""
        )
        section_a = c.get("section_a") or c.get("sectionA") or c.get("section_1") or c.get("section1") or "Section A"
        section_b = c.get("section_b") or c.get("sectionB") or c.get("section_2") or c.get("section2") or "Section B"
        severity = str(c.get("severity", "minor")).lower()
        if severity not in ("material", "minor"):
            severity = "material" if any(w in severity for w in ("high", "crit", "mat", "severe")) else "minor"

        if claim_a or claim_b:
            normalized.append(
                {
                    "section_a": str(section_a),
                    "section_b": str(section_b),
                    "claim_a": str(claim_a) if claim_a else "(unspecified claim)",
                    "claim_b": str(claim_b) if claim_b else "(unspecified claim)",
                    "severity": severity,
                }
            )
    return normalized
