import re
import logging
from collections import Counter
from typing import List, Dict, Any, Optional
import utils.clock as clock

logger = logging.getLogger("TradingAgent.LessonConsolidator")

def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase alphanumeric words, filtering out common stopwords."""
    stopwords = {
        "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with",
        "by", "from", "is", "was", "are", "were", "be", "been", "trade", "next",
        "win", "loss", "breakeven", "whatif", "entry", "exit", "should", "could",
        "would", "market", "price", "dan", "di", "ke", "dari", "yang", "untuk",
        "pada", "dengan", "ini", "itu", "atau", "adalah", "posisi"
    }
    words = re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', text.lower())
    return {w for w in words if w not in stopwords}

def _overlap_similarity(set1: set[str], set2: set[str]) -> float:
    """Compute Overlap (Simpson) coefficient between two token sets for robust short text clustering."""
    if not set1 or not set2:
        return 0.0
    intersection = len(set1 & set2)
    min_len = min(len(set1), len(set2))
    return float(intersection) / float(min_len) if min_len > 0 else 0.0

def cluster_lessons_semantically(
    lessons: List[str],
    similarity_threshold: float = 0.30,
    min_cluster_size: int = 2,
) -> List[Dict[str, Any]]:
    """
    Groups raw trade lessons into semantic theme clusters using token similarity.
    Filters out one-off isolated noise (clusters with size < min_cluster_size)
    to prevent short-term noise overfitting in prompt memory.
    
    Returns:
        List of dicts containing {'representative_lesson': str, 'frequency': int, 'all_items': list[str]}
    """
    if not lessons:
        return []
        
    tokenized_items = [(_tokenize(item), item) for item in lessons]
    clusters: List[List[tuple[set[str], str]]] = []
    
    for tokens, text in tokenized_items:
        if not tokens:
            continue
        assigned = False
        for cluster in clusters:
            avg_sim = sum(_overlap_similarity(tokens, c_tokens) for c_tokens, _ in cluster) / len(cluster)
            if avg_sim >= similarity_threshold:
                cluster.append((tokens, text))
                assigned = True
                break
        if not assigned:
            clusters.append([(tokens, text)])
            
    results = []
    for cluster in clusters:
        freq = len(cluster)
        # Filter one-off noise unless very few lessons exist overall
        if freq >= min_cluster_size or len(lessons) <= 3:
            rep = max(cluster, key=lambda x: len(x[1]))[1]
            results.append({
                "representative_lesson": rep,
                "frequency": freq,
                "all_items": [x[1] for x in cluster]
            })
            
    results.sort(key=lambda x: x["frequency"], reverse=True)
    return results


async def consolidate_lessons_to_playbook(session, settings, auto_propose_only: bool = True) -> str | None:
    from database.models import DecisionReflection, CandidateLesson
    from analysis.providers.llm_factory import get_client_for_task
    from sqlalchemy import select
    from datetime import datetime, timezone, timedelta
    from pathlib import Path

    now = clock.now()
    since = now - timedelta(days=60)
    
    symbols = (settings or {}).get('trading', {}).get('asset_universe', ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'BTCUSD'])
    all_rows = []
    # Symbol-partitioned query to ensure equitable multi-asset representation (max 30 per symbol)
    for sym in symbols:
        sym_rows = (await session.execute(
            select(DecisionReflection).where(DecisionReflection.status == 'resolved')
            .where(DecisionReflection.symbol == sym)
            .where(DecisionReflection.resolved_at >= since)
            .where(DecisionReflection.specific_lesson.is_not(None))
            .where(DecisionReflection.specific_lesson != '')
            .order_by(DecisionReflection.resolved_at.desc()).limit(30)
        )).scalars().all()
        all_rows.extend(sym_rows)

    # General query fallback / fill-up if symbol query yields fewer than 50 rows
    if len(all_rows) < 50:
        general_rows = (await session.execute(
            select(DecisionReflection).where(DecisionReflection.status == 'resolved')
            .where(DecisionReflection.resolved_at >= since)
            .where(DecisionReflection.specific_lesson.is_not(None))
            .where(DecisionReflection.specific_lesson != '')
            .order_by(DecisionReflection.resolved_at.desc()).limit(150)
        )).scalars().all()
        seen_ids = {r.id for r in all_rows}
        for r in general_rows:
            if r.id not in seen_ids:
                all_rows.append(r)
                seen_ids.add(r.id)

    # Exclude normal market variance losses where process was sound
    rows = [r for r in all_rows if not (r.process_was_sound and not r.was_profitable)]
    if len(rows) < 30:
        return None

    by_symbol = {}
    for r in rows:
        if r.is_paper_whatif:
            tag = 'WHATIF'
        else:
            tag = 'WIN' if r.was_profitable else 'LOSS' if r.was_profitable is False else 'BREAKEVEN'
            
        by_symbol.setdefault(r.symbol, []).append(
            f"- [{r.resolved_at.strftime('%Y-%m-%d') if r.resolved_at else '?'}] ({tag}) "
            f"{r.specific_lesson} -> Next: {r.next_trade_adjustment or 'N/A'}"
        )

    prompt = (
        "Below are statistically corroborated trading lessons over 60 days, pre-clustered "
        "and filtered against one-off noise. Each bullet point has been observed across multiple trades.\n"
        "For each symbol, produce a short reconciled playbook: merge redundant rules, resolve contradictions "
        "by prioritizing higher frequency corroborated patterns.\n\n"
    )
    for sym, lessons in by_symbol.items():
        clustered = cluster_lessons_semantically(lessons, similarity_threshold=0.25, min_cluster_size=2)
        if clustered:
            formatted_lessons = [
                f"{c['representative_lesson']} [Corroborated by {c['frequency']} trades]"
                for c in clustered[:15]
            ]
            prompt += f"## {sym}\n" + "\n".join(formatted_lessons) + "\n\n"

    prompt += "\nOutput: markdown, one section per symbol, max 5 bullet points, each a single actionable conditional rule."

    client = get_client_for_task('trade_reflection', settings)
    content = await client.generate(prompt, system='You are a trading playbook editor. Be terse and specific.')
    if not content:
        return None

    # Enforce Declarative Memory Rule
    content = enforce_declarative_memory_rule(content)

    from database.safe_ops import safe_commit
    # Save candidate lessons to database for shadow out-of-sample validation
    for sym in by_symbol:
        sym_block = ""
        if f"## {sym}" in content:
            parts = content.split(f"## {sym}")
            if len(parts) > 1:
                sym_block = parts[1].split("## ")[0].strip()
        if not sym_block:
            sym_block = content[:300].strip()

        candidate = CandidateLesson(
            symbol=sym,
            lesson_text=sym_block,
            status='shadow',
            proposed_at=now,
            evaluated_trades_count=0
        )
        session.add(candidate)
    await safe_commit(session, label="lesson_consolidation")

    # If explicitly asked to write immediately (e.g. initial setup)
    if not auto_propose_only:
        await promote_lesson_to_playbook(content)

    return content


def enforce_declarative_memory_rule(text: str) -> str:
    """
    Declarative Memory Rule.
    Prevents persistent memory files from hijacking future prompts with imperative directives.
    Converts imperative commands ('Always do X', 'Never trade Y') into declarative empirical facts.
    """
    if not text:
        return text

    lines = text.split("\n")
    cleaned_lines = []

    TRANSFORMATIONS = [
        (r'^\s*[-*]\s*(?:always\s+check|ensure\s+to\s+check|make\s+sure\s+to\s+check)\s+', '- Empirical observation: Checking '),
        (r'^\s*[-*]\s*(?:never\s+enter|do\s+not\s+enter|don\'t\s+enter)\s+', '- Empirical risk: Entering '),
        (r'^\s*[-*]\s*(?:never\s+trade|do\s+not\s+trade|don\'t\s+trade)\s+', '- Empirical risk: Trading '),
        (r'^\s*[-*]\s*(?:must\s+wait\s+for|wait\s+for)\s+', '- Historical precedent: Waiting for '),
        (r'^\s*[-*]\s*(?:jangan\s+pernah|jangan\s+entry|jangan\s+trade)\s+', '- Pengamatan risiko empiris: Entry '),
        (r'^\s*[-*]\s*(?:selalu\s+cek|wajib\s+cek|harus\s+cek)\s+', '- Fakta empiris: Pemeriksaan '),
    ]

    for line in lines:
        cleaned = line
        for pat, repl in TRANSFORMATIONS:
            if re.search(pat, cleaned, re.IGNORECASE):
                cleaned = re.sub(pat, repl, cleaned, flags=re.IGNORECASE)
                break
        cleaned_lines.append(cleaned)

    return "\n".join(cleaned_lines)


async def promote_lesson_to_playbook(content: str) -> None:
    """Selectively appends or updates verified candidate lessons in lessons_learned.md per symbol."""
    from pathlib import Path
    import re
    now = clock.now()
    path = Path(__file__).resolve().parent.parent.parent / 'skills' / 'trading' / 'lessons_learned.md'
    existing_text = path.read_text(encoding='utf-8') if path.exists() else ""
    
    section_marker = "## 4. Pelajaran Empiris Terkonsolidasi (Auto-Consolidated)"
    
    if section_marker in existing_text:
        parts = existing_text.split(section_marker, 1)
        base_rules = parts[0].strip()
        sec4_content = parts[1].strip()
        sec4_body = re.sub(r'^\*\([^)]+\)\*\s*', '', sec4_content).strip()
    else:
        base_rules = existing_text.strip()
        sec4_body = ""

    # Parse symbol from content (e.g. "### EURUSD")
    sym_match = re.search(r'###\s+([A-Za-z0-9/_-]+)', content)
    if sym_match and sec4_body:
        target_sym = sym_match.group(1).upper()
        sym_pattern = re.compile(rf'(###\s+{re.escape(target_sym)}\b[\s\S]*?)(?=(?:\n###\s+[A-Za-z0-9/_-]+|\Z))', re.IGNORECASE)
        if sym_pattern.search(sec4_body):
            sec4_body = sym_pattern.sub(content.strip(), sec4_body)
        else:
            sec4_body = f"{sec4_body}\n\n{content.strip()}".strip()
    elif content.strip():
        if sec4_body:
            sec4_body = f"{sec4_body}\n\n{content.strip()}"
        else:
            sec4_body = content.strip()

    updated_content = (
        f"{base_rules}\n\n"
        f"{section_marker}\n"
        f"*(Diperbarui tervalidasi OOS: {now.strftime('%Y-%m-%d')})*\n\n"
        f"{sec4_body}\n"
    )
    
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(updated_content, encoding='utf-8')
    try:
        from skills.loader import invalidate_cache
        invalidate_cache()
    except Exception:
        pass


async def auto_promote_high_confidence_rules(session, settings: Optional[Dict[str, Any]] = None) -> List[int]:
    """
    Evaluates shadow CandidateLesson entries in DB for immediate or high-confidence auto-promotion.
    Promotes if:
    1. Evaluated trades >= min_eval_trades (default 3) and win_rate_delta >= 0.05
    2. Or corroboration count in lesson_text >= min_corroboration (default 3) with non-negative delta
    Rejects if:
    Evaluated trades >= 5 and win_rate_delta <= -0.08
    """
    from database.models import CandidateLesson
    from database.safe_ops import safe_commit
    from sqlalchemy import select

    min_eval = (settings or {}).get("trading", {}).get("memory", {}).get("min_eval_trades_promote", 3)
    min_corrob = (settings or {}).get("trading", {}).get("memory", {}).get("min_corroboration_promote", 3)

    candidates = (await session.execute(
        select(CandidateLesson)
        .where(CandidateLesson.status == 'shadow')
    )).scalars().all()

    promoted_ids = []
    now = clock.now()

    for cand in candidates:
        text = cand.lesson_text or ""
        # Check corroboration count if present, e.g., "[Corroborated by 4 trades]"
        corrob_match = re.search(r'\[Corroborated by (\d+) trades\]', text)
        corrob_count = int(corrob_match.group(1)) if corrob_match else 0

        wr_delta = float(cand.win_rate_delta or 0.0)
        sharpe_delta = float(cand.sharpe_delta or 0.0)
        eval_count = int(cand.evaluated_trades_count or 0)

        is_high_perf = eval_count >= min_eval and (wr_delta >= 0.05 or sharpe_delta > 0.1)
        is_high_corrob = corrob_count >= min_corrob and wr_delta >= 0.0

        if is_high_perf or is_high_corrob:
            cand.status = 'promoted'
            cand.promoted_at = now
            # Format and promote into playbook
            declarative_text = enforce_declarative_memory_rule(text)
            await promote_lesson_to_playbook(f"### {cand.symbol.upper()}\n{declarative_text}")
            promoted_ids.append(cand.id)
            logger.info(f"Auto-promoted candidate lesson #{cand.id} for {cand.symbol} into playbook.")
        elif eval_count >= 5 and wr_delta <= -0.08:
            cand.status = 'rejected'
            cand.rejection_reason = f"negative_delta_{wr_delta:.2f}"
            logger.info(f"Rejected underperforming candidate lesson #{cand.id} for {cand.symbol}.")

    if promoted_ids:
        await safe_commit(session, label="auto_promote_candidate_lessons")

    return promoted_ids


async def record_playbook_rule_outcome(
    session,
    rule_text: str,
    symbol: str,
    was_profitable: bool,
    pnl: float = 0.0,
    min_eval_deprecate: int = 5,
    deprecation_win_rate: float = 0.40,
    golden_win_rate: float = 0.65,
) -> Any:
    """
    SOTA Phase 4: Closed-Loop Playbook Rule Attribution & Evolution.
    Tracks outcome per playbook rule, auto-deprecating consistently failing rules (<40% win rate)
    and marking high-performing rules (>=65% win rate) as 'golden'.
    """
    import hashlib
    from database.models import PlaybookRuleAttribution
    from database.safe_ops import safe_commit
    from sqlalchemy import select

    clean_text = rule_text.strip()
    rule_hash = hashlib.sha256(clean_text.encode('utf-8')).hexdigest()[:16]
    clean_sym = symbol.strip().upper()

    stmt = select(PlaybookRuleAttribution).where(
        PlaybookRuleAttribution.rule_hash == rule_hash,
        PlaybookRuleAttribution.symbol == clean_sym
    )
    attr = (await session.execute(stmt)).scalars().first()

    now = clock.now()
    if not attr:
        attr = PlaybookRuleAttribution(
            rule_hash=rule_hash,
            symbol=clean_sym,
            rule_text=clean_text,
            status='active',
            times_triggered=0,
            wins_count=0,
            losses_count=0,
            total_pnl=0.0,
            win_rate=0.0,
            promoted_at=now
        )
        session.add(attr)

    attr.times_triggered += 1
    if was_profitable:
        attr.wins_count += 1
    else:
        attr.losses_count += 1
    attr.total_pnl += float(pnl)
    attr.win_rate = float(attr.wins_count) / float(attr.times_triggered)
    attr.last_triggered_at = now

    # Check auto-deprecation and auto-promotion thresholds
    if attr.times_triggered >= min_eval_deprecate:
        if attr.win_rate < deprecation_win_rate and attr.status != 'deprecated':
            attr.status = 'deprecated'
            attr.deprecated_at = now
            attr.deprecation_reason = f"low_win_rate_{attr.win_rate:.2f}_after_{attr.times_triggered}_trades"
            logger.warning(f"Playbook rule [{rule_hash}] for {clean_sym} auto-deprecated: win rate {attr.win_rate:.2%}")
        elif attr.win_rate >= golden_win_rate and attr.status == 'active':
            attr.status = 'golden'
            logger.info(f"Playbook rule [{rule_hash}] for {clean_sym} elevated to golden: win rate {attr.win_rate:.2%}")

    await safe_commit(session, label="record_playbook_rule_outcome")
    return attr


