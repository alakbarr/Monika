import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from analysis.strategies.registry import StrategyRegistry
from scheduler.strategy_synthesis_scheduler import (
    StrategySynthesisScheduler,
    SynthesizedStrategyCandidate,
)


@pytest.fixture
def scheduler(tmp_path):
    sched = StrategySynthesisScheduler(
        settings={"trading": {"asset_universe": ["EURUSD"]}},
        min_sharpe=1.5,
        max_drawdown_pct=10.0,
        min_trades=5,
    )
    sched.SYNTHESIZED_DIR = tmp_path
    return sched


def test_code_safety_validation(scheduler):
    """Verifies that malicious or disallowed operations are rejected by AST scanner, while safe OOP/quant code is accepted."""
    safe_code = """
import logging
from decimal import Decimal
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SafeStrategy(EdgeStrategy):
    strategy_id = "safe_strat_1"
    applicable_symbols = {"EURUSD"}

    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.min_threshold = Decimal("0.001")

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        logger.debug(f"Evaluating {symbol}")
        return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction="buy", valid=True, confidence=0.8)
    """.strip()

    unsafe_code_eval = "eval('1 + 1')"
    unsafe_code_os = "import os\nos.system('echo hack')"
    unsafe_code_subprocess = "import subprocess\nsubprocess.run(['dir'])"
    unsafe_code_class_traversal = "x = ().__class__.__bases__[0].__subclasses__()"

    assert scheduler.validate_code_safety(safe_code) is True
    assert scheduler.validate_code_safety(unsafe_code_eval) is False
    assert scheduler.validate_code_safety(unsafe_code_os) is False
    assert scheduler.validate_code_safety(unsafe_code_subprocess) is False
    assert scheduler.validate_code_safety(unsafe_code_class_traversal) is False


def test_strategy_compilation(scheduler):
    """Verifies compilation of valid code with __init__, logging, and decimal into an EdgeStrategy class."""
    code = """
import logging
from decimal import Decimal
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

class CompiledTestStrategy(EdgeStrategy):
    strategy_id = "compiled_test_1"
    applicable_symbols = {"EURUSD"}

    def __init__(self, settings: Dict[str, Any]):
        super().__init__(settings)
        self.dec_val = Decimal("1.5")

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction="buy", valid=True, confidence=0.9)
    """.strip()

    strat_cls = scheduler.compile_strategy_class(code, "CompiledTestStrategy")
    assert strat_cls is not None
    assert strat_cls.strategy_id == "compiled_test_1"
    instance = strat_cls({})
    assert instance.strategy_id == "compiled_test_1"
    assert instance.dec_val == Decimal("1.5")

    # Test invalid class name
    assert scheduler.compile_strategy_class(code, "NonExistentClass") is None


def test_sandbox_backtest_metrics(scheduler):
    """Verifies accurate calculation of Sharpe, Max DD, Win Rate in sandbox."""
    code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

