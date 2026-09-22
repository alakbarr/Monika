from typing import TypedDict, Annotated, List, Dict, Any, Optional, Union
import operator

def merge_dicts(a: Dict, b: Dict) -> Dict:
    """
    Deep merge two dicts. Top-level keys from b override a,
    but nested dicts are merged recursively (not overwritten).
    This prevents data loss when nodes update the same nested key.
    Supports tombstoning: if a value in b is None or '_DELETED_', the key is removed.
    """
    merged = a.copy()
    for k, v in b.items():
        if v is None or v == "_DELETED_":
            merged.pop(k, None)
        elif k in merged and isinstance(merged[k], dict) and isinstance(v, dict):
            merged[k] = merge_dicts(merged[k], v)
        else:
            merged[k] = v
    return merged
def _item_key(item: Any) -> Any:
    try:
        hash(item)
        return (0, item)
    except TypeError:
        if isinstance(item, dict):
            try:
                return (1, tuple(sorted((k, _item_key(v)) for k, v in item.items())))
            except Exception:
                return (2, repr(item))
        elif isinstance(item, (list, set, tuple)):
            try:
                return (3, tuple(_item_key(x) for x in item))
            except Exception:
                return (2, repr(item))
        return (2, repr(item))

def merge_lists(a: List, b: List) -> List:
    """Concatenate two lists with order-preserving O(N) deduplication."""
    res: List[Any] = []
    seen = set()
    for item in (a or []):
        k = _item_key(item)
        if k not in seen:
            seen.add(k)
            res.append(item)
    for item in (b or []):
        k = _item_key(item)
        if k not in seen:
            seen.add(k)
            res.append(item)
    return res


class TradingSummary(TypedDict, total=False):
    cycle_time: str
    processed_assets: int
    actionable_count: int
    executed_count: int
    failed_count: int
    elapsed_total_s: Optional[float]

    # Data gathering & precomputations
    scraping: Dict[str, Any]
    data_refresh: Any
    price_fetch: Any
    price_fetch_m15: Any
    indicators: Any
    structure: Any
    macro_precompute: Union[str, Dict[str, Any]]
    performance_notes: Dict[str, Any]
    data_validation: Dict[str, Any]
    vix_halt: Dict[str, Any]
    macro_regime: Dict[str, Any]

    # Fundamental & Stage 1
    skipped_reason: Optional[str]
    fundamental: Dict[str, Any]
    fundamental_shift_alert: Dict[str, Any]
    ssvp_cds_score: Optional[float]
    ssvp_message: Optional[str]
    ssvp_warning: Optional[str]
    ssvp_reconciliation_context: Optional[str]

    # Stage 2 & SSVP
    per_asset: Dict[str, Any]
    per_asset_errors: List[Dict[str, Any]]
    ssvp_suppressed_symbols: List[str]
    contradiction_filter_applied: Optional[bool]
    context_version_split_detected: Optional[bool]
    context_version_split_detail: Optional[str]

    # Debate & Reflection
    debate_approved: List[str]
    debate_rejected: List[str]
    reflection_filtered: Optional[str]
    reflection_score_inflation_suspected: Optional[bool]
    reflection_vix_filtered: Optional[str]
    reflection_contradiction_filtered: Optional[str]
    reflection_macro_inconsistent_filtered: List[str]
    reflection_all_macro_inconsistent: Optional[bool]

    # Risk Gate & Execution
    portfolio_synthesis_approved: List[str]
    execution: Optional[Dict[str, Any]]
    api_cost_usd: Optional[float]
    plan_refinements: Optional[Any]
    is_ad_hoc: Optional[bool]
    custom_context: Optional[str]
    confluence_filter: Optional[Any]
    reactive_event: Optional[Any]
    adhoc_verdicts: Optional[Dict[str, Any]]

class AssetDecisionSummary(TypedDict, total=False):
    decision: str
    confidence: float
    analysis_id: Optional[int]
    confluence_score: Optional[int]
    priced_in_score: Optional[int]
    elapsed_s: Optional[float]

class TradingState(TypedDict):
    """
    State utama yang mengalir di seluruh node LangGraph.
    Semua komponen akan membaca dan memodifikasi state ini.
    """
    # Context & Data
    symbols: List[str]                  # Daftar simbol yang akan dianalisis
    market_regime: str                  # Hasil identifikasi rezim pasar
    vix_level: Optional[float]          # Current VIX for routing
    brief_confidence: Optional[float]   # Stage 1 confidence for threshold adjustment
    
    # Per-Asset Analysis Results
    asset_analyses: Annotated[Dict[str, Dict[str, Any]], merge_dicts]
    debate_states: Annotated[Dict[str, Dict[str, Any]], merge_dicts]
    risk_debate_states: Annotated[Dict[str, Dict[str, Any]], merge_dicts]
    investment_verdicts: Annotated[Dict[str, Dict[str, Any]], merge_dicts]
    portfolio_decisions: Annotated[Dict[str, Dict[str, Any]], merge_dicts]
    
    # Decisions & Execution
    # PENTING: Bidang narrowing pipeline ini TIDAK memakai reducer agar node hilir dapat memfilter trade
    approved_trades: List[tuple]
    
    # Control flags
    errors: Annotated[List[str], merge_lists]
    should_pause: bool
    
    # --- Orkestrasi Khusus AI Trading Agent ---
    weekend_symbols_override: Optional[List[str]]
    stale_assets: Annotated[List[str], merge_lists]
    summary: Annotated[TradingSummary, merge_dicts]
    actionable_trades: List[tuple]
    reflection_applied: Optional[bool]
    
    node_errors: Annotated[Dict[str, str], merge_dicts]
    data_quality_scores: Annotated[Dict[str, float], merge_dicts]
    cycle_id: str
    fundamental_retry_count: int
    
    # Cross-cycle persistent insights
    prior_cycle_insights: Dict[str, Any]  # Patterns from previous cycle
    consecutive_wait_count: int  # How many cycles produced only WAIT decisions
    last_buy_sell_cycle: Optional[str]  # ISO timestamp of last cycle with buy/sell

    # NEW: SSVP Tracking
    ssvp_per_symbol_contexts: Dict[str, str]
    ssvp_cds_score: Optional[float]
    ssvp_blocked: bool
    ssvp_reconciliation_context: Optional[str]
    context_snapshot_id: Optional[str]
    ssvp_retry_count: int

    # Operator Market Intelligence & Directives (AMIDR)
    user_market_intel: Annotated[List[Dict[str, Any]], merge_lists]

    # Phase 3: Bidirectional Dynamic Re-Planning Loop (LangGraph Backtracking)
    refinement_count: int
    rejection_feedback: Optional[Dict[str, Any]]
    is_negotiable_rejection: bool
