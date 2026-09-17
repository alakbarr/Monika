"""
Comprehensive Empirical Stress-Test Suite for `_classify_query_complexity` in `chat_agent.py`.
Executed by: m3_challenger_1

Test Categories:
1. Exact text from `D:\\Monika\\contoh_pertanyaan.md` (benchmark query variants).
2. Diverse macro event queries (short, long, mixed languages, greetings + macro).
3. Empirical vulnerability / blind-spot investigations (Fed without 'the', R1.2 historical precedents, asymmetric intent).
4. Non-macro complex queries, simple commands, action verbs.
5. Boundary inputs (empty string, whitespace, unusual chars, non-string, injection payloads, super long payloads).
"""

import os
import pytest
from unittest.mock import AsyncMock, patch
from telegram_bot.chat_agent import ChatAgent


@pytest.fixture
def agent():
    with patch("telegram_bot.chat_agent.get_client_for_task") as mock_get_client:
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client
        return ChatAgent({}, 12345)


# ==============================================================================
# Suite 1: Exact text from `contoh_pertanyaan.md`
# ==============================================================================

class TestContohPertanyaanBenchmark:
    """Empirical verification of exact query text from `contoh_pertanyaan.md`."""

    @pytest.mark.asyncio
    async def test_full_contoh_pertanyaan_file(self, agent):
        """Full text of contoh_pertanyaan.md must route to deep_research."""
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
        benchmark_file = os.path.join(repo_root, "contoh_pertanyaan.md")
        assert os.path.exists(benchmark_file), f"Benchmark file missing at {benchmark_file}"

        with open(benchmark_file, "r", encoding="utf-8") as f:
            content = f.read()

        assert agent._is_macro_event_query(content) is True
        res = await agent._classify_query_complexity(content)
        assert res == "deep_research"

    @pytest.mark.asyncio
    async def test_exact_chat_prompt_block(self, agent):
        """Exact prompt block lines 3-11 from contoh_pertanyaan.md must route to deep_research."""
        exact_prompt = (
            "Analisis peluang kemungkinan keputusan suku bunga The Fed 16/17 September 2016 yang akan diumumkan dalam beberapajam ke depan.\n\n"
            "Di CME Fedwatch proyeksinya 89% The Fed akan menaikkan suku bunga (HIKE), sedangkan sisanya adalah HOLD.\n\n"
            "Tapi apakah ini (HIKE) sudah pasti akan dilakukan oleh The Fed? Apakah ada history The Fed tidak searah dengan harapan pasar? "
            "Jika ada, apa yang menyebabkan itu? Kenapa bisa pasar salah mengartikan arah kebijakan The Fed atau justru The Fed yang memang sengaja tidak mengikuti arah keinginan pasar/sengaja mengecoh pasar? Apakah mungkin terjadi lagi saat ini?\n\n"
            "Kemudian setelah pengumuman suku bunga, apa yang kira-kira akan dinyatakan oleh Kevin Warsh saat press conference? apakah akan lebih condong ke hawkish atau dovish? mana yang lebih mungkin terjadi?\n\n"
            "Kumpulkan semua data yang kamu butuhkan. Lakukan analisis secara komprehensif."
        )
        assert agent._is_macro_event_query(exact_prompt) is True
        res = await agent._classify_query_complexity(exact_prompt)
        assert res == "deep_research"

    @pytest.mark.asyncio
    async def test_prompt_block_with_markdown_fences(self, agent):
        """Prompt enclosed in markdown fences as shown in contoh_pertanyaan.md."""
        fenced_prompt = (
            "Pertanyaan Chat:\n```\n"
            "Analisis peluang kemungkinan keputusan suku bunga The Fed 16/17 September 2016 yang akan diumumkan dalam beberapajam ke depan.\n"
            "Di CME Fedwatch proyeksinya 89% The Fed akan menaikkan suku bunga (HIKE), sedangkan sisanya adalah HOLD.\n"
            "Tapi apakah ini (HIKE) sudah pasti akan dilakukan oleh The Fed? Apakah ada history The Fed tidak searah dengan harapan pasar?\n"
            "Kemudian setelah pengumuman suku bunga, apa yang kira-kira akan dinyatakan oleh Kevin Warsh saat press conference?\n"
            "```"
        )
        assert agent._is_macro_event_query(fenced_prompt) is True
        res = await agent._classify_query_complexity(fenced_prompt)
        assert res == "deep_research"

    @pytest.mark.asyncio
    async def test_benchmark_individual_paragraphs(self, agent):
        """Each analytical paragraph of the benchmark query should individually route to deep_research."""
        p1 = "Analisis peluang kemungkinan keputusan suku bunga The Fed 16/17 September 2016 yang akan diumumkan dalam beberapajam ke depan."
        assert agent._is_macro_event_query(p1) is True
        assert await agent._classify_query_complexity(p1) == "deep_research"

        p2 = "Di CME Fedwatch proyeksinya 89% The Fed akan menaikkan suku bunga (HIKE), sedangkan sisanya adalah HOLD."
        assert agent._is_macro_event_query(p2) is True
        assert await agent._classify_query_complexity(p2) == "deep_research"

        p3 = "Tapi apakah ini (HIKE) sudah pasti akan dilakukan oleh The Fed? Apakah ada history The Fed tidak searah dengan harapan pasar? Kenapa bisa pasar salah mengartikan arah kebijakan The Fed atau justru The Fed sengaja mengecoh pasar?"
        assert agent._is_macro_event_query(p3) is True
        assert await agent._classify_query_complexity(p3) == "deep_research"

        p4 = "Kemudian setelah pengumuman suku bunga, apa yang kira-kira akan dinyatakan oleh Kevin Warsh saat press conference? apakah akan lebih condong ke hawkish atau dovish?"
        assert agent._is_macro_event_query(p4) is True
        assert await agent._classify_query_complexity(p4) == "deep_research"


