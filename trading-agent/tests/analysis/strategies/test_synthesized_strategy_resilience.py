"""Unit tests for synthesized strategy resilience and safe_evaluate error boundary."""

import pytest
from unittest.mock import AsyncMock, patch
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal, CandleDict
from analysis.strategies.registry import StrategyRegistry
from analysis.strategies.synthesized.alpha_eurusd_6d622a import SynthesizedStrategy_alpha_eurusd_6d622a
from scheduler.strategy_synthesis_scheduler import StrategySynthesisScheduler


@pytest.mark.asyncio
async def test_alpha_eurusd_6d622a_evaluates_without_nan_casting_error():
    """Verify alpha_eurusd_6d622a executes cleanly without IntCastingNaNError even on low/zero volumes."""
    strat = SynthesizedStrategy_alpha_eurusd_6d622a()

    # Generate 100 mock candles with varying/zero volumes
    mock_candles = []
    for i in range(100):
        mock_candles.append(CandleDict({
            "timestamp": f"2026-09-08T{i % 24:02d}:00:00Z",
            "open": 1.0850 + (i * 0.0001),
            "high": 1.0860 + (i * 0.0001),
            "low": 1.0840 + (i * 0.0001),
            "close": 1.0855 + (i * 0.0001),
            "volume": 0.0 if i < 20 else (100.0 + i),
        }))

    with patch.object(strat, "get_historical_candles", AsyncMock(return_value=mock_candles)):
        sig = await strat.evaluate(AsyncMock(), "EURUSD", {})

    assert isinstance(sig, EdgeSignal)
    assert sig.symbol == "EURUSD"
    assert sig.strategy_id == "alpha_eurusd_6d622a"
    # Should not crash with IntCastingNaNError
    assert "Cannot convert non-finite" not in sig.rationale


@pytest.mark.asyncio
async def test_compile_strategy_class_safe_evaluate_boundary():
    """Verify compile_strategy_class wraps evaluate() with safe_evaluate to catch any unhandled exception."""
    buggy_code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class SynthesizedStrategy_alpha_test_buggy(EdgeStrategy):
    strategy_id: str = "alpha_test_buggy"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        # Deliberate runtime exception simulation
        raise ValueError("Cannot convert non-finite values (NA or inf) to integer")
"""
    scheduler = StrategySynthesisScheduler({})
    compiled_cls = scheduler.compile_strategy_class(buggy_code, "SynthesizedStrategy_alpha_test_buggy")
    assert compiled_cls is not None

    strat = compiled_cls()
    sig = await strat.evaluate(AsyncMock(), "EURUSD", {})

    assert isinstance(sig, EdgeSignal)
    assert sig.valid is False
    assert sig.strategy_id == "alpha_test_buggy"
    assert "Evaluation failed" in sig.rationale
    assert "evaluation_error" in sig.tags


@pytest.mark.asyncio
async def test_strategy_registry_evaluate_all_isolation():
    """Verify StrategyRegistry.evaluate_all continues when a strategy raises an exception."""
    class CrashingStrategy(EdgeStrategy):
        strategy_id: str = "alpha_crashing"
        applicable_symbols: set = {"EURUSD"}

        async def evaluate(self, session, symbol, settings):
            raise RuntimeError("Catastrophic strategy failure")

    class HealthyStrategy(EdgeStrategy):
        strategy_id: str = "alpha_healthy"
        applicable_symbols: set = {"EURUSD"}

        async def evaluate(self, session, symbol, settings):
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction="buy",
                valid=True,
                confidence=0.8,
                rationale="Healthy signal"
            )

    try:
        StrategyRegistry.register(CrashingStrategy, overwrite=True)
        StrategyRegistry.register(HealthyStrategy, overwrite=True)

        signals = await StrategyRegistry.evaluate_all(AsyncMock(), "EURUSD", {})
        healthy_signals = [s for s in signals if s.strategy_id == "alpha_healthy"]
        assert len(healthy_signals) == 1
        assert healthy_signals[0].direction == "buy"
    finally:
        StrategyRegistry._registry.pop("alpha_crashing", None)
        StrategyRegistry._registry.pop("alpha_healthy", None)


def test_sanitize_strategy_code_modern_pandas():
    """Verify StrategySynthesisScheduler.sanitize_strategy_code rewrites deprecated fillna(method=)."""
    raw_code = """