class SandboxTestStrat(EdgeStrategy):
    strategy_id = "sandbox_strat_1"
    applicable_symbols = {"EURUSD"}

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0)
    """.strip()

    strat_cls = scheduler.compile_strategy_class(code, "SandboxTestStrat")
    assert strat_cls is not None

    # Synthetic return series with strong positive drift and small drawdown
    high_perf_returns = [0.01, 0.015, -0.005, 0.02, 0.01, 0.018, -0.003, 0.012, 0.025, 0.008]
    metrics = scheduler.run_backtest_sandbox(strat_cls, "EURUSD", simulated_returns=high_perf_returns)

    assert metrics["sharpe"] > 1.5
    assert metrics["max_drawdown_pct"] < 10.0
    assert metrics["win_rate_pct"] == 80.0
    assert metrics["trades"] == 10


@pytest.mark.asyncio
async def test_evaluate_and_register_qualified_candidate(scheduler, tmp_path):
    """Verifies that candidates passing quant criteria are registered into StrategyRegistry and saved."""
    code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

class HighAlphaStrategy(EdgeStrategy):
    strategy_id = "high_alpha_quant_1"
    applicable_symbols = {"EURUSD"}

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="buy",
            valid=True,
            confidence=0.88,
            tags=["trend"]
        )
    """.strip()

    # Pass returns giving Sharpe > 1.5, Max DD < 10%
    returns = [0.01, 0.02, -0.004, 0.015, 0.022, 0.008, 0.019]

    with patch("scheduler.strategy_synthesis_scheduler.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_exec = MagicMock()
        mock_exec.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_exec
        mock_get_session.return_value.__aenter__.return_value = mock_session

        candidate = await scheduler.evaluate_and_register_candidate(
            strategy_id="high_alpha_quant_1",
            class_name="HighAlphaStrategy",
            code_str=code,
            symbol="EURUSD",
            simulated_returns=returns,
        )

        assert candidate is not None
        assert candidate.sharpe_ratio > 1.5
        assert candidate.max_drawdown_pct < 10.0
        assert candidate.status == "REGISTERED"

        # Verify registration in StrategyRegistry
        registered = StrategyRegistry.get_strategy("high_alpha_quant_1")
        assert registered is not None
        assert registered.strategy_id == "high_alpha_quant_1"

        # Verify strategy evaluation works via registry
        signals = await StrategyRegistry.evaluate_all(mock_session, "EURUSD", {"trading": {"edge_strategy": {}}})
        assert any(s.strategy_id == "high_alpha_quant_1" for s in signals)

        # Verify file persisted to disk
        assert (tmp_path / "high_alpha_quant_1.py").exists()

        # Verify ActivityLog entry was added with related_id=None
        from database.models import ActivityLog
        added_activities = [
            call.args[0] for call in mock_session.add.call_args_list
            if isinstance(call.args[0], ActivityLog)
        ]
        assert len(added_activities) == 1
        assert added_activities[0].related_id is None
        assert "high_alpha_quant_1" in added_activities[0].description


@pytest.mark.asyncio
async def test_reject_sub_threshold_candidate(scheduler):
    """Verifies that candidates failing Sharpe (>1.5) or Max DD (<10%) are rejected."""
    code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

class BadStrategy(EdgeStrategy):
    strategy_id = "bad_alpha_1"
    applicable_symbols = {"EURUSD"}

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0)
    """.strip()

    # Returns with large drawdown (-15%) and low Sharpe
    bad_returns = [0.01, -0.15, -0.05, 0.02, -0.08, 0.01]

    candidate = await scheduler.evaluate_and_register_candidate(
        strategy_id="bad_alpha_1",
        class_name="BadStrategy",
        code_str=code,
        symbol="EURUSD",
        simulated_returns=bad_returns,
    )

    assert candidate is None
    assert StrategyRegistry.get_strategy("bad_alpha_1") is None


def test_ast_security_blocks_indirect_builtins_and_exploits(scheduler):
    """Verifies that obfuscated exploits and unauthorized imports are strictly rejected."""
    # 1. Indirect builtin access via getattr
    p1 = "def f(): return getattr(__builtins__, 'eval')('1+1')"
    assert scheduler.validate_code_safety(p1) is False

    # 2. Direct __import__ call
    p2 = "def f(): return __import__('os').system('dir')"
    assert scheduler.validate_code_safety(p2) is False

    # 3. Class hierarchy traversal (__subclasses__)
    p3 = "def f(): return ().__class__.__bases__[0].__subclasses__()"
    assert scheduler.validate_code_safety(p3) is False

    # 4. Unauthorized module import (socket, subprocess, requests)
    p4 = "import socket\ndef f(): return socket.socket()"
    assert scheduler.validate_code_safety(p4) is False

    # 5. Dunder name traversal
    p5 = "def f(): return __builtins__"
    assert scheduler.validate_code_safety(p5) is False


@pytest.mark.asyncio
async def test_walk_forward_gating_blocks_overfitted_candidate(scheduler):
    """Verifies that an overfitted strategy (great in-sample, poor out-of-sample) is blocked by walk-forward gating."""
    code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

class OverfittedStrategy(EdgeStrategy):
    strategy_id = "overfitted_alpha_1"
    applicable_symbols = {"EURUSD"}

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction="buy",
            valid=True,
            confidence=0.9,
            tags=["trend"]
        )
    """.strip()

    # IS (first 60% = 6 trades): huge wins (+2% each, Sharpe > 10)
    # OOS (last 40% = 4 trades): losses (-1% each, negative Sharpe)
    returns = [0.02, 0.025, 0.02, 0.022, 0.021, 0.023, -0.015, -0.012, -0.018, -0.010]

    scheduler.walk_forward_enabled = True
    scheduler.min_walk_forward_sharpe = 1.0

    candidate = await scheduler.evaluate_and_register_candidate(
        strategy_id="overfitted_alpha_1",
        class_name="OverfittedStrategy",
        code_str=code,
        symbol="EURUSD",
        simulated_returns=returns,
    )
    # Must be rejected because out-of-sample failed walk-forward gating
    assert candidate is None