# ==============================================================================
# Suite 2: Diverse Macro Event Queries (Supported)
# ==============================================================================

class TestDiverseMacroEventQueriesSupported:
    """Testing diverse macro event queries across languages, lengths, and nuances that are properly supported."""

    @pytest.mark.asyncio
    async def test_short_macro_queries_supported(self, agent):
        """Short, concise macro event queries."""
        short_queries = [
            "Peluang rate hike FOMC?",
            "CME FedWatch probability update",
            "Press conference Powell dovish or hawkish?",
            "Prediksi suku bunga BI besok",
            "Dot plot SEP forecast FOMC",
            "Peluang rate cut ECB vs BOE",
            "Skenario Ueda BOJ rate hike",
            "Prospek kebijakan moneter central bank",
            "Peluang Fed rate cut",
            "Analisis keputusan suku bunga ECB",
            "analisis keputusan suku bunga the fed",
            "prospek keputusan suku bunga the fed",
        ]
        for q in short_queries:
            is_macro = agent._is_macro_event_query(q)
            res = await agent._classify_query_complexity(q)
            assert is_macro is True, f"Failed _is_macro_event_query for: '{q}'"
            assert res == "deep_research", f"Failed _classify_query_complexity for: '{q}', got '{res}'"

    @pytest.mark.asyncio
    async def test_long_macro_queries(self, agent):
        """Long, detailed multi-sentence macro event queries (>300 chars)."""
        long_query_1 = (
            "Tolong berikan evaluasi mendalam terkait kebijakan moneter The Fed menjelang pengumuman suku bunga malam ini. "
            "Bagaimana pergeseran dot plot SEP diproyeksikan dan apakah probabilitas di CME FedWatch sudah mencerminkan kondisi "
            "priced-in sepenuhnya atau masih terbuka peluang kejutan pasar? Jelaskan skenario hawkish hold vs dovish cut serta "
            "dampaknya terhadap pergerakan yield obligasi US10Y dan indeks dollar DXY pasca press conference Jerome Powell."
        )
        assert len(long_query_1) > 300
        assert agent._is_macro_event_query(long_query_1) is True
        assert await agent._classify_query_complexity(long_query_1) == "deep_research"

        long_query_2 = (
            "Analyze the comprehensive macro outlook for the upcoming FOMC rate decision. Taking into account recent sticky "
            "PCE inflation prints and resilient non-farm payrolls, how do you assess the odds of an interest rate hike versus "
            "a hold? Deconstruct the expected forward guidance from Kevin Warsh during the press conference and outline a "
            "three-scenario reaction framework for gold (XAUUSD) and Treasury yields."
        )
        assert len(long_query_2) > 300
        assert agent._is_macro_event_query(long_query_2) is True
        assert await agent._classify_query_complexity(long_query_2) == "deep_research"

    @pytest.mark.asyncio
    async def test_mixed_language_macro_queries(self, agent):
        """Mixed English-Indonesian queries."""
        mixed_queries = [
            "Tolong preview FOMC meeting malam ini, apakah ada chance The Fed rate hike mengecoh market consensus dan bagaimana implikasi dot plot?",
            "Bagaimana outlook kebijakan moneter Jerome Powell di press conference nanti, hawkish atau dovish?",
            "Cek CME FedWatch odds dan berikan analisis probabilitas monetary policy ECB pasca rilis inflasi",
            "Apakah ada preseden historis central bank market surprise yang relevan dengan setup The Fed saat ini?",
        ]
        for q in mixed_queries:
            assert agent._is_macro_event_query(q) is True, f"Failed macro detection: {q}"
            assert await agent._classify_query_complexity(q) == "deep_research", f"Failed routing: {q}"

    @pytest.mark.asyncio
    async def test_greetings_with_macro_queries(self, agent):
        """Greetings prepended to macro queries must still trigger deep_research."""
        queries = [
            "Halo Monika, tolong analisis probabilitas suku bunga The Fed malam ini",
            "Hi! What is the CME FedWatch rate hike probability?",
            "Selamat pagi, bisakah analisa outlook kebijakan moneter Jerome Powell di press conference nanti?",
            "Hey, ada peluang rate cut di FOMC nanti malam?",
        ]
        for q in queries:
            assert agent._is_macro_event_query(q) is True, f"Failed macro detection: {q}"
            assert await agent._classify_query_complexity(q) == "deep_research", f"Failed routing: {q}"

    @pytest.mark.asyncio
    async def test_case_insensitivity_and_spacing(self, agent):
        """Case insensitivity and spacing variations."""
        variations = [
            "fOmC rAtE hIkE pRoBaBiLiTy",
            "THE FED SUKU BUNGA PROBABILITAS",
            "cme    fedwatch    hike   vs   hold",
            "   analisis   peluang   keputusan   suku   bunga   the   fed   ",
        ]
        for q in variations:
            assert agent._is_macro_event_query(q) is True, f"Failed: {q}"
            assert await agent._classify_query_complexity(q) == "deep_research", f"Failed: {q}"