import pandas as pd
df = pd.DataFrame({'a': [1, None, 3]})
df.fillna(method='ffill', inplace=True)
df.fillna(method="bfill", inplace=True)
df['x'] = df['a'].fillna(method='ffill')
df['y'] = df['a'].fillna(method="bfill")
df.fillna(inplace=True, method='ffill')
df.fillna(inplace=False, method='bfill')
from app.something import helper
"""
    sanitized = StrategySynthesisScheduler.sanitize_strategy_code(raw_code)
    assert "method=" not in sanitized
    assert "df.ffill(inplace=True)" in sanitized
    assert "df.bfill(inplace=True)" in sanitized
    assert "df['a'].ffill()" in sanitized
    assert "df['a'].bfill()" in sanitized
    assert "from analysis.strategies.base_strategy import helper" in sanitized


@pytest.mark.asyncio
async def test_compile_strategy_with_deprecated_fillna_succeeds():
    """Verify compiling and evaluating code with deprecated fillna works due to auto-sanitization."""
    code_with_deprecated_fillna = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any
import pandas as pd
import numpy as np

class SynthesizedStrategy_alpha_test_fillna(EdgeStrategy):
    strategy_id: str = "alpha_test_fillna"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        df = pd.DataFrame({'close': [1.0, np.nan, 1.2]})
        df.fillna(method='ffill', inplace=True)
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="buy",
            valid=True,
            confidence=0.85,
            rationale="Passes cleanly"
        )
"""
    scheduler = StrategySynthesisScheduler({})
    compiled_cls = scheduler.compile_strategy_class(code_with_deprecated_fillna, "SynthesizedStrategy_alpha_test_fillna")
    assert compiled_cls is not None

    strat = compiled_cls()
    sig = await strat.evaluate(AsyncMock(), "EURUSD", {})
    assert isinstance(sig, EdgeSignal)
    assert sig.valid is True
    assert sig.direction == "buy"
    assert "error" not in sig.tags


@pytest.mark.asyncio
async def test_repaired_synthesized_strategies_execution():
    """Verify repaired strategies evaluate without NDFrame.fillna error on mock candles."""
    from analysis.strategies.synthesized.alpha_xtiusd_f30ff5 import SynthesizedStrategy_alpha_xtiusd_f30ff5
    from analysis.strategies.synthesized.alpha_xbrusd_e55dbf import SynthesizedStrategy_alpha_xbrusd_e55dbf
    from analysis.strategies.synthesized.alpha_xauusd_94ad53 import SynthesizedStrategy_alpha_xauusd_94ad53
    from analysis.strategies.synthesized.alpha_usdjpy_13a603 import SynthesizedStrategy_alpha_usdjpy_13a603

    mock_candles = [
        CandleDict({
            "timestamp": f"2026-09-08T{i % 24:02d}:00:00Z",
            "open": 100.0 + i,
            "high": 102.0 + i,
            "low": 99.0 + i,
            "close": 101.0 + i,
            "volume": 50.0 + i,
        })
        for i in range(120)
    ]

    for strat_cls, sym in [
        (SynthesizedStrategy_alpha_xtiusd_f30ff5, "XTIUSD"),
        (SynthesizedStrategy_alpha_xbrusd_e55dbf, "XBRUSD"),
        (SynthesizedStrategy_alpha_xauusd_94ad53, "XAUUSD"),
        (SynthesizedStrategy_alpha_usdjpy_13a603, "USDJPY"),
    ]:
        strat = strat_cls({})
        with patch.object(strat, "get_historical_candles", AsyncMock(return_value=mock_candles)):
            sig = await strat.evaluate(AsyncMock(), sym, {})
            assert isinstance(sig, EdgeSignal)
            # Must not crash with TypeError fillna() got an unexpected keyword argument 'method'
            assert "NDFrame.fillna" not in sig.rationale