def test_safe_getattr_allowed_and_dangerous_rejected(scheduler):
    """Verifies that literal safe getattr calls are permitted while dangerous/dynamic ones are rejected."""
    # Safe literal getattr
    safe_code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

class SafeGetattrStrategy(EdgeStrategy):
    strategy_id = "safe_getattr_1"
    applicable_symbols = {"EURUSD"}

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        val = getattr(settings, "risk_pct", 0.01)
        return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction="buy", valid=True, confidence=val)
    """.strip()
    assert scheduler.validate_code_safety(safe_code) is True

    # Dangerous: accessing dunder attribute via getattr
    bad_dunder = "def f(obj): return getattr(obj, '__class__')"
    assert scheduler.validate_code_safety(bad_dunder) is False

    # Dangerous: accessing system attribute via getattr
    bad_attr = "def f(obj): return getattr(obj, 'system')('ls')"
    assert scheduler.validate_code_safety(bad_attr) is False

    # Dangerous: target is __builtins__
    bad_builtins = "def f(): return getattr(__builtins__, 'eval')"
    assert scheduler.validate_code_safety(bad_builtins) is False

    # Dangerous: dynamic variable attribute name (not a string literal)
    bad_dynamic = "def f(obj, name): return getattr(obj, name)"
    assert scheduler.validate_code_safety(bad_dynamic) is False


def test_compile_strategy_auto_injects_strategy_id_and_safe_init(scheduler):
    """Verifies that compiled strategies are robust against missing strategy_id and kwargs-only __init__."""
    # Strategy without class-level strategy_id and with kwargs-only __init__
    code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

class KwargsOnlyStrategy(EdgeStrategy):
    applicable_symbols = {"EURUSD"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.param = 42

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction="buy", valid=True, confidence=0.8)
    """.strip()

    strat_cls = scheduler.compile_strategy_class(code, "KwargsOnlyStrategy")
    assert strat_cls is not None
    # Auto-injected strategy_id
    assert getattr(strat_cls, "strategy_id", None) is not None

    # Instantiate with positional settings (should not raise TypeError)
    instance = strat_cls({"trading": {}})
    assert instance is not None
    assert instance.param == 42
    assert instance.settings == {"trading": {}}


@pytest.mark.asyncio
async def test_strategy_registry_evaluate_all_isolation():
    """Verifies that an error in one strategy does not crash evaluate_all for other strategies."""
    from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal

    class BrokenInitStrategy(EdgeStrategy):
        strategy_id = "broken_init_strat"
        applicable_symbols = {"EURUSD"}
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Fatal instantiation failure")
        async def evaluate(self, session, symbol, settings):
            return None

    class WorkingStrategy(EdgeStrategy):
        strategy_id = "working_strat"
        applicable_symbols = {"EURUSD"}
        async def evaluate(self, session, symbol, settings):
            return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction="buy", valid=True, confidence=0.9)

    StrategyRegistry.register(BrokenInitStrategy, overwrite=True)
    StrategyRegistry.register(WorkingStrategy, overwrite=True)

    mock_session = AsyncMock()
    signals = await StrategyRegistry.evaluate_all(mock_session, "EURUSD", {})

    # Working strategy must still produce signal despite BrokenInitStrategy failing
    assert any(s.strategy_id == "working_strat" for s in signals)