# ==============================================================================
# Suite 3: Empirical Vulnerability / Blind-Spot Investigations
# ==============================================================================

class TestMacroRoutingVulnerabilities:
    """
    EMPIRICAL CHALLENGER FINDINGS:
    Documenting blind-spots and classification failures in `_classify_query_complexity`
    and `_is_macro_event_query`.
    """

    @pytest.mark.asyncio
    async def test_vulnerability_fed_without_the(self, agent):
        r"""
        Remedy 1: '(?:the\s+)?fed\b' and 'fed\s*(?:hike|cut|hold|pause|pivot|decision)'
        now reliably match Fed queries without 'the'.
        E.g. 'Fed hike probability', 'what are fed hike odds', 'analisis peluang fed cut bulan ini', 'Fed hold probability'.
        """
        fed_queries = [
            "Fed hike probability",
            "Fed cut probability",
            "what are fed hike odds",
            "analisis peluang fed cut bulan ini",
            "Fed hold probability",
        ]
        for q in fed_queries:
            is_macro = agent._is_macro_event_query(q)
            res = await agent._classify_query_complexity(q)
            assert is_macro is True, f"Expected macro match for: {q}"
            assert res == "deep_research", f"Query '{q}' routed to '{res}', expected 'deep_research'"

    @pytest.mark.asyncio
    async def test_vulnerability_historical_precedents_r1_library(self, agent):
        """
        Remedy 2: Canonical historical central bank surprise precedents
        from Milestone 1 (R1.2: Greenspan 1994, Bernanke 2013 No-Taper, Yellen 2015 Global Risk, tapering)
        now match macro_event_patterns and route to deep_research.
        """
        precedent_queries = [
            "Bagaimana preseden Bernanke 2013 no-taper?",
            "Analisis analogi Greenspan 1994 bond market massacre",
            "Analisis preseden Yellen 2015 global risk",
            "Bagaimana preseden tapering Bernanke?",
        ]
        for q in precedent_queries:
            is_macro = agent._is_macro_event_query(q)
            res = await agent._classify_query_complexity(q)
            assert is_macro is True, f"Expected macro match for: {q}"
            assert res == "deep_research", f"Query '{q}' routed to '{res}', expected 'deep_research'"

    @pytest.mark.asyncio
    async def test_vulnerability_asymmetric_intent_and_events(self, agent):
        """
        Remedy 3: 'market surprise' / 'kejutan pasar' and 'keputusan suku bunga'
        now have matching intent patterns ('surprise', 'kejutan', 'keputusan', 'decision')
        and self-sufficient compound triggers, routing cleanly to deep_research.
        """
        asymmetric_queries = [
            "Keputusan suku bunga The Fed",
            "Apakah ada market surprise dari The Fed?",
            "Apakah ada kejutan pasar dari The Fed?",
            "FOMC decision",
            "FOMC rate decision",
        ]
        for q in asymmetric_queries:
            is_macro = agent._is_macro_event_query(q)
            res = await agent._classify_query_complexity(q)
            assert is_macro is True, f"Expected macro match for: {q}"
            assert res == "deep_research", f"Query '{q}' routed to '{res}', expected 'deep_research'"