def test_sanitize_strategy_code_repairs_missing_except_at_eof():
    """Verify StrategySynthesisScheduler.sanitize_strategy_code auto-repairs missing except/finally at EOF."""
    code_with_missing_except = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class SynthesizedStrategy_alpha_eof_repair(EdgeStrategy):
    strategy_id: str = "alpha_eof_repair"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            x = 1.0
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction="buy",
                valid=True,
                confidence=0.85,
                rationale="Complete signal without explicit except block",
                tags=["trend"]
            )
"""
    sanitized = StrategySynthesisScheduler.sanitize_strategy_code(code_with_missing_except)
    import ast
    # Must now be parseable by Python AST
    tree = ast.parse(sanitized)
    assert tree is not None
    assert "except Exception as e:" in sanitized
    assert "Calculation error" in sanitized


def test_sanitize_strategy_code_repairs_inline_unclosed_try():
    """Verify StrategySynthesisScheduler.sanitize_strategy_code auto-repairs unclosed try inside loop."""
    code_with_loop_try = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class SynthesizedStrategy_alpha_loop_repair(EdgeStrategy):
    strategy_id: str = "alpha_loop_repair"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        candles = []
        for c in candles:
            try:
                open_val = getattr(c, 'open', 0.0)
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="sell",
            valid=True,
            confidence=0.75,
            rationale="Repaired inline try",
            tags=["trend"]
        )
"""
    sanitized = StrategySynthesisScheduler.sanitize_strategy_code(code_with_loop_try)
    import ast
    tree = ast.parse(sanitized)
    assert tree is not None
    assert "except Exception:" in sanitized


@pytest.mark.asyncio
async def test_compile_strategy_with_missing_except_repaired():
    """Verify compile_strategy_class compiles and evaluates code that omitted except block."""
    code_missing_except = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class SynthesizedStrategy_alpha_test_compile_repair(EdgeStrategy):
    strategy_id: str = "alpha_test_compile_repair"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction="buy",
                valid=True,
                confidence=0.90,
                rationale="Auto-repaired except block compilation test"
            )
"""
    scheduler = StrategySynthesisScheduler({})
    compiled_cls = scheduler.compile_strategy_class(code_missing_except, "SynthesizedStrategy_alpha_test_compile_repair")
    assert compiled_cls is not None

    strat = compiled_cls()
    sig = await strat.evaluate(AsyncMock(), "EURUSD", {})
    assert isinstance(sig, EdgeSignal)
    assert sig.valid is True
    assert sig.direction == "buy"
    assert sig.confidence == 0.90


@pytest.mark.asyncio
async def test_synthesize_code_falls_back_on_syntax_error():
    """Verify synthesize_code returns None without generating fake stub when LLM returns unparseable code."""
    scheduler = StrategySynthesisScheduler({})

    mock_llm_client = AsyncMock()
    # Simulate LLM returning unfixable syntax error (e.g., broken brackets and unclosed tokens)
    mock_llm_client.generate = AsyncMock(return_value="```python\ndef broken(\n  (((bad\n```")

    with patch("analysis.providers.llm_factory.get_client_for_task", return_value=mock_llm_client):
        res = await scheduler.synthesize_code("EURUSD", "Test Concept")
        assert res is None


def test_sanitize_strategy_reindents_unindented_evaluate():
    """Verify sanitize_strategy_code re-indents 'async def evaluate' placed at column 0."""
    unindented_code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class SynthesizedStrategy_alpha_reindent_test(EdgeStrategy):
    strategy_id: str = "alpha_reindent_test"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)

async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
    try:
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="buy",
            valid=True,
            confidence=0.88,
            rationale="Reindented evaluate worked"
        )
    except Exception as e:
        return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0, rationale=f"Error: {e}", tags=["error"])
"""
    sanitized = StrategySynthesisScheduler.sanitize_strategy_code(unindented_code)
    scheduler = StrategySynthesisScheduler({})
    compiled_cls = scheduler.compile_strategy_class(sanitized, "SynthesizedStrategy_alpha_reindent_test")
    assert compiled_cls is not None
    # Canary instantiation must succeed without abstract method TypeError
    inst = compiled_cls()
    assert inst is not None