@pytest.mark.asyncio
async def test_edge_strategy_get_historical_candles():
    """Verifies that EdgeStrategy.get_historical_candles returns formatted candles from PriceOHLCV."""
    from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
    from datetime import datetime, timezone

    class MockStrategy(EdgeStrategy):
        strategy_id = "mock_candles_strat"
        async def evaluate(self, session, symbol, settings):
            return None

    strat = MockStrategy({})
    mock_session = AsyncMock()
    mock_row = MagicMock()
    mock_row.timestamp = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    mock_row.open = 1.0850
    mock_row.high = 1.0890
    mock_row.low = 1.0830
    mock_row.close = 1.0875
    mock_row.volume = 1500.0

    mock_exec = MagicMock()
    mock_exec.scalars.return_value.all.return_value = [mock_row]
    mock_session.execute = AsyncMock(return_value=mock_exec)

    candles = await strat.get_historical_candles(mock_session, "EURUSD", "H1", limit=10)
    assert len(candles) == 1
    # Check item access
    assert candles[0]["open"] == 1.0850
    assert candles[0]["close"] == 1.0875
    assert candles[0]["volume"] == 1500.0
    # Check attribute access
    assert candles[0].high == 1.0890
    assert candles[0].low == 1.0830
    assert candles[0].close == 1.0875
    assert "2026-09-07" in candles[0]["timestamp"]


def test_candle_dict_item_and_attribute_access():
    """Verifies CandleDict acts as dict while permitting attribute access and DataFrame compatibility."""
    import pandas as pd
    from analysis.strategies.base_strategy import CandleDict

    c = CandleDict({"open": 2500.0, "high": 2520.0, "low": 2490.0, "close": 2515.0, "volume": 100.0})
    assert isinstance(c, dict)
    assert c["high"] == 2520.0
    assert c.high == 2520.0
    assert c.close == 2515.0

    # Assignment via attribute
    c.close = 2516.0
    assert c["close"] == 2516.0

    # Non-existent attribute raises AttributeError
    with pytest.raises(AttributeError):
        _ = c.nonexistent

    # DataFrame conversion works seamlessly
    df = pd.DataFrame([c])
    assert df["high"].iloc[0] == 2520.0
    assert df["close"].iloc[0] == 2516.0


@pytest.mark.asyncio
async def test_synthesized_strategies_with_candle_dict():
    """Verifies that synthesized strategies accessing c.high evaluate without 'dict' object has no attribute 'high'."""
    from analysis.strategies.base_strategy import CandleDict
    from analysis.strategies.synthesized.alpha_xauusd_96d26b import SynthesizedStrategy_alpha_xauusd_96d26b
    from analysis.strategies.synthesized.alpha_xauusd_5044bf import SynthesizedStrategy_alpha_xauusd_5044bf

    strat1 = SynthesizedStrategy_alpha_xauusd_96d26b({})
    strat2 = SynthesizedStrategy_alpha_xauusd_5044bf({})

    # Mock candles with CandleDict instances
    mock_candles = [
        CandleDict({"open": 2500.0 + i, "high": 2510.0 + i, "low": 2490.0 + i, "close": 2505.0 + i, "volume": 100.0})
        for i in range(50)
    ]

    mock_session = AsyncMock()
    with patch.object(strat1, "get_historical_candles", new_callable=AsyncMock) as mock_get_candles1:
        mock_get_candles1.return_value = mock_candles
        sig1 = await strat1.evaluate(mock_session, "XAUUSD", {})
        assert sig1 is not None

    with patch.object(strat2, "get_historical_candles", new_callable=AsyncMock) as mock_get_candles2:
        mock_get_candles2.return_value = mock_candles
        sig2 = await strat2.evaluate(mock_session, "XAUUSD", {})
        assert sig2 is not None