# ==============================================================================
# Suite 4: Non-Macro Complex Queries, Simple Commands, Action Verbs
# ==============================================================================

class TestNonMacroAndActionQueries:
    """Ensure non-macro queries do NOT false-positive into deep_research."""

    @pytest.mark.asyncio
    async def test_simple_commands_route_to_simple(self, agent):
        """Exact simple commands must return 'simple'."""
        commands = [
            "status",
            "posisi",
            "positions",
            "vix",
            "balance",
            "equity",
            "pnl",
            "drawdown",
            "stats",
            "performa",
            "trigger",
            "triggers",
            "history",
            "riwayat",
            "health",
            "kesehatan",
            "biaya",
            "token",
        ]
        for cmd in commands:
            assert agent._is_macro_event_query(cmd) is False, f"False positive macro on '{cmd}'"
            res = await agent._classify_query_complexity(cmd)
            assert res == "simple", f"Command '{cmd}' should be simple, got '{res}'"

    @pytest.mark.asyncio
    async def test_common_simple_queries(self, agent):
        """Simple balance, PnL, position status inquiries."""
        simple_queries = [
            "berapa saldo akun sekarang?",
            "cek posisi aktif",
            "tampilkan pnl hari ini",
            "lihat status performa paper trading",
            "berapa win rate sistem?",
            "cek kesehatan server",
        ]
        for q in simple_queries:
            assert agent._is_macro_event_query(q) is False, f"False positive macro on '{q}'"
            res = await agent._classify_query_complexity(q)
            assert res == "simple", f"Query '{q}' should be simple, got '{res}'"

    @pytest.mark.asyncio
    async def test_short_greetings(self, agent):
        """Short greetings under 15 characters."""
        greetings = [
            "halo",
            "hai",
            "hi",
            "hello",
            "ping",
            "makasih",
            "terima kasih",
            "thanks",
            "ok",
            "siap",
        ]
        for g in greetings:
            assert agent._is_macro_event_query(g) is False, f"False positive macro on '{g}'"
            res = await agent._classify_query_complexity(g)
            assert res == "simple", f"Greeting '{g}' should be simple, got '{res}'"

    @pytest.mark.asyncio
    async def test_action_verbs_route_to_complex(self, agent):
        """Action verbs must route to 'complex' (Tier 3 Claude for careful confirmation)."""
        actions = [
            "close all positions now",
            "tutup posisi EURUSD",
            "modify SL XAUUSD to 2650",
            "ubah TP USDJPY ke 155.00",
            "batalkan order pending",
            "cancel order #12345",
            "adjust stop loss EURUSD",
            "geser SL ke breakeven",
        ]
        for a in actions:
            assert agent._is_macro_event_query(a) is False, f"Action '{a}' should not be macro"
            res = await agent._classify_query_complexity(a)
            assert res == "complex", f"Action '{a}' should be complex, got '{res}'"

    @pytest.mark.asyncio
    async def test_non_macro_complex_queries(self, agent):
        """Analytical queries on technicals, trade reviews, and trade reasoning."""
        complex_queries = [
            "Kenapa trade XAUUSD tadi malam kena SL?",
            "Bagaimana setup ICT untuk EURUSD pada sesi London?",
            "Analisa teknikal indikator RSI divergence pada GBPUSD",
            "Evaluasi performa strategi Bollinger Band minggu ini",
            "Mengapa harga emas drop drastis tadi pagi?",
            "Bagaimana review jurnal trading kita bulan ini?",
        ]
        for q in complex_queries:
            assert agent._is_macro_event_query(q) is False, f"Query '{q}' should not be macro"
            res = await agent._classify_query_complexity(q)
            assert res == "complex", f"Query '{q}' should be complex, got '{res}'"

    @pytest.mark.asyncio
    async def test_common_medium_queries(self, agent):
        """General queries about news, summaries, and schedules."""
        medium_queries = [
            "berita pasar hari ini apa saja?",
            "ringkasan sesi New York",
            "apa jadwal rilis ekonomi hari ini?",
            "kapan sesi London buka?",
        ]
        for q in medium_queries:
            assert agent._is_macro_event_query(q) is False, f"Query '{q}' should not be macro"
            res = await agent._classify_query_complexity(q)
            assert res == "medium", f"Query '{q}' should be medium, got '{res}'"


