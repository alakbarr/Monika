# ==============================================================================
# File: tests/llm/test_prompt_layout_discipline.py
# Description: Regression tests enforcing static-first prefix prompt discipline
# ==============================================================================

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from monika.application.analysis.stages.per_asset.runner_mixins.prescreen import (
    PrescreenMixin,
)
from monika.application.analysis.stages.per_asset.runner_mixins.single_asset import (
    SingleAssetAnalysisMixin,
)
from monika.application.analysis.stages.fundamental_stage import FundamentalStage
from monika.application.analysis.subagent_spawner import DynamicSubagentPool
from monika.infrastructure.llm.cache_breakpoint_manager import CacheBreakpointManager
from monika.infrastructure.llm.prompt_compressor import estimate_tokens
from tests.conftest import create_mock_async_session


class DummyPerAssetRunner(SingleAssetAnalysisMixin):
    """Test harness for SingleAssetAnalysisMixin message assembly."""

    def __init__(self):
        self.settings = {
            "trading": {"cost_mode": "standard"},
            "agent_architecture": {"specialist_decomposition": False},
        }
        self._last_analysis_time = {}
        self._min_reanalysis_minutes = 0
        self.primary_client = None
        self.secondary_client = None
        self.session_trigger_client = None

    def _build_trimmed_user_message(self, symbol: str) -> str:
        return f"Analyze {symbol} and provide a structured trading decision."


class DummyPrescreenRunner(PrescreenMixin):
    """Test harness for PrescreenMixin system prompt verification."""

    def __init__(self):
        self.settings = {"trading": {"asset_universe": ["EURUSD"]}}
        self._last_analysis_time = {}
        self.always_open_assets = set()
        self._haiku_client = MagicMock()


@pytest.mark.asyncio
async def test_stage2_user_message_has_context_blocks_before_data_bundle():
    """Verify Stage 2 per-asset user message places context_blocks before data_bundle."""
    runner = DummyPerAssetRunner()
    session = create_mock_async_session()
    symbol = "EURUSD"

    # Mock dependencies to isolate message assembly in _run_single_asset
    runner._check_brief_freshness_and_quality = AsyncMock(return_value=(None, {"brief_ok": True}, []))
    runner._fetch_stage2_bundle = AsyncMock(
        return_value=("OHLCV_DATA_BUNDLE_CONTENT", {"regime": "trend"}, True, "Use SMC first")
    )
    runner._compose_stage2_system_prompt = MagicMock(return_value=("STATIC_SYS_PROMPT", None))
    runner._build_user_message = MagicMock(return_value="Core user instructions")
    runner._build_stage2_context_blocks = AsyncMock(
        return_value=[("FUNDAMENTAL BRIEF", "Shared cycle macro brief across all 20 assets")]
    )
    runner._check_minimum_data_quality = AsyncMock(return_value=(True, "ok"))
    runner._check_data_coherence_for_analysis = AsyncMock(return_value=(True, "coherent"))
    runner._run_prescreen = AsyncMock(return_value=(True, "passed"))
    runner._verify_data_currency = AsyncMock(return_value=(True, "fresh"))
    runner._fetch_precomputed_data = AsyncMock(return_value="")
    runner._recover_missing_analysis = AsyncMock(return_value=None)
    runner._post_process_analysis_verifications = AsyncMock(return_value=("wait", 0.5))

    mock_client = MagicMock()
    captured_kwargs = {}

    async def fake_run_agent(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "success": True,
            "decision": "wait",
            "confidence": 0.5,
            "symbol": symbol,
            "tool_calls_made": 0,
            "turns": 1,
        }

    mock_client.run_agent = AsyncMock(side_effect=fake_run_agent)
    mock_client.model = "minimax-m3.1-flash"
    runner.primary_client = mock_client

    with patch("monika.domain.market.instrument_identity.resolve_instrument_identity") as mock_res:
        mock_res.return_value.cot_code = "EUR"
        mock_res.return_value.canonical_symbol = "EURUSD"
        with patch(
            "monika.application.analysis.stages.per_asset.runner_mixins.single_asset.compute_prompt_invariants",
            new=AsyncMock(return_value=(1.10, 0.005, 0.01)),
        ):
            await runner.run_one(
                session=session,
                symbol=symbol,
                bypass_prescreen=True,
                skip_cooldown=True,
            )

    user_msg = captured_kwargs.get("user_message", "")
    assert "FUNDAMENTAL BRIEF" in user_msg, "Context blocks must be present in user message"
    assert "PRE-FETCHED" in user_msg, "Data bundle must be present in user message"

    ctx_pos = user_msg.index("FUNDAMENTAL BRIEF")
    bundle_pos = user_msg.index("PRE-FETCHED")
    assert ctx_pos < bundle_pos, (
        f"Prefix violation: context_blocks (pos {ctx_pos}) must precede "
        f"symbol-specific data_bundle (pos {bundle_pos}) to preserve cross-symbol cache sharing."
    )


