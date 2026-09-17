"""
Dynamic Context Compressor — Mengurangi token count data bundle
tanpa kehilangan informasi kritis untuk keputusan trading.

Token estimation: ~4 chars per token (industry standard).
"""
import logging
import json
from typing import Any, List, Dict, Union, Optional

logger = logging.getLogger("TradingAgent.PromptCompressor")


def estimate_tokens(text: str) -> int:
    """Estimasi kasar jumlah token (~4 chars per token)."""
    if not text:
        return 0
    return len(text) // 4


def truncate_to_budget(text: str, max_tokens: int) -> str:
    """
    Truncate text to approximate token budget with Lossless Semantic Slicing (LSS).
    Preserves JSON structure (even when embedded in prompt wrappers) and protects critical trading keys.
    """
    if not text or max_tokens <= 0:
        return ""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text

    PROTECTED_KEYS = {
        "symbol", "price", "current_price", "atr", "atr_14", "adr", "stop_loss", "sl",
        "take_profit", "tp", "entry", "entry_price", "invalidation", "invalidation_price",
        "confluence", "confluence_score", "status", "open_positions", "balance", "equity",
        "margin", "high_impact_events", "ticket", "decision", "indicators", "smc_zones",
        "order_blocks", "fvg_zones", "liquidity_zones", "swing_points", "structure_breaks",
        "levels", "optimal_levels", "fibonacci", "rationale", "bias", "direction",
        "currency_bias", "risk_sentiment", "confidence", "market_regime", "macro_regime",
        "real_us10y_yield_pct", "gold_macro_bias", "risk_multiplier", "adjusted_entry",
        "adjusted_sl", "adjusted_tp", "market_chronicle", "macro_reality", "fvg", "ob",
        "bos", "choch", "liquidity_sweep", "candles", "ohlcv", "price_history", "history", "rates"
    }

    def _prune_data_structure(data: Any, target_char_budget: int) -> Any:
        if isinstance(data, dict):
            pruned = dict(data)
            # Pass 1: Prune via structural LFSP handler
            for k in list(pruned.keys()):
                val = pruned[k]
                if k.lower() not in PROTECTED_KEYS:
                    if isinstance(val, list):
                        pruned[k] = _prune_data_structure(val, target_char_budget // max(1, len(pruned)))
                    elif isinstance(val, str) and estimate_tokens(val) > 150:
                        pruned[k] = val[:400] + "... [summarized]"
            if len(json.dumps(pruned, default=str)) <= target_char_budget:
                return pruned

            # Pass 2: Recurse into nested structures
            for k in list(pruned.keys()):
                if isinstance(pruned[k], (dict, list)):
                    pruned[k] = _prune_data_structure(pruned[k], target_char_budget // max(1, len(pruned)))
            return pruned
        elif isinstance(data, list):
            if not data:
                return data
            # Lossless Financial Structural Projection (LFSP)
            first = data[0]
            if isinstance(first, dict):
                # A. SMC Zones (OB, FVG, Liquidity pools)
                is_zone_list = any(k in first for k in ("price_high", "price_low", "zone_type", "type"))
                if is_zone_list:
                    unmitigated = [
                        d for d in data
                        if isinstance(d, dict) and not d.get("is_mitigated", False) and not d.get("mitigated", False)
                    ]
                    candidates = unmitigated if unmitigated else data
                    while len(candidates) > 2 and len(json.dumps(candidates, default=str)) > target_char_budget:
                        candidates = candidates[1:]
                    return candidates

                # B. OHLCV Candles (open, high, low, close)
                is_ohlcv = all(k in first for k in ("open", "high", "low", "close"))
                if is_ohlcv:
                    if len(json.dumps(data, default=str)) <= target_char_budget:
                        return data
                    
                    # Need compression to fit budget
                    highest_bar = max(data, key=lambda x: float(x.get("high", 0.0)))
                    lowest_bar = min(data, key=lambda x: float(x.get("low", float("inf"))))
                    first_bar = data[0]
                    recent = data[-4:] if len(data) >= 4 else data
                    
                    # Core structural anchors that must never be dropped
                    anchors = {id(b): b for b in [first_bar, highest_bar, lowest_bar] + recent}
                    
                    # Estimate how many total bars fit in target_char_budget
                    avg_bar_size = max(1, len(json.dumps(first, default=str)) + 2)
                    target_count = max(len(anchors), target_char_budget // avg_bar_size)
                    
                    if len(data) > target_count:
                        # Stride subsampling across full dataset to preserve continuity
                        stride = max(1, len(data) // target_count)
                        sampled = data[::stride]
                        # Merge anchors into sampled bars
                        for a in anchors.values():
                            if id(a) not in {id(b) for b in sampled}:
                                sampled.append(a)
                        candidates = sorted(sampled, key=lambda x: str(x.get("time") or ""))
                    else:
                        candidates = list(data)
                        
                    while len(candidates) > len(anchors) and len(json.dumps(candidates, default=str)) > target_char_budget:
                        # Drop non-anchor older bars first
                        non_anchor_idx = [i for i, b in enumerate(candidates) if id(b) not in anchors]
                        if non_anchor_idx:
                            candidates.pop(non_anchor_idx[0])
                        else:
                            break
                            
                    return sorted(candidates, key=lambda x: str(x.get("time") or ""))

                # C. Economic calendar: strictly prioritize HIGH/MEDIUM impact
                if any("impact" in d for d in data if isinstance(d, dict)):
                    high_med = [
                        d for d in data
                        if isinstance(d, dict) and str(d.get("impact", "")).upper() in ("HIGH", "MEDIUM", "CRITICAL")
                    ]
                    candidates = high_med if high_med else data
                    while len(candidates) > 2 and len(json.dumps(candidates, default=str)) > target_char_budget:
                        candidates = candidates[1:]
                    return candidates

                candidates = list(data)
                while len(candidates) > 2 and len(json.dumps(candidates, default=str)) > target_char_budget:
                    candidates = candidates[1:]
                return candidates
            return data[-6:] if len(data) > 6 else data
        return data

    trimmed = text.strip()

    # 1. Pure JSON root
    if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
        try:
            parsed = json.loads(trimmed)
            curr_budget = max_chars
            res_str = trimmed
            for _ in range(4):
                pruned_data = _prune_data_structure(parsed, curr_budget)
                res_str = json.dumps(pruned_data, default=str)
                if len(res_str) <= max_chars:
                    return res_str
                curr_budget = int(curr_budget * 0.7)
            return res_str
        except Exception:
            pass

    # 2. Embedded JSON inside text / prompt wrapper (e.g. "Prompt:\n{...}")
    import re
    match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', text)
    if match:
        start_idx, end_idx = match.span()
        prefix = text[:start_idx]
        suffix = text[end_idx:]
        json_candidate = match.group(0)
        try:
            parsed = json.loads(json_candidate)
            budget_for_json = max_chars - len(prefix) - len(suffix) - 50
            if budget_for_json > 200:
                pruned_json = _prune_data_structure(parsed, budget_for_json)
                assembled = prefix + json.dumps(pruned_json, default=str) + suffix
                if len(assembled) <= max_chars:
                    return assembled
        except Exception:
            pass

    # 3. Non-JSON text fallback: clean boundary cut at newline or sentence
    # SOTA Section Protection: Preserve critical tail blocks like [STRESS TEST], [INVALIDATION], and [ACTIVE MACRO CHRONICLE]
    stress_match = re.search(r'\[STRESS TEST:[\s\S]*?\]', text)
    stress_block = stress_match.group(0) if stress_match else ""

    inval_match = re.search(r'\[INVALIDATION:[\s\S]*?\]', text)
    inval_block = inval_match.group(0) if inval_match else ""

    chronicle_match = re.search(r'\[ACTIVE MACRO (?:CHRONICLE|REALITY):[\s\S]*?\]', text)
    chronicle_block = chronicle_match.group(0) if chronicle_match else ""

    protected_tail = ""
    if stress_block and stress_block not in text[:max_chars // 2]:
        protected_tail += "\n" + stress_block
    if inval_block and inval_block not in text[:max_chars // 2]:
        protected_tail += "\n" + inval_block
    if chronicle_block and chronicle_block not in text[:max_chars // 2]:
        protected_tail += "\n" + chronicle_block

    budget_for_body = max_chars - len(protected_tail) - 50
    if budget_for_body > 100:
        safe_cut = text[:budget_for_body]
        last_nl = safe_cut.rfind("\n")
        if last_nl > budget_for_body // 2:
            safe_cut = safe_cut[:last_nl]
        else:
            last_dot = safe_cut.rfind(".")
            if last_dot > budget_for_body // 2:
                safe_cut = safe_cut[:last_dot + 1]
        return safe_cut + "\n[TRUNCATED — budget exceeded]" + protected_tail

    safe_cut = text[:max_chars]
    last_nl = safe_cut.rfind("\n")
    if last_nl > max_chars // 2:
        safe_cut = safe_cut[:last_nl]
    else:
        last_dot = safe_cut.rfind(".")
        if last_dot > max_chars // 2:
            safe_cut = safe_cut[:last_dot + 1]
    return safe_cut + "\n[TRUNCATED — budget exceeded]"



class ContextCompressor:
    """Kompres data bundle sebelum injeksi ke LLM prompt."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}

    def compress_ohlcv(self, bars: List[Dict[str, Any]], max_bars: int = 20) -> List[Dict[str, Any]]:
        """Subsample bars using regular stride without dropping chronological continuity."""
        if not bars or len(bars) <= max_bars:
            return bars
        # Keep last bars (most recent sequence)
        recent_count = min(10, max_bars // 2)
        recent = bars[-recent_count:]
        older = bars[:-recent_count]
        
        remaining_slots = max_bars - recent_count
        if older and remaining_slots > 0:
            stride = max(1, (len(older) + remaining_slots - 1) // remaining_slots)
            subsampled_older = older[::stride][-remaining_slots:]
            combined = subsampled_older + recent
        else:
            combined = recent
            
        return sorted(combined, key=lambda b: str(b.get('time', '')))

    def compress_indicators(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Drop neutral indicators. Keep extreme/decisive values only."""
        if not indicators:
            return {}
        compressed = {}
        for key, value in indicators.items():
            if isinstance(value, dict):
                compressed[key] = value
                continue
            try:
                val = float(value)
            except (TypeError, ValueError):
                compressed[key] = value
                continue

            k_lower = key.lower()
            # Keep RSI if extreme
            if 'rsi' in k_lower:
                if val < 35 or val > 65:
                    compressed[key] = value
            # Keep MACD
            elif 'macd' in k_lower:
                compressed[key] = value
            # Keep BBands
            elif 'bb' in k_lower or 'band' in k_lower:
                compressed[key] = value
            # Keep SMAs/EMAs for trend
            elif 'sma' in k_lower or 'ema' in k_lower:
                compressed[key] = value
            # Keep ADX / ATR
            elif 'adx' in k_lower or 'atr' in k_lower:
                compressed[key] = value
            # Drop neutral stochastics
            elif 'stoch' in k_lower:
                if val <= 25 or val >= 75:
                    compressed[key] = value
            else:
                compressed[key] = value
        return compressed

    def compress_stage1_dict(self, data: Dict[str, Any], max_tokens: int = 6000) -> str:
        """Kompres Stage 1 macro data dictionary secara semantik dan JSON-safe."""
        if not data:
            return "{}"

        # 1. Semantic pruning on in-memory object
        pruned = dict(data)

        # Prune economic_calendar events if large, prioritizing high & medium impact
        ec = pruned.get("economic_calendar")
        if isinstance(ec, dict) and isinstance(ec.get("events"), list) and len(ec["events"]) > 15:
            events = ec["events"]
            impact_map = {"critical": 4, "high": 3, "medium": 2, "low": 1}
            # Preserve high/critical impact events, then medium, then closest low-impact
            high_critical = [e for e in events if impact_map.get(str(e.get("impact", "")).lower(), 0) >= 3]
            medium_impact = [e for e in events if impact_map.get(str(e.get("impact", "")).lower(), 0) == 2]
            low_impact = [e for e in events if impact_map.get(str(e.get("impact", "")).lower(), 0) <= 1]
            
            selected_events = high_critical + medium_impact
            if len(selected_events) < 15:
                selected_events += low_impact[:(15 - len(selected_events))]
            elif len(selected_events) > 20:
                selected_events = selected_events[:20]
                
            pruned["economic_calendar"] = dict(ec)
            pruned["economic_calendar"]["events"] = selected_events

        # Prune news items, prioritizing breaking & high-importance news
        news = pruned.get("news_digest")
        if isinstance(news, dict) and isinstance(news.get("items"), list) and len(news["items"]) > 10:
            items = news["items"]
            breaking_high = [
                i for i in items 
                if (isinstance(i, dict) and (i.get("is_breaking") or str(i.get("impact", "")).lower() in ("high", "critical")))
            ]
            others = [i for i in items if i not in breaking_high]
            selected_items = breaking_high + others
            pruned["news_digest"] = dict(news)
            pruned["news_digest"]["items"] = selected_items[:12]

        # Prune DXY & VIX history
        for k in ("dxy", "vix"):
            item = pruned.get(k)
            if isinstance(item, dict) and isinstance(item.get("history"), list) and len(item["history"]) > 10:
                pruned[k] = dict(item)
                pruned[k]["history"] = item["history"][:10]

        serialized = json.dumps(pruned, default=str)
        if estimate_tokens(serialized) <= max_tokens:
            return serialized

        # 2. Aggressive pruning if still over budget (drop lengthy history arrays)
        for k in ("dxy", "vix", "treasury_yields", "interest_rates"):
            item = pruned.get(k)
            if isinstance(item, dict) and "history" in item:
                pruned[k] = {k2: v2 for k2, v2 in item.items() if k2 != "history"}

        serialized = json.dumps(pruned, default=str)
        return serialized

    def compress_stage1_bundle(self, bundle: Union[str, Dict[str, Any]], max_tokens: int = 6000) -> str:
        """Kompres Stage 1 macro data bundle (JSON-safe, never truncates into invalid JSON)."""
        if not bundle:
            return "{}" if isinstance(bundle, dict) else ""

        if isinstance(bundle, dict):
            return self.compress_stage1_dict(bundle, max_tokens=max_tokens)

        # If already string, try loading as JSON for safe pruning
        try:
            parsed = json.loads(bundle)
            if isinstance(parsed, dict):
                return self.compress_stage1_dict(parsed, max_tokens=max_tokens)
        except Exception:
            pass

        current_tokens = estimate_tokens(bundle)
        if current_tokens <= max_tokens:
            return bundle

        return truncate_to_budget(bundle, max_tokens)

    def _prune_text_bundle_safely(self, text: str, max_tokens: int = 8000) -> str:
        """Pangkas text bundle secara semantik dan aman tanpa memotong bagian esensial."""
        if not text or estimate_tokens(text) <= max_tokens:
            return text

        lines = text.split("\n")
        # 1. Bersihkan baris kosong berulang & garis dekoratif berlebih
        cleaned_lines = []
        prev_blank = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if not prev_blank:
                    cleaned_lines.append("")
                    prev_blank = True
            else:
                prev_blank = False
                cleaned_lines.append(line)

        cleaned_text = "\n".join(cleaned_lines)
        if estimate_tokens(cleaned_text) <= max_tokens:
            return cleaned_text

        # 2. Pangkas price history table ke 12 bar terakhir jika ada
        if "time,O,H,L,C" in cleaned_text:
            out_lines = []
            in_price = False
            price_buf = []
            for line in cleaned_lines:
                if "time,O,H,L,C" in line:
                    in_price = True
                    out_lines.append(line)
                    price_buf = []
                elif in_price and (line.startswith("──") or line.startswith("###") or line.startswith("GET ") or not line.strip()):
                    if price_buf:
                        kept = price_buf[-12:] if len(price_buf) > 12 else price_buf
                        out_lines.extend(kept)
                    in_price = False
                    price_buf = []
                    out_lines.append(line)
                elif in_price:
                    price_buf.append(line)
                else:
                    out_lines.append(line)
            if in_price and price_buf:
                kept = price_buf[-12:] if len(price_buf) > 12 else price_buf
                out_lines.extend(kept)
            cleaned_text = "\n".join(out_lines)
            if estimate_tokens(cleaned_text) <= max_tokens:
                return cleaned_text

        # 3. Pangkas teks berita panjang jika masih over-budget (SENTIMEN & STRUKTUR DILINDUNGI PENUH)
        filtered_lines = []
        for line in cleaned_text.split("\n"):
            # Pangkas body berita panjang tapi pertahankan headline dan sentimen
            if line.startswith("• [") and len(line) > 160:
                filtered_lines.append(line[:157] + "...")
            else:
                filtered_lines.append(line)

        pruned_result = "\n".join(filtered_lines)
        if estimate_tokens(pruned_result) > max_tokens:
            # Lindungi mandatory tail blocks (ADR, PI, Alpha Lessons, Efficiency Protocol)
            mandatory_markers = [
                "── DAILY RANGE CONTEXT (ADR)",
                "── AUTOMATED PRICED-IN SUBSCORES",
                "── RECENT ALPHA LESSONS",
                "# EFFICIENCY PROTOCOL",
            ]
            tail_start_idx = -1
            for marker in mandatory_markers:
                idx = pruned_result.find(marker)
                if idx != -1:
                    if tail_start_idx == -1 or idx < tail_start_idx:
                        tail_start_idx = idx

            if tail_start_idx != -1:
                body = pruned_result[:tail_start_idx]
                tail = pruned_result[tail_start_idx:]
                tail_tokens = estimate_tokens(tail)
                body_budget = max(500, max_tokens - tail_tokens)
                if estimate_tokens(body) > body_budget:
                    body = truncate_to_budget(body, body_budget)
                pruned_result = body + "\n\n" + tail
            else:
                pruned_result = truncate_to_budget(pruned_result, max_tokens)
        return pruned_result

    def compress_stage2_dict(self, data: Dict[str, Any], max_tokens: int = 8000) -> str:
        """Kompres Stage 2 dictionary secara semantik berbasis dict/JSON-safe."""
        if not data:
            return "{}"

        pruned = dict(data)
        # Pangkas array price history jika ada
        for k, v in list(pruned.items()):
            if "price_history" in k.lower() and isinstance(v, dict) and "bars" in v:
                bars = v.get("bars", [])
                if len(bars) > 15:
                    pruned[k] = dict(v)
                    pruned[k]["bars"] = bars[-15:]

        serialized = json.dumps(pruned, default=str)
        if estimate_tokens(serialized) <= max_tokens:
            return serialized

        # Subsample indikator netral
        for k, v in list(pruned.items()):
            if "indicator" in k.lower() and isinstance(v, dict):
                pruned[k] = self.compress_indicators(v)

        return json.dumps(pruned, default=str)

    def compress_stage2_bundle(self, bundle: Union[str, Dict[str, Any]], symbol: str = "", max_tokens: int = 8000) -> str:
        """Kompres Stage 2 per-asset data bundle tanpa pernah memotong data mandatory (ADR, PI, Alpha Lessons)."""
        if not bundle:
            return ""

        if isinstance(bundle, dict):
            return self.compress_stage2_dict(bundle, max_tokens=max_tokens)

        # Jika sudah berupa string JSON, coba parse
        if isinstance(bundle, str):
            trimmed = bundle.strip()
            if trimmed.startswith("{") and trimmed.endswith("}"):
                try:
                    parsed = json.loads(trimmed)
                    if isinstance(parsed, dict):
                        return self.compress_stage2_dict(parsed, max_tokens=max_tokens)
                except Exception:
                    pass
            return self._prune_text_bundle_safely(bundle, max_tokens=max_tokens)

        return str(bundle)