@pytest.mark.asyncio
async def test_compile_strategy_resolves_method_alias():
    """Verify compile_strategy_class maps common alias 'generate_signals' to 'evaluate'."""
    alias_code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class SynthesizedStrategy_alpha_alias_test(EdgeStrategy):
    strategy_id: str = "alpha_alias_test"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)

    async def generate_signals(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="sell",
            valid=True,
            confidence=0.82,
            rationale="Aliased generate_signals resolved"
        )
"""
    scheduler = StrategySynthesisScheduler({})
    compiled_cls = scheduler.compile_strategy_class(alias_code, "SynthesizedStrategy_alpha_alias_test")
    assert compiled_cls is not None
    inst = compiled_cls()
    sig = await inst.evaluate(AsyncMock(), "EURUSD", {})
    assert sig.direction == "sell"
    assert sig.confidence == 0.82


def test_compile_strategy_rejects_missing_evaluate_cleanly():
    """Verify compile_strategy_class returns None if class completely lacks evaluate/aliases."""
    code_without_evaluate = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class SynthesizedStrategy_alpha_no_evaluate(EdgeStrategy):
    strategy_id: str = "alpha_no_evaluate"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
"""
    scheduler = StrategySynthesisScheduler({})
    compiled_cls = scheduler.compile_strategy_class(code_without_evaluate, "SynthesizedStrategy_alpha_no_evaluate")
    # Must reject cleanly with None rather than returning uninstantiable class
    assert compiled_cls is None


@pytest.mark.asyncio
async def test_synthesize_code_falls_back_on_missing_evaluate():
    """Verify synthesize_code falls back to deterministic template when LLM code lacks evaluate."""
    code_no_evaluate = """```python
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class SynthesizedStrategy_alpha_eurusd_testfail(EdgeStrategy):
    strategy_id: str = "alpha_eurusd_testfail"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
```"""
    scheduler = StrategySynthesisScheduler({})
    mock_llm_client = AsyncMock()
    mock_llm_client.generate = AsyncMock(return_value=code_no_evaluate)

    with patch("analysis.providers.llm_factory.get_client_for_task", return_value=mock_llm_client):
        res = await scheduler.synthesize_code("EURUSD", "Test Concept")
        assert res is None


def test_sanitize_strategy_repairs_unclosed_paren_at_line_24():
    """Verify sanitize_strategy_code auto-repairs '(' was never closed on nested call at line 24."""
    code_with_unclosed_paren = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class SynthesizedStrategy_alpha_unclosed_paren(EdgeStrategy):
    strategy_id: str = "alpha_unclosed_paren"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)
        self.ma_period = int(self.cfg.get("ma_period", 20))

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            atr_p = int(settings.get('atr_period', 14))
            ma_p = int(settings.get('ma_period', self.ma_period)
            exhaustion_mult = float(settings.get('exhaustion_multiplier', 2.5))
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction="buy",
                valid=True,
                confidence=0.85,
                rationale="Unclosed paren at line 24 repaired"
            )
        except Exception as e:
            return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0, rationale=f"Error: {e}", tags=["error"])
"""
    sanitized = StrategySynthesisScheduler.sanitize_strategy_code(code_with_unclosed_paren)
    import ast
    # Must now parse cleanly without '(' was never closed
    tree = ast.parse(sanitized)
    assert tree is not None
    assert "ma_p = int(settings.get('ma_period', self.ma_period))" in sanitized


def test_sanitize_strategy_repairs_multiline_unclosed_call():
    """Verify sanitize_strategy_code auto-repairs unclosed multi-line call."""
    multiline_unclosed = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class SynthesizedStrategy_alpha_multiline_call(EdgeStrategy):
    strategy_id: str = "alpha_multiline_call"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        try:
            candles = await self.get_historical_candles(
                session=session,
                symbol=symbol,
                timeframe='H1',
                limit=100
            multiplier = float(settings.get('mult', 1.5))
            return EdgeSignal(
                strategy_id=self.strategy_id,
                symbol=symbol,
                direction="sell",
                valid=True,
                confidence=0.8,
                rationale="Multi-line unclosed call repaired"
            )
        except Exception as e:
            return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0, rationale=f"Error: {e}", tags=["error"])
"""
    sanitized = StrategySynthesisScheduler.sanitize_strategy_code(multiline_unclosed)
    import ast
    tree = ast.parse(sanitized)
    assert tree is not None
    assert "limit=100)" in sanitized


