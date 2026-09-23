import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.prefetch.news_digest import NewsDigestProcessor
from database.models import NewsItem, NewsDigest
from datetime import datetime, timezone

class TestNewsDigestProcessor:

    def test_init(self):
        from config.settings import load_all_config
        settings = load_all_config()
        processor = NewsDigestProcessor(settings)
        assert processor._flash_lite is not None
        assert processor._flash is not None

    @pytest.mark.asyncio
    async def test_classify_unscored_news_empty(self):
        processor = NewsDigestProcessor({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        count = await processor.classify_unscored_news(mock_session)
        assert count == 0

    @pytest.mark.asyncio
    async def test_classify_unscored_news_success(self):
        processor = NewsDigestProcessor({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        
        item1 = NewsItem(id=1, title="USD Interest Rate Hike", summary="Fed raises rates", currency_tags="USD")
        item2 = NewsItem(id=2, title="EUR ECB Policy", summary="ECB keeps rates steady", currency_tags=None)
        def mock_execute_side_effect(*args, **kwargs):
            query_str = str(args[0])
            m_res = MagicMock()
            if "news_item" in query_str.lower():
                m_res.scalars().all.return_value = [item1, item2]
            else:
                m_res.scalars().all.return_value = []
            return m_res
            
        mock_session.execute = AsyncMock(side_effect=mock_execute_side_effect)
        
        processor._flash_lite.classify_json = AsyncMock(return_value=[
            {"index": 1, "impact": "HIGH", "confidence": 0.9, "surprise_magnitude": "large", "key_data_point": "4.2%", "currencies": ["EUR", "USD"], "sentiments": ["BEARISH_USD"]},
            {"index": 2, "impact": "LOW", "confidence": 0.8, "surprise_magnitude": "none", "key_data_point": "", "sentiments": ["NEUTRAL"]}
        ])
        
        count = await processor.classify_unscored_news(mock_session)
        
        assert count == 2
        assert item1.impact == "HIGH"
        assert "EUR" in item1.currency_tags
        assert "USD" in item1.currency_tags
        assert item1.sentiment == "BEARISH_USD,SURPRISE_LARGE"
        
        assert item2.impact == "LOW"
        assert item2.sentiment == "NEUTRAL"
        
        assert mock_session.commit.await_count >= 1

    @pytest.mark.asyncio
    async def test_create_news_digest_empty(self):
        processor = NewsDigestProcessor({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        # mock_result_empty is for get_latest_digest, high, medium, and fallback
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        digest = await processor.create_news_digest(mock_session)
        assert digest is None

    @pytest.mark.asyncio
    async def test_create_news_digest_success(self):
        processor = NewsDigestProcessor({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        item1 = NewsItem(id=1, source="source1", title="title 1", summary="sum 1", currency_tags="USD")
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars().all.return_value = [item1]
        
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        processor._flash.generate = AsyncMock(return_value="Broad Market Sentiment & Macro Drivers: This is a summary digest")
        processor._macro_synth.generate = AsyncMock(return_value="Broad Market Sentiment & Macro Drivers: This is a summary digest")
        processor._digest_generator.generate = AsyncMock(return_value="Broad Market Sentiment & Macro Drivers: This is a summary digest")
        processor._verifier.classify_json = AsyncMock(return_value={"has_contradictions": False, "contradictions": []})
    
        digest = await processor.create_news_digest(mock_session)
    
        assert digest is not None
        assert "Broad Market Sentiment & Macro Drivers" in digest
        assert "This is a summary digest" in digest
        mock_session.add.assert_called_once()
        args, _ = mock_session.add.call_args
        assert isinstance(args[0], NewsDigest)
        assert "This is a summary digest" in args[0].digest_text
        mock_session.commit.assert_awaited()

    def test_resolve_item_index_variations(self):
        from analysis.prefetch.news_digest import _resolve_item_index
        item1 = NewsItem(id=101, title="Item 1")
        item2 = NewsItem(id=102, title="Item 2")
        item3 = NewsItem(id=103, title="Item 3")
        batch = [item1, item2, item3]

        # 1. Match by news_id / id
        assert _resolve_item_index({"news_id": 102, "index": 99}, batch) == 1
        assert _resolve_item_index({"id": 103, "index": 99}, batch) == 2

        # 2. Standard 1-based indexing
        assert _resolve_item_index({"index": 1}, batch) == 0
        assert _resolve_item_index({"index": 3}, batch) == 2
        assert _resolve_item_index({"index": "2."}, batch) == 1
        assert _resolve_item_index({"index": "3)"}, batch) == 2

        # 3. 0-based indexing series
        all_results_zero_based = [{"index": 0}, {"index": 1}, {"index": 2}]
        assert _resolve_item_index({"index": 0}, batch, all_results_zero_based) == 0
        assert _resolve_item_index({"index": 1}, batch, all_results_zero_based) == 1
        assert _resolve_item_index({"index": 2}, batch, all_results_zero_based) == 2

        # 4. Out of bounds & invalid values
        assert _resolve_item_index({"index": 99}, batch) is None
        assert _resolve_item_index({"index": "invalid"}, batch) is None
        assert _resolve_item_index({}, batch) is None

    @pytest.mark.asyncio
    async def test_classify_unscored_news_zero_indexed_response(self):
        processor = NewsDigestProcessor({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        item1 = NewsItem(id=10, title="Federal Reserve Interest Rate Decision", summary="Fed policy update")
        item2 = NewsItem(id=20, title="ECB President Lagarde Speech on Inflation", summary="European central bank updates")

        def mock_execute_side_effect(*args, **kwargs):
            query_str = str(args[0])
            m_res = MagicMock()
            if "news_item" in query_str.lower():
                m_res.scalars().all.return_value = [item1, item2]
            else:
                m_res.scalars().all.return_value = []
            return m_res

        mock_session.execute = AsyncMock(side_effect=mock_execute_side_effect)

        # Model outputs 0-based indices [0, 1]
        processor._flash_lite.classify_json = AsyncMock(return_value=[
            {"index": 0, "impact": "HIGH", "confidence": 0.85, "surprise_magnitude": "none", "currencies": ["USD"], "sentiments": ["HAWKISH"], "key_data_point": ""},
            {"index": 1, "impact": "LOW", "confidence": 0.9, "surprise_magnitude": "none", "currencies": ["EUR"], "sentiments": ["NEUTRAL"], "key_data_point": ""}
        ])

        count = await processor.classify_unscored_news(mock_session)
        assert count == 2
        assert item1.impact == "HIGH"
        assert item2.impact == "LOW"

    @pytest.mark.asyncio
    async def test_classify_unscored_news_omitted_item_recovery(self):
        processor = NewsDigestProcessor({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()

        item1 = NewsItem(id=10, title="Federal Reserve Interest Rate Decision", summary="Fed policy update")
        item2 = NewsItem(id=20, title="Israel military strikes oil refinery in major escalation", summary="Explosions reported")

        called = False
        def mock_execute_side_effect(*args, **kwargs):
            nonlocal called
            query_str = str(args[0])
            m_res = MagicMock()
            if "news_item" in query_str.lower() and not called:
                called = True
                m_res.scalars().all.return_value = [item1, item2]
            else:
                m_res.scalars().all.return_value = []
            return m_res

        mock_session.execute = AsyncMock(side_effect=mock_execute_side_effect)

        # Model only returns item 1 (index 1), completely omitting item 2
        processor._flash_lite.classify_json = AsyncMock(side_effect=[
            [{"index": 1, "impact": "LOW", "confidence": 0.85, "surprise_magnitude": "none", "currencies": ["USD"], "sentiments": ["NEUTRAL"], "key_data_point": ""}],
            []  # micro retry also returns empty
        ])

        count = await processor.classify_unscored_news(mock_session)
        assert count == 2
        assert item1.impact == "LOW"
        # item 2 was shock news omitted by LLM; recovered via keyword fallback (not blindly set to MEDIUM)
        assert item2.impact in ("BREAKING", "HIGH")

    @pytest.mark.asyncio
    async def test_build_5day_macro_context_and_cache(self):
        processor = NewsDigestProcessor({})
        mock_session = AsyncMock()
        
        brief_mock = MagicMock()
        brief_mock.macro_regime = "stagflation"
        brief_mock.risk_sentiment = "risk_off"
        brief_mock.currency_bias = {"USD": "bearish", "EUR": "bullish"}
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = brief_mock
        mock_result.all.return_value = [
            ("Canada announces counter tariffs", "USD", "HIGH", datetime(2026, 8, 20, tzinfo=timezone.utc)),
            ("Middle East tension escalates", "OIL", "BREAKING", datetime(2026, 8, 21, tzinfo=timezone.utc))
        ]
        mock_session.execute = AsyncMock(return_value=mock_result)

        now_utc = datetime.now(timezone.utc)
        ctx1 = await processor._build_5day_macro_context(mock_session, now_utc)
        assert "5-DAY MACRO NARRATIVE" in ctx1
        assert "STAGFLATION" in ctx1
        assert "Canada announces counter tariffs" in ctx1

        # Check caching hit
        ctx2 = await processor._build_5day_macro_context(mock_session, now_utc)
        assert ctx1 == ctx2

        # Check explicit invalidation
        processor.invalidate_macro_context_cache()
        assert processor._macro_context_cache is None

    @pytest.mark.asyncio
    async def test_verify_high_medium_boundary_contradiction_guard(self):
        processor = NewsDigestProcessor({})
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        # Item 1: German economic breakdown (MEDIUM)
        item1 = NewsItem(id=1, title="Germany's Economic Model Is Broken", summary="Structural challenges in German industrial model", impact="MEDIUM")
        # Item 2: Routine data (HIGH)
        item2 = NewsItem(id=2, title="US Wholesale Inventories", summary="Routine inventory data", impact="HIGH")
        # Item 3: US CPI Surprise (MEDIUM)
        item3 = NewsItem(id=3, title="US CPI Surges to 4.5%", summary="Massive inflation surprise", impact="MEDIUM")

        news_items = [item1, item2, item3]

        # Model returns contradictory verdict for item 1 (HIGH with "keep medium" reason)
        # Model returns valid demotion for item 2
        # Model returns valid promotion for item 3
        processor._classification_verifier.classify_json = AsyncMock(return_value=[
            {"index": 1, "target_impact": "HIGH", "reason": "Germany economic breakdown analysis relevant to EUR but lacks immediate catalyst; keep MEDIUM"},
            {"index": 2, "target_impact": "MEDIUM", "reason": "Routine inventory data matching consensus without policy cues"},
            {"index": 3, "target_impact": "HIGH", "reason": "Tier-1 data surprise with direct Fed rate impact"}
        ])

        await processor._verify_high_medium_boundary(mock_session, news_items)

        # Item 1 should have been caught by contradiction guard and STAYED MEDIUM (not promoted to HIGH!)
        assert item1.impact == "MEDIUM"
        # Item 2 demoted to MEDIUM
        assert item2.impact == "MEDIUM"
        # Item 3 promoted to HIGH
        assert item3.impact == "HIGH"
        assert mock_session.commit.await_count >= 1

    def test_extract_numeric_claims(self):
        from analysis.prefetch.news_digest import _extract_numeric_claims
        text = (
            "Gold spot traded at $4,550 after reaching 4550.50 earlier. "
            "Fed probability increased by 50 bps (or 0.5% / 0.50), while EUR/USD was 1.08542. "
            "Macro score was +3.0 with AUD/USD at 0.6000. Volume reached 100k contracts ($1.5M). "
            "In 2026, 2-3 primary drivers moving across 5-day horizon."
        )
        claims = _extract_numeric_claims(text)
        assert "$4,550" in claims or "4,550" in claims
        assert "4550.50" in claims
        assert "50 bps" in claims
        assert "0.5%" in claims
        assert "1.08542" in claims
        assert "+3.0" in claims or "3.0" in claims
        assert "0.6000" in claims
        assert "100k" in claims
        assert "1.5M" in claims or "$1.5M" in claims

    def test_normalize_num_variants(self):
        from analysis.prefetch.news_digest import _normalize_num_variants
        # Percentages
        v_pct = _normalize_num_variants("50%")
        assert 50.0 in v_pct
        assert 0.5 in v_pct

        # Basis points
        v_bps = _normalize_num_variants("50 bps")
        assert 50.0 in v_bps
        assert 0.5 in v_bps
        assert 0.005 in v_bps

        # Thousands separator & currency
        v_curr = _normalize_num_variants("$4,550")
        assert 4550.0 in v_curr

        # Multipliers
        v_k = _normalize_num_variants("100k")
        assert 100000.0 in v_k
        v_m = _normalize_num_variants("1.5M")
        assert 1500000.0 in v_m

    def test_flag_ungrounded_numbers_no_false_positives(self):
        from analysis.prefetch.news_digest import _flag_ungrounded_numbers

        # Test Case 1: 4-digit number in source without comma (4550) vs LLM with comma ($4,550)
        source_news = "Gold touched 4550 intraday high amid safe-haven flows."
        section_text = "Current XAU Bias: Bullish. Gold holds support near $4,550 following safe-haven demand."
        ungrounded = _flag_ungrounded_numbers(section_text, source_news, extra_context_text="VIX: 18.5")
        assert ungrounded == []

        # Test Case 2: User scenario with 115, 0.9, 0.2, 0.6000, 0.5
        macro_source = "US Dollar Index DXY rose to 115.00. Fedwatch shows 90% probability of pause and 20% cut chance."
        macro_context = "Currency signals: AUD net score 0.6000. 50% consensus on rate path. 5-day theme across 2026."
        macro_text = (
            "MACRO OVERVIEW:\n"
            "DXY holds strong near 115 with 0.9 pause probability and 0.2 cut chance. "
            "AUD weighted score is 0.6000 with 0.5 probability alignment in 2-3 primary drivers."
        )
        ungrounded_macro = _flag_ungrounded_numbers(macro_text, macro_source, extra_context_text=macro_context)
        assert ungrounded_macro == []

    def test_format_news_item_for_prompt(self):
        from analysis.prefetch.news_digest import _format_news_item_for_prompt
        # Case 1: Standard news item with full summary and key data point
        item = NewsItem(
            id=1,
            title="Bitcoin ETF Inflows Surge",
            summary="Institutional investors added funds across major spot ETFs. Total inflows were significant.",
            key_data_point="+$450M",
            published_at=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
            impact="HIGH",
        )
        formatted = _format_news_item_for_prompt(item)
        assert "<untrusted_news_item impact='HIGH'>" in formatted
        assert "</untrusted_news_item>" in formatted
        assert "12:00 UTC" in formatted
        assert "Bitcoin ETF Inflows Surge" in formatted
        assert "(Data Point: +$450M)" in formatted
        assert "Total inflows were significant." in formatted

        # Case 2: Very long summary truncated cleanly at sentence boundary
        long_summary = "First sentence about monetary policy. " * 30 + "Final extra tail."
        item_long = NewsItem(
            id=2,
            title="Long Policy Analysis",
            summary=long_summary,
            published_at=datetime(2026, 8, 24, 14, 0, tzinfo=timezone.utc),
            impact="MEDIUM",
        )
        formatted_long = _format_news_item_for_prompt(item_long, max_summary_chars=300)
        assert "</untrusted_news_item>" in formatted_long
        assert len(formatted_long) < 450

    def test_flag_ungrounded_numbers_btc_jpy_macro_hallucinations(self):
        from analysis.prefetch.news_digest import _flag_ungrounded_numbers

        # BTC Hallucination scenario from user log
        btc_source = "Bitcoin ETF demand remained resilient with positive sentiment across crypto desks."
        btc_hallucinated = "Current BTC Bias: Bullish. ETF inflows reached $2B and $4B with cumulative $75.39B volume and $600M liquidations."
        btc_ungrounded = _flag_ungrounded_numbers(btc_hallucinated, btc_source)
        assert "$75.39B" in btc_ungrounded or "75.39B" in btc_ungrounded
        assert "$600M" in btc_ungrounded or "600M" in btc_ungrounded
        assert "$2B" in btc_ungrounded or "2B" in btc_ungrounded

        # JPY Hallucination scenario
        jpy_source = "Bank of Japan kept policy rates steady amid currency market monitoring."
        jpy_hallucinated = "Current JPY Bias: Bearish. MoF intervened with ¥1M (or ¥1T) in thin liquidity."
        jpy_ungrounded = _flag_ungrounded_numbers(jpy_hallucinated, jpy_source)
        assert any("1M" in u or "1T" in u for u in jpy_ungrounded)

        # Macro Grounded scenario (valid numbers in source should NOT be flagged)
        macro_source = "Treasury auction of $950B concluded as fiscal deficit reached $1T with $20B reserve buffer."
        macro_text = "Key Drivers: US debt management issued $950B in Treasuries, navigating $1T deficit and $20B buffers."
        macro_ungrounded = _flag_ungrounded_numbers(macro_text, macro_source)
        assert macro_ungrounded == []

    def test_normalize_num_variants_financial_words_and_abbreviations(self):
        from analysis.prefetch.news_digest import _normalize_num_variants

        # Millions variations
        for token in ["16 million", "16 millions", "16M", "16m", "16 mln", "16 mio", "16 mm"]:
            variants = _normalize_num_variants(token)
            assert 16000000.0 in variants, f"Failed for {token}"
            assert 16.0 in variants, f"Scaled variant failed for {token}"

        # Billions variations
        for token in ["$6.4 billion", "$6.4 billions", "$6.4B", "$6.4b", "$6.4 bn", "$6.4 bln"]:
            variants = _normalize_num_variants(token)
            assert 6400000000.0 in variants, f"Failed for {token}"
            assert 6.4 in variants, f"Scaled variant failed for {token}"

        # Trillions variations
        for token in ["$1 trillion", "$1 trillions", "$1T", "$1t", "$1 tn", "$1tn"]:
            variants = _normalize_num_variants(token)
            assert 1000000000000.0 in variants, f"Failed for {token}"
            assert 1.0 in variants, f"Scaled variant failed for {token}"

        # Thousands variations
        for token in ["100 thousand", "100 thousands", "100k", "100K"]:
            variants = _normalize_num_variants(token)
            assert 100000.0 in variants, f"Failed for {token}"

        # Rates, bps, percentages
        assert 50.0 in _normalize_num_variants("50 bps")
        assert 0.5 in _normalize_num_variants("50 bps")
        assert 0.005 in _normalize_num_variants("50 bps")
        assert 2.5 in _normalize_num_variants("2.5 percentage points")
        assert 0.025 in _normalize_num_variants("2.5%")

    def test_flag_ungrounded_numbers_live_payload_scenarios(self):
        from analysis.prefetch.news_digest import _flag_ungrounded_numbers

        # Skenario USD & XTI: 16 million barrels -> 16M
        src_usd = "@barakravid: Around 40 tankers transited. Around 16 million barrels of oil moved out of the strait on Friday night."
        sec_usd = "Current USD Bias: Bearish. Strait tanker traffic moved 16M barrels under heightened geopolitical friction."
        assert _flag_ungrounded_numbers(sec_usd, src_usd) == []

        # Skenario XAU & EUR: $6.4 billion & $1 trillion -> $6.4B & $1T
        src_xau = "Gold prices rose driven by U.S. Treasury's $6.4 billion buyback announcement. Bessent could tap near $1 trillion TGA."
        sec_xau = "Current XAU Bias: Bullish. Gold supported by $6.4B Treasury buybacks and prospective $1T TGA drawdown."
        assert _flag_ungrounded_numbers(sec_xau, src_xau) == []

        # Skenario BTC: 4 billion, 6.69 billion, 5.1 billion -> $4B, $6.69B, $5.1B
        src_btc = "Strategy disclosed $1.59 billion liquidity pool and $2.01 billion offering ($4 billion total). Weekly ETF flows hit 6.69 billion and 5.1 billion."
        sec_btc = "Current BTC Bias: Bullish. Backed by $4B corporate liquidity and massive $6.69B and $5.1B ETF inflow volume."
        assert _flag_ungrounded_numbers(sec_btc, src_btc) == []

        # Skenario Tenor & Historical: 10Y, 30Y, 1982, 1996
        src_hist = "Crude reserve fell to lowest since 1982. Japan yields reached 1996 highs. 10-year yield was 4.70% while 30-year held above 5%."
        sec_hist = "Nuances: SPR at 1982 lows, JPY borrowing at 1996 peaks. 10Y yield dropped to 4.70% while 30Y remained firm."
        assert _flag_ungrounded_numbers(sec_hist, src_hist) == []

        # Skenario Real Hallucination: Harus tetap di-flag
        sec_fake = "Current XAU Bias: Bullish. Gold target is $9,999/oz backed by $888B secret liquidity."
        ungrounded_fake = _flag_ungrounded_numbers(sec_fake, src_xau)
        assert "$9,999" in ungrounded_fake or "9,999" in ungrounded_fake
        assert "$888B" in ungrounded_fake or "888B" in ungrounded_fake

    def test_normalize_contradictions_various_keys(self):
        from analysis.prefetch.news_digest import _normalize_contradictions
        
        # Test 1: Empty or non-list
        assert _normalize_contradictions(None) == []
        assert _normalize_contradictions("invalid") == []
        assert _normalize_contradictions([]) == []

        # Test 2: Standard schema format
        std_input = [{
            "section_a": "Macro", "section_b": "USD",
            "claim_a": "USD Bullish", "claim_b": "USD Bearish",
            "severity": "material"
        }]
        res_std = _normalize_contradictions(std_input)
        assert len(res_std) == 1
        assert res_std[0]["claim_a"] == "USD Bullish"
        assert res_std[0]["claim_b"] == "USD Bearish"
        assert res_std[0]["severity"] == "material"

        # Test 3: Malformed keys (claim1, claimA, statement_a, section_1, etc.)
        malformed_input = [
            {"section_1": "Global", "section_2": "EUR", "claim_1": "Rate Cut", "claim_2": "Rate Hike", "severity": "material"},
            {"sectionA": "US", "sectionB": "JPY", "claimA": "Hawkish", "claimB": "Dovish", "severity": "HIGH"},
            {"section_a": "XAU", "claim_a": "Gold rally", "severity": "minor"}, # missing section_b & claim_b
            {"statement_a": "Oil surplus", "statement_b": "Oil deficit", "severity": "critical"}
        ]
        res_malformed = _normalize_contradictions(malformed_input)
        assert len(res_malformed) == 4
        assert res_malformed[0]["section_a"] == "Global"
        assert res_malformed[0]["claim_a"] == "Rate Cut"
        assert res_malformed[1]["claim_a"] == "Hawkish"
        assert res_malformed[1]["severity"] == "material"
        assert res_malformed[2]["claim_a"] == "Gold rally"
        assert res_malformed[2]["claim_b"] == "(unspecified claim)"
        assert res_malformed[3]["claim_a"] == "Oil surplus"
        assert res_malformed[3]["severity"] == "material"

    @pytest.mark.asyncio
    async def test_news_digest_consistency_and_reconcile_malformed_keys(self):
        from analysis.prefetch.news_digest import NewsDigestProcessor
        processor = NewsDigestProcessor({})

        # Mock verifier to return malformed key contradictions
        processor._verifier.classify_json = AsyncMock(return_value={
            "has_contradictions": True,
            "contradictions": [
                {"claim1": "DXY strengthening", "claim2": "USD bias bearish", "section1": "Macro", "section2": "USD", "severity": "material"},
                {"statement_a": "Minor nuance", "severity": "minor"}
            ]
        })
        # Mock macro synth reconciliation
        processor._macro_synth.generate = AsyncMock(return_value="Corrected digest text [RECONCILED: 1 material contradictions resolved]")

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        # Reconcile shouldn't raise KeyError: 'claim_a'
        reconciled = await processor._reconcile_digest_contradictions("Original digest text", [
            {"claim1": "DXY strengthening", "claim2": "USD bias bearish", "section1": "Macro", "section2": "USD", "severity": "material"}
        ])
        assert reconciled is not None
        assert "Corrected digest text" in reconciled

    @pytest.mark.asyncio
    async def test_build_currency_signals_summary_smoothing_and_edge_cases(self):
        processor = NewsDigestProcessor({})

        # 1. Empty news items
        res_empty = await processor._build_currency_signals_summary({}, ['USD', 'EUR'])
        assert '| USD | NEUTRAL | - | 0 | No significant news |' in res_empty
        assert '| EUR | NEUTRAL | - | 0 | No significant news |' in res_empty

        # 2. Single isolated HIGH item without BREAKING -> smoothed to MIXED/NEUTRAL
        single_high_item = NewsItem(id=1, title="EUR Retail Sales Inching Up", impact="HIGH", sentiment="BULLISH_EUR")
        res_single = await processor._build_currency_signals_summary({'EUR': [single_high_item]}, ['EUR'])
        assert '| EUR | MIXED/NEUTRAL | LOW | +2 |' in res_single

        # 3. Single BREAKING item -> directional signal respected
        single_breaking_item = NewsItem(id=2, title="ECB Emergency Rate Cut", impact="BREAKING", sentiment="BEARISH_EUR")
        res_breaking = await processor._build_currency_signals_summary({'EUR': [single_breaking_item]}, ['EUR'])
        assert '| EUR | BEARISH | MEDIUM | -3 |' in res_breaking

        # 4. Multi-item strong consensus -> BULLISH with HIGH confidence
        multi_strong = [
            NewsItem(id=10, title="US GDP Surges 3.5%", impact="HIGH", sentiment="BULLISH_USD"),
            NewsItem(id=11, title="Fed Hawkish Stance Reinforced", impact="HIGH", sentiment="BULLISH_USD"),
            NewsItem(id=12, title="US Jobs Report Beats Forecast", impact="HIGH", sentiment="BULLISH_USD"),
        ]
        res_strong = await processor._build_currency_signals_summary({'USD': multi_strong}, ['USD'])
        assert '| USD | BULLISH | HIGH | +6 |' in res_strong

        # 5. Mixed opposing items -> MIXED/NEUTRAL
        mixed_items = [
            NewsItem(id=20, title="GBP Inflation High", impact="HIGH", sentiment="BULLISH_GBP"),
            NewsItem(id=21, title="UK Recession Fears", impact="HIGH", sentiment="BEARISH_GBP"),
        ]
        res_mixed = await processor._build_currency_signals_summary({'GBP': mixed_items}, ['GBP'])
        assert '| GBP | MIXED/NEUTRAL | LOW | +0 |' in res_mixed

    @pytest.mark.asyncio
    async def test_create_news_digest_reconciliation_fallback_passive_note(self):
        processor = NewsDigestProcessor({})
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        item1 = NewsItem(id=1, source="rss", title="Fed rate path", summary="rates", impact="HIGH", currency_tags="USD", sentiment="BULLISH_USD", fetched_at=datetime.now(timezone.utc))

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars().all.return_value = [item1]
        mock_session.execute = AsyncMock(return_value=mock_result)

        processor._macro_synth.generate = AsyncMock(return_value="Macro overview text")
        processor._digest_generator.generate = AsyncMock(return_value="USD Nuance text")

        # Mock consistency check with material contradiction
        processor._verifier.classify_json = AsyncMock(return_value={
            "has_contradictions": True,
            "contradictions": [
                {"section_a": "Macro", "claim_a": "USD is Bullish", "section_b": "USD Nuances", "claim_b": "USD is Bearish", "severity": "material"}
            ]
        })

        # Mock reconciliation failure (returns None) -> should trigger passive note fallback
        with patch.object(processor, '_reconcile_digest_contradictions', AsyncMock(return_value=None)):
            digest = await processor.create_news_digest(mock_session)
            assert digest is not None
            assert "### CONSISTENCY CHECK (belum terselesaikan — perlakukan dengan hati-hati)" in digest
            assert "USD is Bullish  vs  [USD Nuances] USD is Bearish" in digest
