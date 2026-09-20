"""
PostgreSQL Unified Historical Session and Precedent Search Engine.

Retrieves past cycle decisions, debate outcomes, and reflections directly from
PostgreSQL database (Single Source of Truth) without SQLite dual-write overhead.
"""

import logging
import math
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import select, desc, or_
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import DecisionReflection

logger = logging.getLogger("TradingAgent.SessionSearch")


class SessionSearchEngine:
    """Provides semantic, keyword, and recency-based precedent search directly against PostgreSQL."""

    def __init__(self, db_path: Optional[str] = None):
        # db_path kept for backward compatibility with existing constructors/tests
        self.db_path = db_path
        self._has_pgvector: Optional[bool] = None

    def _is_postgres_session(self, session: AsyncSession) -> bool:
        """Check if active session connects to a PostgreSQL backend."""
        from unittest.mock import Mock
        if isinstance(session, Mock):
            return False
        try:
            bind = session.get_bind() if hasattr(session, "get_bind") else getattr(session, "bind", None)
            dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
            return bool(dialect_name and "postgres" in dialect_name)
        except Exception:
            return False

    async def _detect_pgvector(self, session: AsyncSession) -> bool:
        """Auto-detect if PostgreSQL has the pgvector extension active."""
        if self._has_pgvector is not None:
            return self._has_pgvector
        from unittest.mock import Mock
        if isinstance(session, Mock):
            self._has_pgvector = False
            return False
        try:
            bind = session.get_bind() if hasattr(session, "get_bind") else getattr(session, "bind", None)
            dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
            if dialect_name and "postgres" not in dialect_name:
                self._has_pgvector = False
                return False
            from sqlalchemy import text
            res = await session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
            self._has_pgvector = (res.scalar() is not None)
        except Exception:
            self._has_pgvector = False
        return self._has_pgvector

    @staticmethod
    def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two dense vectors using NumPy SIMD."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        import numpy as np
        a = np.array(vec_a, dtype=np.float32)
        b = np.array(vec_b, dtype=np.float32)
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
        return float(np.dot(a, b) / denom)

    async def get_symbol_precedents(
        self,
        symbol: str,
        limit: int = 3,
        session: Optional[AsyncSession] = None,
        regime: Optional[str] = None,
        as_of: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves most recent decisive analysis sessions (real executions and what-ifs)
        directly from PostgreSQL decision_reflections table, prioritized by regime alignment when provided.
        Supports point-in-time safety via as_of parameter.
        """
        if not symbol or not symbol.strip():
            return []

        clean_sym = symbol.strip().upper()

        if session is not None:
            return await self._execute_symbol_precedents(session, clean_sym, limit, regime=regime, as_of=as_of)

        try:
            from database.db import get_session
            async with get_session() as s:
                return await self._execute_symbol_precedents(s, clean_sym, limit, regime=regime, as_of=as_of)
        except Exception as e:
            logger.warning(f"[PostgreSQL] get_symbol_precedents error for {clean_sym}: {e}")
            return []

    async def _execute_symbol_precedents(
        self,
        session: AsyncSession,
        clean_sym: str,
        limit: int,
        regime: Optional[str] = None,
        as_of: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        try:
            base_stmt = (
                select(DecisionReflection)
                .where(DecisionReflection.symbol == clean_sym)
                .where(DecisionReflection.decision.in_(["buy", "sell", "BUY", "SELL"]))
            )
            if as_of is not None:
                base_stmt = base_stmt.where(DecisionReflection.created_at <= as_of)
            rows = []
            if regime and str(regime).strip():
                raw_reg = str(regime).strip()
                if self._is_postgres_session(session):
                    from sqlalchemy import func
                    clean_terms = " & ".join(re.findall(r'\w+', raw_reg))
                    ts_filter = (
                        func.to_tsquery('english', clean_terms)
                        if clean_terms
                        else func.plainto_tsquery('english', raw_reg)
                    )
                    reg_stmt = base_stmt.where(
                        or_(
                            DecisionReflection.search_vector.op("@@")(ts_filter),
                            DecisionReflection.reflection_text.ilike(f"%{raw_reg.lower()}%"),
                        )
                    ).order_by(desc(DecisionReflection.created_at)).limit(limit)
                    try:
                        reg_rows = (await session.execute(reg_stmt)).scalars().all()
                        rows.extend(reg_rows)
                    except Exception as pg_fts_err:
                        logger.debug(f"[SessionSearch] FTS regime search fallback to ILIKE: {pg_fts_err}")
                if not rows:
                    tokens = [t.strip().lower() for t in raw_reg.replace("|", ",").replace(";", ",").split(",") if len(t.strip()) >= 3]
                    conditions = [
                        DecisionReflection.reflection_text.ilike(f"%{raw_reg.lower()}%"),
                        DecisionReflection.rationale_summary.ilike(f"%{raw_reg.lower()}%")
                    ]
                    for tok in tokens:
                        conditions.append(DecisionReflection.reflection_text.ilike(f"%{tok}%"))
                        conditions.append(DecisionReflection.rationale_summary.ilike(f"%{tok}%"))

                    reg_stmt = base_stmt.where(or_(*conditions)).order_by(desc(DecisionReflection.created_at)).limit(limit)
                    reg_rows = (await session.execute(reg_stmt)).scalars().all()
                    rows.extend(reg_rows)

            if len(rows) < limit:
                seen_ids = {r.id for r in rows}
                general_stmt = base_stmt.order_by(desc(DecisionReflection.created_at)).limit(limit * 2)
                gen_rows = (await session.execute(general_stmt)).scalars().all()
                for gr in gen_rows:
                    if gr.id not in seen_ids:
                        rows.append(gr)
                        seen_ids.add(gr.id)
                        if len(rows) >= limit:
                            break
            results: List[Dict[str, Any]] = []
            for r in rows:
                pnl_val = None
                if r.outcome_pnl_usd is not None:
                    pnl_val = float(r.outcome_pnl_usd)
                elif r.is_paper_whatif and r.whatif_hypothetical_pnl_pips is not None:
                    pnl_val = float(r.whatif_hypothetical_pnl_pips) / 10.0

                stage_val = "whatif" if r.is_paper_whatif else "execution"
                content_text = r.rationale_summary or f"Decision {r.decision} for {clean_sym}"
                if r.exit_reason:
                    content_text += f" | Outcome: {r.exit_reason}"
                if r.alpha_lesson or r.reflection_text:
                    ref_text = r.alpha_lesson or r.reflection_text or ""
                    content_text += f" | Reflection: {ref_text[:100]}"

                ts_str = r.created_at.isoformat() if r.created_at else datetime.now(timezone.utc).isoformat()
                results.append({
                    "session_id": str(r.id),
                    "symbol": r.symbol.upper(),
                    "timestamp": ts_str,
                    "stage": stage_val,
                    "decision": r.decision.upper(),
                    "confidence": float(r.confidence or 0.0),
                    "confluence_score": int(r.confluence_score or 0),
                    "content": content_text,
                    "pnl": pnl_val,
                })
            return results
        except Exception as e:
            logger.warning(f"[PostgreSQL] _execute_symbol_precedents query error: {e}")
            return []

    async def search(
        self,
        query: str,
        limit: int = 5,
        session: Optional[AsyncSession] = None,
        query_vector: Optional[List[float]] = None,
        as_of: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Searches past sessions matching query string directly in PostgreSQL with optional point-in-time safety."""
        if not query or not query.strip():
            return []

        clean_query = query.strip()

        if session is not None:
            return await self._execute_search(session, clean_query, limit, query_vector=query_vector, as_of=as_of)

        try:
            from database.db import get_session
            async with get_session() as s:
                return await self._execute_search(s, clean_query, limit, query_vector=query_vector, as_of=as_of)
        except Exception as e:
            logger.warning(f"[PostgreSQL] search error for '{query}': {e}")
            return []

    async def _execute_search(
        self,
        session: AsyncSession,
        query: str,
        limit: int,
        query_vector: Optional[List[float]] = None,
        as_of: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        try:
            if self._is_postgres_session(session):
                from sqlalchemy import func
                clean_terms = " & ".join(re.findall(r'\w+', query))
                ts_filter = (
                    func.to_tsquery('english', clean_terms)
                    if clean_terms
                    else func.plainto_tsquery('english', query)
                )
                stmt = (
                    select(DecisionReflection)
                    .where(
                        or_(
                            DecisionReflection.search_vector.op("@@")(ts_filter),
                            DecisionReflection.symbol == query.strip().upper(),
                        )
                    )
                )
            else:
                search_pattern = f"%{query}%"
                stmt = (
                    select(DecisionReflection)
                    .where(
                        or_(
                            DecisionReflection.symbol.ilike(search_pattern),
                            DecisionReflection.rationale_summary.ilike(search_pattern),
                            DecisionReflection.reflection_text.ilike(search_pattern),
                            DecisionReflection.alpha_lesson.ilike(search_pattern),
                        )
                    )
                )
            if as_of is not None:
                stmt = stmt.where(DecisionReflection.created_at <= as_of)
            stmt = stmt.order_by(desc(DecisionReflection.created_at)).limit(limit * 2)
            sparse_rows = (await session.execute(stmt)).scalars().all()

            # If no query_vector provided, attempt auto-vectorization via Gemini Embedding
            if not query_vector:
                try:
                    from utils.llm.embedding import generate_gemini_embedding
                    query_vector = await generate_gemini_embedding(query)
                except Exception:
                    query_vector = None

            # If still no query_vector, return sparse rows formatted
            if not query_vector:
                return [self._format_reflection(r) for r in sparse_rows[:limit]]

            # Dense Vector Search: Dual-Engine (pgvector <=> or NumPy SIMD Cosine)
            dense_rows = []
            has_pgv = await self._detect_pgvector(session)
            if has_pgv:
                try:
                    from sqlalchemy import text
                    vec_literal = "[" + ",".join(str(float(x)) for x in query_vector) + "]"
                    pgv_stmt = (
                        select(DecisionReflection)
                        .where(DecisionReflection.embedding.isnot(None))
                    )
                    if as_of is not None:
                        pgv_stmt = pgv_stmt.where(DecisionReflection.created_at <= as_of)
                    pgv_stmt = (
                        pgv_stmt
                        .order_by(text(f"embedding <=> '{vec_literal}'"))
                        .limit(limit * 2)
                    )
                    dense_rows = list((await session.execute(pgv_stmt)).scalars().all())
                except Exception as pgv_err:
                    logger.debug(f"[pgvector] <=> operator query error, falling back to NumPy SIMD: {pgv_err}")
                    dense_rows = []

            if not dense_rows:
                dense_stmt = select(DecisionReflection).where(DecisionReflection.embedding.isnot(None))
                if as_of is not None:
                    dense_stmt = dense_stmt.where(DecisionReflection.created_at <= as_of)
                all_embedded = (await session.execute(dense_stmt)).scalars().all()

                if all_embedded:
                    import numpy as np
                    q_vec = np.array(query_vector, dtype=np.float32)
                    q_norm = np.linalg.norm(q_vec) + 1e-9

                    doc_vecs = []
                    valid_docs = []
                    for doc in all_embedded:
                        if doc.embedding and isinstance(doc.embedding, (list, tuple)):
                            doc_vecs.append(doc.embedding)
                            valid_docs.append(doc)

                    if doc_vecs:
                        d_mat = np.array(doc_vecs, dtype=np.float32)
                        d_norms = np.linalg.norm(d_mat, axis=1) + 1e-9
                        sims = np.dot(d_mat, q_vec) / (d_norms * q_norm)
                        top_idx = np.argsort(-sims)[:limit * 2]
                        dense_rows = [valid_docs[i] for i in top_idx]

            # Reciprocal Rank Fusion (RRF, k=60)
            rrf_scores: Dict[int, float] = {}
            row_map: Dict[int, DecisionReflection] = {}
            k = 60

            for rank, r in enumerate(sparse_rows):
                rrf_scores[r.id] = rrf_scores.get(r.id, 0.0) + (1.0 / (k + rank + 1))
                row_map[r.id] = r

            for rank, r in enumerate(dense_rows):
                rrf_scores[r.id] = rrf_scores.get(r.id, 0.0) + (1.0 / (k + rank + 1))
                row_map[r.id] = r

            ranked_ids = sorted(rrf_scores.keys(), key=lambda rid: rrf_scores[rid], reverse=True)[:limit]
            return [self._format_reflection(row_map[rid]) for rid in ranked_ids]

        except Exception as e:
            logger.warning(f"[PostgreSQL] _execute_search error: {e}")
            return []

    def _format_reflection(self, r: DecisionReflection) -> Dict[str, Any]:
        pnl_val = None
        if r.outcome_pnl_usd is not None:
            pnl_val = float(r.outcome_pnl_usd)
        elif r.is_paper_whatif and r.whatif_hypothetical_pnl_pips is not None:
            pnl_val = float(r.whatif_hypothetical_pnl_pips) / 10.0

        stage_val = "whatif" if r.is_paper_whatif else "execution"
        content_text = r.rationale_summary or f"Decision {r.decision} for {r.symbol}"
        if r.exit_reason:
            content_text += f" | Outcome: {r.exit_reason}"
        if r.alpha_lesson or r.reflection_text:
            ref_text = r.alpha_lesson or r.reflection_text or ""
            content_text += f" | Reflection: {ref_text[:120]}"

        ts_str = r.created_at.isoformat() if r.created_at else datetime.now(timezone.utc).isoformat()
        return {
            "session_id": str(r.id),
            "symbol": r.symbol.upper(),
            "timestamp": ts_str,
            "stage": stage_val,
            "decision": r.decision.upper(),
            "confidence": float(r.confidence or 0.0),
            "confluence_score": int(r.confluence_score or 0),
            "content": content_text,
            "pnl": pnl_val,
        }

    async def hybrid_search(
        self,
        query: str,
        symbol: Optional[str] = None,
        query_vector: Optional[List[float]] = None,
        limit: int = 5,
        session: Optional[AsyncSession] = None,
        as_of: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Executes hybrid semantic search combining BM25 keyword matching and
        dense vector cosine similarity via Reciprocal Rank Fusion.
        Supports point-in-time anti-lookahead protection via as_of.
        """
        q = query
        if symbol:
            q = f"{symbol} {query}".strip()
        return await self.search(q, limit=limit, session=session, query_vector=query_vector, as_of=as_of)

    def index_session(self, *args, **kwargs):
        """No-op kept for backwards compatibility. Delegates to index_reflection if AsyncSession is provided."""
        if args and hasattr(args[0], "get_bind"):
            return self.index_reflection(*args, **kwargs)
        return True

    def update_session_outcome(self, *args, **kwargs) -> bool:
        """No-op kept for backwards compatibility. Delegates to update_reflection_outcome if AsyncSession is provided."""
        if args and hasattr(args[0], "get_bind"):
            return self.update_reflection_outcome(*args, **kwargs)
        return True

    def compute_precedent_hybrid_score(
        self,
        reflection: DecisionReflection,
        current_regime: Optional[str] = None,
        setup_tokens: Optional[set[str]] = None,
        now: Optional[datetime] = None
    ) -> Dict[str, float]:
        """
        SOTA Phase 4: Hybrid Multi-Factor Precedent Scoring.
        Formula: 0.40 * regime + 0.30 * keyword + 0.20 * outcome + 0.10 * recency
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # 1. Regime Score (0.40 weight)
        regime_score = 0.10
        if current_regime and str(current_regime).strip():
            c_reg = str(current_regime).lower()
            text_corpus = f"{reflection.reflection_text or ''} {reflection.rationale_summary or ''}".lower()
            if c_reg in text_corpus:
                regime_score = 1.0
            else:
                toks = [t.strip() for t in c_reg.replace('|', ',').split(',') if len(t.strip()) >= 3]
                if toks and any(t in text_corpus for t in toks):
                    regime_score = 0.50

        # 2. Keyword Relevance Score (0.30 weight)
        keyword_score = 0.10
        if setup_tokens:
            doc_text = f"{reflection.symbol} {reflection.decision} {reflection.rationale_summary or ''} {reflection.alpha_lesson or ''}".lower()
            doc_tokens = set(re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', doc_text))
            if doc_tokens and setup_tokens:
                overlap = len(setup_tokens & doc_tokens)
                keyword_score = min(1.0, float(overlap) / max(1.0, len(setup_tokens)))

        # 3. Outcome Quality Score (0.20 weight)
        outcome_score = 0.30
        if reflection.was_profitable is True or (reflection.outcome_pnl_usd is not None and reflection.outcome_pnl_usd > 0):
            outcome_score = 1.0
        elif reflection.was_profitable is False or (reflection.outcome_pnl_usd is not None and reflection.outcome_pnl_usd < 0):
            outcome_score = 0.10
        elif reflection.process_was_sound:
            outcome_score = 0.70

        # 4. Recency Score (0.10 weight with exponential decay)
        recency_score = 0.50
        if reflection.created_at:
            ref_dt = reflection.created_at
            if ref_dt.tzinfo is None:
                ref_dt = ref_dt.replace(tzinfo=timezone.utc)
            days_ago = max(0.0, (now - ref_dt).total_seconds() / 86400.0)
            recency_score = math.exp(-days_ago / 30.0)  # Halves every ~21 days

        composite = (
            0.40 * regime_score +
            0.30 * keyword_score +
            0.20 * outcome_score +
            0.10 * recency_score
        )

        return {
            "composite": round(composite, 4),
            "regime_score": round(regime_score, 4),
            "keyword_score": round(keyword_score, 4),
            "outcome_score": round(outcome_score, 4),
            "recency_score": round(recency_score, 4)
        }

    async def get_symbol_precedents_hybrid(
        self,
        symbol: str,
        current_regime: Optional[str] = None,
        setup_text: Optional[str] = None,
        limit: int = 3,
        session: Optional[AsyncSession] = None,
        query_vector: Optional[List[float]] = None,
        as_of: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        SOTA Phase 4 & Phase 2: Retrieves and re-ranks symbol precedents using multi-factor
        hybrid scoring combined with dense vector cosine similarity via Reciprocal Rank Fusion (RRF):
        0.40 * Regime + 0.30 * Keyword + 0.20 * Outcome + 0.10 * Recency + Dense Vector RRF.
        Supports point-in-time safety via as_of parameter.
        """
        if not symbol or not symbol.strip():
            return []

        clean_sym = symbol.strip().upper()

        if session is not None:
            return await self._execute_symbol_precedents_hybrid(
                session, clean_sym, current_regime=current_regime, setup_text=setup_text, limit=limit, query_vector=query_vector, as_of=as_of
            )

        try:
            from database.db import get_session
            async with get_session() as s:
                return await self._execute_symbol_precedents_hybrid(
                    s, clean_sym, current_regime=current_regime, setup_text=setup_text, limit=limit, query_vector=query_vector, as_of=as_of
                )
        except Exception as e:
            logger.warning(f"[PostgreSQL] get_symbol_precedents_hybrid error for {clean_sym}: {e}")
            return []

    async def _execute_symbol_precedents_hybrid(
        self,
        session: AsyncSession,
        clean_sym: str,
        current_regime: Optional[str] = None,
        setup_text: Optional[str] = None,
        limit: int = 3,
        query_vector: Optional[List[float]] = None,
        as_of: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        try:
            stmt = (
                select(DecisionReflection)
                .where(DecisionReflection.symbol == clean_sym)
                .where(DecisionReflection.decision.in_(["buy", "sell", "BUY", "SELL"]))
            )
            if as_of is not None:
                stmt = stmt.where(DecisionReflection.created_at <= as_of)
            stmt = stmt.order_by(desc(DecisionReflection.created_at)).limit(30)
            candidates = list((await session.execute(stmt)).scalars().all())
            if not candidates:
                return []

            setup_tokens = None
            if setup_text and setup_text.strip():
                raw_words = re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', setup_text.lower())
                stopwords = {"the", "and", "for", "with", "this", "that", "trade", "price", "entry"}
                setup_tokens = {w for w in raw_words if w not in stopwords}

            now = as_of if as_of is not None else datetime.now(timezone.utc)
            if now.tzinfo is None:
                now = now.replace(tzinfo=timezone.utc)
            
            # 1. Multi-factor heuristic scoring
            heuristic_ranks = []
            for r in candidates:
                scores = self.compute_precedent_hybrid_score(
                    reflection=r,
                    current_regime=current_regime,
                    setup_tokens=setup_tokens,
                    now=now
                )
                heuristic_ranks.append((r, scores))
            heuristic_ranks.sort(key=lambda item: item[1]["composite"], reverse=True)

            # 2. Dense vector ranking if query_vector provided
            dense_ranks = []
            if query_vector:
                has_pgv = await self._detect_pgvector(session)
                if has_pgv:
                    try:
                        from sqlalchemy import text
                        vec_str = "[" + ",".join(str(float(x)) for x in query_vector) + "]"
                        pgv_cand_stmt = (
                            select(DecisionReflection)
                            .where(DecisionReflection.symbol == clean_sym)
                            .where(DecisionReflection.embedding.isnot(None))
                            .order_by(text(f"embedding <=> '{vec_str}'"))
                            .limit(30)
                        )
                        dense_ranks = list((await session.execute(pgv_cand_stmt)).scalars().all())
                    except Exception as pgv_err:
                        logger.debug(f"pgvector hybrid search error: {pgv_err}")
                        dense_ranks = []

                if not dense_ranks:
                    # Fallback to in-memory SIMD cosine similarity
                    dense_with_sim = []
                    for r in candidates:
                        if r.embedding and isinstance(r.embedding, (list, tuple)):
                            sim = self.compute_cosine_similarity(query_vector, r.embedding)
                            dense_with_sim.append((r, sim))
                    dense_with_sim.sort(key=lambda x: x[1], reverse=True)
                    dense_ranks = [item[0] for item in dense_with_sim]

            # 3. Reciprocal Rank Fusion (RRF, k=60)
            if query_vector and dense_ranks:
                k = 60
                rrf_scores: Dict[int, float] = {}
                row_map: Dict[int, DecisionReflection] = {r.id: r for r in candidates}
                for r in dense_ranks:
                    row_map[r.id] = r
                for rank, (r, _) in enumerate(heuristic_ranks):
                    rrf_scores[r.id] = rrf_scores.get(r.id, 0.0) + (1.0 / (k + rank + 1))
                for rank, r in enumerate(dense_ranks):
                    rrf_scores[r.id] = rrf_scores.get(r.id, 0.0) + (1.0 / (k + rank + 1))

                ranked_ids = sorted(rrf_scores.keys(), key=lambda rid: rrf_scores[rid], reverse=True)
                scored = []
                for rid in ranked_ids:
                    r = row_map[rid]
                    h_score = next((sc for cand, sc in heuristic_ranks if cand.id == rid), None)
                    if not h_score:
                        h_score = self.compute_precedent_hybrid_score(r, current_regime=current_regime, setup_tokens=setup_tokens, now=now)
                    formatted = self._format_reflection(r)
                    formatted["hybrid_scores"] = h_score
                    formatted["composite_score"] = h_score["composite"]
                    formatted["rrf_score"] = round(rrf_scores[rid], 6)
                    scored.append(formatted)
                return scored[:limit]

            # If no dense vector ranking needed, return pure multi-factor ranked
            scored = []
            for r, scores in heuristic_ranks:
                formatted = self._format_reflection(r)
                formatted["hybrid_scores"] = scores
                formatted["composite_score"] = scores["composite"]
                scored.append(formatted)

            return scored[:limit]
        except Exception as e:
            logger.warning(f"[PostgreSQL] _execute_symbol_precedents_hybrid error: {e}")
            return []

    async def index_reflection(
        self,
        session: AsyncSession,
        reflection_id: int,
        custom_text: Optional[str] = None
    ) -> bool:
        """
        Indexes or re-indexes a DecisionReflection record for PostgreSQL Full-Text Search.
        Computes search_vector from reflection text, rationale, lessons, and metadata.
        """
        try:
            r = await session.get(DecisionReflection, reflection_id)
            if not r:
                return False

            parts = [
                r.symbol or "",
                r.decision or "",
                r.rationale_summary or "",
                r.exit_reason or "",
                r.reflection_text or "",
                r.alpha_lesson or "",
                r.specific_lesson or "",
                custom_text or ""
            ]
            combined_text = " ".join(filter(None, parts)).strip()

            if self._is_postgres_session(session):
                from sqlalchemy import func
                r.search_vector = func.to_tsvector('english', combined_text)
            else:
                r.search_vector = combined_text

            await session.commit()
            return True
        except Exception as e:
            logger.warning(f"[SessionSearch] index_reflection error for reflection {reflection_id}: {e}")
            await session.rollback()
            return False

    async def update_reflection_outcome(
        self,
        session: AsyncSession,
        reflection_id: int,
        outcome_data: Dict[str, Any]
    ) -> bool:
        """
        Updates trade reflection outcome and re-indexes the search vector.
        """
        try:
            r = await session.get(DecisionReflection, reflection_id)
            if not r:
                return False

            if "outcome_pnl_usd" in outcome_data:
                r.outcome_pnl_usd = float(outcome_data["outcome_pnl_usd"])
            if "exit_reason" in outcome_data:
                r.exit_reason = str(outcome_data["exit_reason"])
            if "was_profitable" in outcome_data:
                r.was_profitable = bool(outcome_data["was_profitable"])
            if "reflection_text" in outcome_data:
                r.reflection_text = str(outcome_data["reflection_text"])
            if "alpha_lesson" in outcome_data:
                r.alpha_lesson = str(outcome_data["alpha_lesson"])
            if "status" in outcome_data:
                r.status = str(outcome_data["status"])
            if "resolved_at" in outcome_data:
                r.resolved_at = outcome_data["resolved_at"]
            else:
                r.resolved_at = datetime.now(timezone.utc)

            await session.commit()
            return await self.index_reflection(session, reflection_id)
        except Exception as e:
            logger.warning(f"[SessionSearch] update_reflection_outcome error for reflection {reflection_id}: {e}")
            await session.rollback()
            return False