def test_validate_code_safety_rejects_undefined_symbols(scheduler):
    """Verifies that symtable/lint check rejects code referencing undefined variables (e.g. F821)."""
    code_with_undefined = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

class BrokenSymbolStrategy(EdgeStrategy):
    strategy_id = "broken_sym_1"
    applicable_symbols = {"EURUSD"}

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        if current_price > donchian_mid:
            return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction="buy", valid=True, confidence=0.8)
        return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0)
    """.strip()
    assert scheduler.validate_code_safety(code_with_undefined) is False


def test_validate_code_safety_accepts_utf8_characters(scheduler):
    """Verifies that validate_code_safety and ruff linting safely process code with non-ASCII UTF-8 characters."""
    code_with_utf8 = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

class Utf8Strategy(EdgeStrategy):
    \"\"\"Docstring with unicode quotes “smart”, dashes — and symbols • € 📈\"\"\"
    strategy_id = "utf8_strategy_1"
    applicable_symbols = {"EURUSD"}

    # Comment with unicode quotes “test” and math ≥ 0.5
    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction="buy", valid=True, confidence=0.8)
    """.strip()
    assert scheduler.validate_code_safety(code_with_utf8) is True


def test_validate_code_safety_rejects_missing_returns(scheduler):
    """Verifies that EdgeStrategy evaluate() without return statement is rejected."""
    code_no_return = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

class NoReturnStrategy(EdgeStrategy):
    strategy_id = "no_return_1"
    applicable_symbols = {"EURUSD"}

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        x = 1 + 1
    """.strip()
    assert scheduler.validate_code_safety(code_no_return) is False


@pytest.mark.asyncio
async def test_run_historical_simulation_disqualifies_on_eval_error(scheduler):
    """Verifies that historical simulation returns [] immediately if evaluate() raises error or returns error tags."""
    from analysis.strategies.base_strategy import EdgeStrategy
    from database.models import PriceOHLCV
    from datetime import datetime, timezone

    class ErrorRaisingStrategy(EdgeStrategy):
        strategy_id = "err_strat"
        applicable_symbols = {"EURUSD"}

        async def evaluate(self, session, symbol, settings):
            raise NameError("donchian_mid is not defined")

    mock_candles = [
        PriceOHLCV(
            symbol="EURUSD",
            timeframe="H1",
            timestamp=datetime(2026, 9, 1, i % 24, 0, tzinfo=timezone.utc),
            open=1.08,
            high=1.09,
            low=1.07,
            close=1.085,
            volume=100.0,
        )
        for i in range(100)
    ]

    with patch("scheduler.strategy_synthesis_scheduler.get_session") as mock_get_session:
        mock_session = AsyncMock()
        mock_exec = MagicMock()
        mock_exec.scalars.return_value.all.return_value = mock_candles
        mock_session.execute = AsyncMock(return_value=mock_exec)
        mock_get_session.return_value.__aenter__.return_value = mock_session

        returns = await scheduler.run_historical_simulation(ErrorRaisingStrategy, "EURUSD")
        assert returns == []


@pytest.mark.asyncio
async def test_canary_evaluation_failure_blocks_registration(scheduler):
    """Verifies that canary evaluation returning error tag blocks candidate registration."""
    code = """
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

class CanaryErrorStrategy(EdgeStrategy):
    strategy_id = "canary_err_strat"
    applicable_symbols = {"EURUSD"}

    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:
        return EdgeSignal(
            strategy_id=self.strategy_id,
            symbol=symbol,
            direction=None,
            valid=False,
            confidence=0.0,
            rationale="Calculation error",
            tags=["error"]
        )
    """.strip()

    candidate = await scheduler.evaluate_and_register_candidate(
        strategy_id="canary_err_strat",
        class_name="CanaryErrorStrategy",
        code_str=code,
        symbol="EURUSD",
        simulated_returns=[0.02, 0.03, 0.01, 0.02, 0.015],
    )
    assert candidate is None
    assert StrategyRegistry.get_strategy("canary_err_strat") is None