@pytest.mark.asyncio
async def test_compile_strategy_with_unclosed_paren_succeeds():
    """Verify compile_strategy_class compiles and evaluates candidate with unclosed paren."""
    code_with_unclosed = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, Dict, Any

class SynthesizedStrategy_alpha_test_compile_unclosed(EdgeStrategy):
    strategy_id: str = "alpha_test_compile_unclosed"
    applicable_symbols: set = {"EURUSD"}

    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
        super().__init__(settings or {}, *args, **kwargs)

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        val = int(settings.get('threshold', 10)
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="buy",
            valid=True,
            confidence=0.88,
            rationale="Compiled after unclosed paren repair"
        )
"""
    scheduler = StrategySynthesisScheduler({})
    compiled_cls = scheduler.compile_strategy_class(code_with_unclosed, "SynthesizedStrategy_alpha_test_compile_unclosed")
    assert compiled_cls is not None
    inst = compiled_cls()
    sig = await inst.evaluate(AsyncMock(), "EURUSD", {})
    assert sig.direction == "buy"
    assert sig.confidence == 0.88


@pytest.mark.asyncio
async def test_strategy_registry_blacklists_and_purges_stub_synthesized_strategy():
    """Verify StrategyRegistry detects stub, records in _blacklisted_ids, and purges from DB."""
    import json
    from unittest.mock import MagicMock
    from database.models import SystemConfig

    StrategyRegistry._blacklisted_ids.clear()
    s_id = "alpha_test_blacklisted_stub_999"

    stub_payload = json.dumps({
        "strategy_id": s_id,
        "class_name": f"SynthesizedStrategy_{s_id}",
        "python_code": 'direction="buy" and confidence=0.82',
    })
    mock_config = SystemConfig(key=f"synthesized_strategy_{s_id}", value=stub_payload)

    mock_session = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [mock_config]
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute = AsyncMock(return_value=mock_result)

    # First load: detects stub, adds to blacklist, calls delete
    await StrategyRegistry.load_dynamic_parameters(mock_session)

    assert s_id in StrategyRegistry._blacklisted_ids
    # Verify delete was called
    from sqlalchemy.sql.dml import Delete
    delete_calls = [c for c in mock_session.execute.call_args_list if len(c.args) > 0 and isinstance(c.args[0], Delete)]
    assert len(delete_calls) >= 1

    # Second load: skipped immediately via _blacklisted_ids check
    mock_session.execute.reset_mock()
    mock_scalars.all.return_value = [mock_config]
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_result

    await StrategyRegistry.load_dynamic_parameters(mock_session)
    # delete should not be called again because it was already blacklisted
    second_delete_calls = [c for c in mock_session.execute.call_args_list if len(c.args) > 0 and isinstance(c.args[0], Delete)]
    assert len(second_delete_calls) == 0


@pytest.mark.asyncio
async def test_strategy_registry_evaluate_all_throttling():
    """Verify evaluate_all throttles load_dynamic_parameters within _load_interval."""
    import time
    mock_session = AsyncMock()
    StrategyRegistry._last_load_time = time.time()  # just loaded

    with patch.object(StrategyRegistry, "load_dynamic_parameters", AsyncMock()) as mock_load:
        await StrategyRegistry.evaluate_all(mock_session, "EURUSD", {})
        # Should be throttled, not calling load_dynamic_parameters
        assert mock_load.call_count == 0

        # With force_reload=True, it should execute
        await StrategyRegistry.evaluate_all(mock_session, "EURUSD", {}, force_reload=True)
        assert mock_load.call_count == 1