@pytest.mark.asyncio
async def test_stage1_user_message_timestamp_at_tail():
    """Verify Stage 1 delta revision places execution timestamp at tail, not at byte 0."""
    stage = FundamentalStage(settings={})
    session = create_mock_async_session()

    mock_brief = MagicMock()
    mock_brief.id = 42
    mock_brief.generated_at = "2026-10-28 10:00:00"
    mock_brief.macro_regime = "trend"
    mock_brief.risk_sentiment = "risk-on"
    mock_brief.confidence = 0.85
    mock_brief.currency_bias = {"USD": "bullish"}
    mock_brief.content_markdown = "Strong US labor and sticky inflation"
    mock_brief.structured_json = "{}"

    mock_client = MagicMock()
    captured_prompt = None

    async def fake_classify_json(prompt, **kwargs):
        nonlocal captured_prompt
        captured_prompt = prompt
        return {
            "has_thesis_changed": False,
            "catalyst_impact": "REINFORCES_EXISTING_BIAS",
            "revision_summary": "Catalyst reinforces existing bias",
            "currency_bias_adjustments": {},
        }

    mock_client.classify_json = AsyncMock(side_effect=fake_classify_json)

    with patch("monika.application.analysis.stages.fundamental_stage.get_client_for_task", return_value=mock_client):
        # Mock session.execute to return mock_brief
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_brief
        session.execute = AsyncMock(return_value=mock_result)

        await stage.patch_brief(
            session=session,
            catalyst_text="US Core PCE printed in line with expectations at 0.2% MoM",
            catalyst_type="news",
        )

    assert captured_prompt is not None
    # Verify that dynamic timestamp is NOT at the start of the prompt
    assert not captured_prompt.startswith("CURRENT TIME:"), (
        "Cache buster: CURRENT TIME timestamp must not be placed at byte 0 of prompt."
    )
    assert "[EXECUTION_METADATA]: Current time is" in captured_prompt
    # Verify that EXECUTION_METADATA is in the final lines (tail)
    lines = [line.strip() for line in captured_prompt.strip().split("\n") if line.strip()]
    tail_text = "\n".join(lines[-3:])
    assert "[EXECUTION_METADATA]: Current time is" in tail_text, (
        f"Execution timestamp must be at the very tail of the prompt. Tail was:\n{tail_text}"
    )


@pytest.mark.asyncio
async def test_prescreen_has_non_empty_padded_system_prompt():
    """Verify stage2_prescreen passes a static padded system prompt exceeding threshold."""
    runner = DummyPrescreenRunner()
    session = create_mock_async_session()

    captured_system_prompt = None

    async def fake_classify_json(prompt, system_prompt=None, **kwargs):
        nonlocal captured_system_prompt
        captured_system_prompt = system_prompt
        return {"decision": "YES", "reason": "active setup"}

    runner._haiku_client.classify_json = AsyncMock(side_effect=fake_classify_json)
    runner._haiku_client.model = "gemini-3.5-flash-lite"

    # Mock DB queries to bypass early exit filters
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)

    await runner._run_prescreen(session=session, symbol="EURUSD")

    assert captured_system_prompt is not None, "stage2_prescreen must provide a system_prompt"
    assert len(captured_system_prompt) >= CacheBreakpointManager.GEMINI_3_MIN_CACHEABLE_CHARS, (
        f"Prescreen system prompt ({len(captured_system_prompt)} chars) must exceed minimum threshold "
        f"({CacheBreakpointManager.GEMINI_3_MIN_CACHEABLE_CHARS} chars) for Gemini caching."
    )


def test_deep_research_system_prompt_exceeds_threshold():
    """Verify deep_research subagent specs include CANONICAL_TIER0_ANCHOR and exceed 4,096 tokens."""
    pool = DynamicSubagentPool(settings={})
    tools = [
        {"name": "get_treasury_yields", "description": "Yields"},
        {"name": "get_price_history", "description": "Price history"},
    ]

    base_prompt = "You are a research subagent examining macro and technical trends."
    specs = pool.decompose_research_query(
        query="Analyze US 10Y yield divergence with USDJPY",
        base_system_prompt=base_prompt,
        available_tools=tools,
    )

    assert len(specs) > 0, "Must generate research subagent specs"
    for spec in specs:
        anchor_prefix = CacheBreakpointManager.CANONICAL_TIER0_ANCHOR[:80]
        assert anchor_prefix in spec.system_prompt, (
            f"Worker '{spec.worker_id}' system prompt must contain CANONICAL_TIER0_ANCHOR."
        )
        tokens = estimate_tokens(spec.system_prompt)
        assert tokens >= 4096, (
            f"Worker '{spec.worker_id}' system prompt ({tokens} tokens) must meet or exceed 4,096 tokens "
            "for Claude Opus / Gemini 4 Argon prompt cache qualification."
        )


@pytest.mark.asyncio
async def test_context_compaction_uses_isolated_padded_system_prompt():
    """Verify compaction uses its own isolated static system prompt with anchor when offloading."""
    from monika.infrastructure.llm.context_compaction import ContextCompactionEngine

    compactor = ContextCompactionEngine({})
    messages = [
        {"role": "user", "content": "Compute volatility"},
    ]
    for i in range(5):
        messages.append({"role": "assistant", "content": f"Intermediate step {i} " * 200})
        messages.append({"role": "user", "content": f"Intermediate observation {i} " * 200})

    mock_client = MagicMock()
    mock_client.model = "gemini-3.5-flash-lite"
    mock_client.provider = "gemini"
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "<compacted-summary>\nPreserved analysis\n</compacted-summary>"
    mock_client.run_tool_agent = AsyncMock(return_value=mock_resp)

    with patch("monika.infrastructure.providers.llm_factory.get_client_for_task", return_value=mock_client):
        await compactor.compact_with_summary_model(
            messages=messages,
            context_window=1000,
        )

    assert mock_client.run_tool_agent.called
    call_kwargs = mock_client.run_tool_agent.call_args.kwargs
    sys_prompt = call_kwargs.get("system_prompt", "")
    assert "Context Compaction Engine" in sys_prompt
    assert len(sys_prompt) >= CacheBreakpointManager.GEMINI_3_MIN_CACHEABLE_CHARS
