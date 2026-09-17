import pytest
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database.models import Base, DecisionReflection
from analysis.memory.session_search import SessionSearchEngine


@pytest.mark.asyncio
async def test_session_search_postgresql_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        # Seed test DecisionReflection records
        ref1 = DecisionReflection(
            analysis_id=101,
            symbol="EURUSD",
            decision="buy",
            confidence=0.75,
            confluence_score=8,
            rationale_summary="Bullish BOS at H4 1.0850 with unmitigated FVG",
            outcome_pnl_usd=1.45,
            exit_reason="tp_hit",
            created_at=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc)
        )
        ref2 = DecisionReflection(
            analysis_id=102,
            symbol="EURUSD",
            decision="buy",
            confidence=0.88,
            confluence_score=11,
            rationale_summary="Recent high-probability retest of demand zone",
            is_paper_whatif=True,
            whatif_reason="risk_gate",
            whatif_hypothetical_pnl_pips=25.0,
            created_at=datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
        )
        ref3 = DecisionReflection(
            analysis_id=103,
            symbol="XAUUSD",
            decision="sell",
            confidence=0.70,
            confluence_score=7,
            rationale_summary="Liquidity sweep at 2650 resistance",
            outcome_pnl_usd=-0.50,
            exit_reason="sl_hit",
            created_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        )
        session.add_all([ref1, ref2, ref3])
        await session.commit()

        search_engine = SessionSearchEngine()

        # 1. Test get_symbol_precedents: Recency-first (ref2 should come before ref1)
        precedents = await search_engine.get_symbol_precedents("EURUSD", limit=2, session=session)
        assert len(precedents) == 2
        assert precedents[0]["symbol"] == "EURUSD"
        assert precedents[0]["stage"] == "whatif"
        assert precedents[0]["confidence"] == 0.88
        assert precedents[0]["pnl"] == 2.50
        assert precedents[1]["stage"] == "execution"
        assert precedents[1]["pnl"] == 1.45

        # 2. Test keyword search
        search_res = await search_engine.search("FVG", limit=5, session=session)
        assert len(search_res) >= 1
        assert search_res[0]["symbol"] == "EURUSD"
        assert "FVG" in search_res[0]["content"]

        # 3. Test backward-compatibility no-ops
        search_engine.index_session("dummy_id", "EURUSD", "stage2", "test")
        assert search_engine.update_session_outcome("dummy_id", 1.0) is True

    await engine.dispose()


@pytest.mark.asyncio
async def test_session_search_dense_simd_and_rrf():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        # Test DecisionReflection with embeddings
        ref_a = DecisionReflection(
            analysis_id=201,
            symbol="EURUSD",
            decision="buy",
            confidence=0.85,
            confluence_score=9,
            rationale_summary="Breakout above resistance with bullish liquidity pool",
            embedding=[0.9, 0.1, 0.0],
            created_at=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
        )
        ref_b = DecisionReflection(
            analysis_id=202,
            symbol="EURUSD",
            decision="buy",
            confidence=0.70,
            confluence_score=6,
            rationale_summary="Choppy consolidation inside range",
            embedding=[0.0, 0.1, 0.9],
            created_at=datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
        )
        session.add_all([ref_a, ref_b])
        await session.commit()

        search_engine = SessionSearchEngine()

        # Check SIMD cosine similarity helper
        cos_high = search_engine.compute_cosine_similarity([1.0, 0.0, 0.0], [0.9, 0.1, 0.0])
        cos_low = search_engine.compute_cosine_similarity([1.0, 0.0, 0.0], [0.0, 0.1, 0.9])
        assert cos_high > cos_low

        # Test pgvector auto-detection (False in SQLite)
        has_pgv = await search_engine._detect_pgvector(session)
        assert has_pgv is False

        # Test hybrid precedent search with RRF and query_vector
        query_vec = [1.0, 0.0, 0.0]
        results = await search_engine.get_symbol_precedents_hybrid(
            "EURUSD",
            current_regime="trending_bullish",
            setup_text="breakout resistance liquidity",
            limit=2,
            session=session,
            query_vector=query_vec
        )
        assert len(results) == 2
        # ref_a matches query_vec strongly [0.9, 0.1, 0.0] vs [1.0, 0.0, 0.0]
        assert results[0]["session_id"] == str(ref_a.id)
        assert "rrf_score" in results[0]

    await engine.dispose()


@pytest.mark.asyncio
async def test_session_search_point_in_time_safety():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async with session_maker() as session:
        # Past record (Aug 15)
        ref_past = DecisionReflection(
            analysis_id=301,
            symbol="EURUSD",
            decision="buy",
            confidence=0.80,
            confluence_score=8,
            rationale_summary="Past breakout on EURUSD",
            created_at=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
        )
        # Future record (Sep 5)
        ref_future = DecisionReflection(
            analysis_id=302,
            symbol="EURUSD",
            decision="buy",
            confidence=0.95,
            confluence_score=10,
            rationale_summary="Future breakout on EURUSD",
            created_at=datetime(2026, 9, 5, 12, 0, tzinfo=timezone.utc)
        )
        session.add_all([ref_past, ref_future])
        await session.commit()

        search_engine = SessionSearchEngine()

        # Query as of Aug 20 -> should ONLY see ref_past, not ref_future
        as_of_cutoff = datetime(2026, 8, 20, 0, 0, tzinfo=timezone.utc)

        precedents = await search_engine.get_symbol_precedents(
            "EURUSD", limit=5, session=session, as_of=as_of_cutoff
        )
        assert len(precedents) == 1
        assert precedents[0]["session_id"] == str(ref_past.id)

        # Keyword search as of Aug 20
        search_res = await search_engine.search(
            "breakout", limit=5, session=session, as_of=as_of_cutoff
        )
        assert len(search_res) == 1
        assert search_res[0]["session_id"] == str(ref_past.id)

        # Hybrid search as of Aug 20
        hybrid_res = await search_engine.get_symbol_precedents_hybrid(
            "EURUSD", limit=5, session=session, as_of=as_of_cutoff
        )
        assert len(hybrid_res) == 1
        assert hybrid_res[0]["session_id"] == str(ref_past.id)

        # Query without as_of -> sees both
        all_prec = await search_engine.get_symbol_precedents("EURUSD", limit=5, session=session)
        assert len(all_prec) == 2

    await engine.dispose()