# ==============================================================================
# Suite 5: Boundary Inputs & Adversarial Edge Cases
# ==============================================================================

class TestBoundaryAndAdversarialInputs:
    """Boundary values, malformed inputs, edge cases, and robustness."""

    @pytest.mark.asyncio
    async def test_empty_string_and_whitespace(self, agent):
        """Empty string and whitespace-only inputs."""
        assert agent._is_macro_event_query("") is False
        res_empty = await agent._classify_query_complexity("")
        assert res_empty == "simple"

        assert agent._is_macro_event_query("     ") is False
        res_ws = await agent._classify_query_complexity("     ")
        assert res_ws == "simple"

        assert agent._is_macro_event_query("\n\t\r") is False
        res_newline = await agent._classify_query_complexity("\n\t\r")
        assert res_newline == "simple"

    @pytest.mark.asyncio
    async def test_emojis_and_unusual_characters(self, agent):
        """Emojis and symbol strings."""
        assert agent._is_macro_event_query("🔥🔥🔥🚀🚀🚀") is False
        res = await agent._classify_query_complexity("🔥🔥🔥🚀🚀🚀")
        assert res != "deep_research"

        assert agent._is_macro_event_query("💰📈💵") is False
        res = await agent._classify_query_complexity("💰📈💵")
        assert res != "deep_research"

    @pytest.mark.asyncio
    async def test_injection_payloads(self, agent):
        """SQL injection, script injection, and template payloads."""
        payloads = [
            "' OR '1'='1' --",
            "<script>alert('xss')</script>",
            "{{7*7}}",
            "; DROP TABLE users; --",
        ]
        for p in payloads:
            assert agent._is_macro_event_query(p) is False, f"Payload '{p}' false positive"
            res = await agent._classify_query_complexity(p)
            assert res != "deep_research"

    @pytest.mark.asyncio
    async def test_regex_special_characters(self, agent):
        """Regex metacharacters must not raise re.error."""
        regex_chars = "*+?{}[].^$|\\()"
        assert agent._is_macro_event_query(regex_chars) is False
        res = await agent._classify_query_complexity(regex_chars)
        assert res != "deep_research"

    @pytest.mark.asyncio
    async def test_zero_width_characters(self, agent):
        """Zero-width and hidden unicode characters."""
        zw = "\u200b\u200c\u200d\ufeff"
        assert agent._is_macro_event_query(zw) is False
        res = await agent._classify_query_complexity(zw)
        assert res != "deep_research"

    @pytest.mark.asyncio
    async def test_non_latin_scripts(self, agent):
        """Non-Latin alphabets (Arabic, Chinese, Russian)."""
        non_latin = [
            "تحليل السوق",
            "市场分析",
            "анализ рынка",
        ]
        for nl in non_latin:
            assert agent._is_macro_event_query(nl) is False
            res = await agent._classify_query_complexity(nl)
            assert res != "deep_research"

    @pytest.mark.asyncio
    async def test_super_long_payloads(self, agent):
        """Extreme payload lengths (10,000 chars) should not cause ReDoS or OOM."""
        import time

        # 1. 10k random chars without macro terms
        long_non_macro = "X" * 10000
        t0 = time.perf_counter()
        assert agent._is_macro_event_query(long_non_macro) is False
        res = await agent._classify_query_complexity(long_non_macro)
        duration = time.perf_counter() - t0
        assert res == "complex"  # len > 300
        assert duration < 0.1, f"Execution took too long: {duration}s"

        # 2. 10k string with embedded macro query
        long_macro = ("A" * 5000) + " Analisis peluang keputusan suku bunga The Fed CME FedWatch " + ("B" * 5000)
        t0 = time.perf_counter()
        assert agent._is_macro_event_query(long_macro) is True
        res = await agent._classify_query_complexity(long_macro)
        duration = time.perf_counter() - t0
        assert res == "deep_research"
        assert duration < 0.1, f"Execution took too long: {duration}s"

    @pytest.mark.asyncio
    async def test_vulnerability_non_string_type_crash(self, agent):
        """
        Remedy 4: `_classify_query_complexity` now includes defensive type and empty guard,
        safely returning 'simple' on None, empty string, whitespace, or non-strings without crashing.
        """
        # _is_macro_event_query safely handles None and non-strings
        assert agent._is_macro_event_query(None) is False
        assert agent._is_macro_event_query(12345) is False
        assert agent._is_macro_event_query([]) is False

        # _classify_query_complexity safely returns 'simple' on None and non-strings
        assert await agent._classify_query_complexity(None) == "simple"
        assert await agent._classify_query_complexity(12345) == "simple"
        assert await agent._classify_query_complexity([]) == "simple"
        assert await agent._classify_query_complexity("") == "simple"
        assert await agent._classify_query_complexity("   ") == "simple"
