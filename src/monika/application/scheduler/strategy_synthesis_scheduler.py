"""
Autonomous LLM Strategy Code Synthesis Scheduler.

Synthesizes new EdgeStrategy subclasses using LLM reasoning, compiles and validates them
in a backtesting sandbox, and registers qualified candidates meeting institutional quant
thresholds (Sharpe > 1.5, Max Drawdown < 10%).
"""

import ast
import asyncio
import builtins
import inspect
import json
import logging
import math
import re
import shutil
import subprocess
import symtable
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, cast

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from monika.application.analysis.strategies.base_strategy import EdgeSignal, EdgeStrategy
from monika.application.analysis.strategies.hypothesis_registry import HypothesisRegistry, HypothesisStatus
from monika.application.analysis.strategies.registry import StrategyRegistry
from monika.application.scheduler import synthesis_validator
from monika.infrastructure.database.db import get_session
from monika.infrastructure.database.models import ActivityLog, SystemConfig

logger = logging.getLogger("TradingAgent.StrategySynthesisScheduler")


@dataclass
class SynthesizedStrategyCandidate:
    """Metadata and backtest performance for a synthesized strategy candidate."""

    strategy_id: str
    class_name: str
    symbol: str
    python_code: str
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate_pct: float
    total_trades: int
    status: str = "QUALIFIED"  # "QUALIFIED", "REGISTERED", "REJECTED"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    file_path: Optional[str] = None
    derived_from: Optional[str] = None
    generation: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HistoricalSliceSession:
    """Proxy AsyncSession for sandbox backtesting that guarantees zero-lookahead bias."""

    def __init__(self, candle_slice: list):
        self._slice = list(candle_slice)

    async def execute(self, stmt, *args, **kwargs):
        class _SliceScalarResult:
            def __init__(self, data):
                self._data = data

            def scalars(self):
                return self

            def all(self):
                # Reverse back to descending order as expected by get_historical_candles
                return list(reversed(self._data))

            def scalar_one_or_none(self):
                return self._data[-1] if self._data else None

            def first(self):
                return self._data[-1] if self._data else None

        return _SliceScalarResult(self._slice)

    async def commit(self):
        pass

    async def rollback(self):
        pass


class StrategySynthesisScheduler:
    """
    Autonomous scheduler that synthesizes novel EdgeStrategy code,
    verifies it in a backtesting sandbox, and promotes passing strategies
    into the active StrategyRegistry.
    """

    from monika.core.paths import get_runtime_strategies_dir

    SYNTHESIZED_DIR = get_runtime_strategies_dir()

    def __init__(
        self,
        settings: dict,
        interval_hours: float = 48.0,
        min_sharpe: float = 1.5,
        max_drawdown_pct: float = 10.0,
        min_trades: int = 25,
        target_symbols: Optional[List[str]] = None,
        recovery_event: Optional[asyncio.Event] = None,
        notifier: Optional[Any] = None,
        edge_strategy_runner: Optional[Any] = None,
    ):
        self.settings = settings
        cfg = settings.get("strategy_synthesis", {}) if isinstance(settings, dict) else {}
        self.enabled = bool(cfg.get("enabled", True))
        self.interval_hours = float(cfg.get("interval_hours", interval_hours))
        self.min_sharpe = float(cfg.get("min_sharpe", min_sharpe))
        self.max_drawdown_pct = float(cfg.get("max_drawdown_pct", max_drawdown_pct))
        self.min_trades = int(cfg.get("min_trades", min_trades))
        self.target_symbols = target_symbols or cfg.get(
            "target_symbols", settings.get("trading", {}).get("asset_universe", ["EURUSD", "BTCUSD", "XAUUSD"])
        )
        self.walk_forward_enabled = bool(cfg.get("walk_forward_enabled", True))
        self.min_walk_forward_sharpe = float(cfg.get("min_walk_forward_sharpe", 1.0))
        self.min_walk_forward_efficiency = float(cfg.get("min_walk_forward_efficiency", 0.55))
        self.recovery_event = recovery_event
        self.notifier = notifier
        self.edge_strategy_runner = edge_strategy_runner
        self._running = False
        self._stop_event = asyncio.Event()
        self.candidates: List[SynthesizedStrategyCandidate] = []
        self.hypothesis_registry = HypothesisRegistry()
        self.SYNTHESIZED_DIR.mkdir(parents=True, exist_ok=True)

    # Institutional module allowlist for quantitative EdgeStrategy code
    # Institutional module allowlist & security definitions
    ALLOWED_MODULE_ROOTS = synthesis_validator.ALLOWED_MODULE_ROOTS
    ALLOWED_DUNDER_ATTRS = synthesis_validator.ALLOWED_DUNDER_ATTRS
    ALLOWED_DUNDER_NAMES = synthesis_validator.ALLOWED_DUNDER_NAMES
    DISALLOWED_CALL_NAMES = synthesis_validator.DISALLOWED_CALL_NAMES
    DISALLOWED_CALL_ATTRS = synthesis_validator.DISALLOWED_CALL_ATTRS

    @staticmethod
    def validate_code_safety(code_str: str) -> bool:
        """AST code safety validation delegated to synthesis_validator."""
        return synthesis_validator.validate_code_safety(code_str)

    @staticmethod
    def _lint_check_code(code_str: str) -> tuple[bool, str]:
        """Code lint check delegated to synthesis_validator."""
        return synthesis_validator.lint_check_code(code_str)

    @staticmethod
    def sanitize_strategy_code(code_str: str) -> str:
        """Code sanitization and AST repair delegated to synthesis_validator."""
        return synthesis_validator.sanitize_strategy_code(code_str)

    @staticmethod
    def _repair_invalid_replace_calls(code_str: str) -> str:
        """Repair invalid replace calls delegated to synthesis_validator."""
        return synthesis_validator.repair_invalid_replace_calls(code_str)

    @staticmethod
    def _repair_unclosed_delimiters(code_str: str) -> str:
        """Repair unclosed delimiters delegated to synthesis_validator."""
        return synthesis_validator.repair_unclosed_delimiters(code_str)

    @staticmethod
    def _reindent_unindented_methods(code_str: str) -> str:
        """Repair unindented methods delegated to synthesis_validator."""
        return synthesis_validator.reindent_unindented_methods(code_str)

    @staticmethod
    def _repair_unclosed_try_blocks(code_str: str) -> str:
        """Repair unclosed try blocks delegated to synthesis_validator."""
        return synthesis_validator.repair_unclosed_try_blocks(code_str)

    def compile_strategy_class(self, code_str: str, class_name: str) -> Optional[Type[EdgeStrategy]]:
        """
        Compiles sanitized code in a restricted namespace and retrieves the EdgeStrategy subclass.
        Auto-injects strategy_id, applicable_symbols, and polymorphic safe_init.
        """
        code_str = self.sanitize_strategy_code(code_str)
        if not self.validate_code_safety(code_str):
            return None

        import builtins

        safe_builtins = dict(builtins.__dict__)
        for dangerous in (
            "eval",
            "exec",
            "compile",
            "open",
            "input",
            "breakpoint",
            "globals",
            "locals",
            "getattr",
            "setattr",
            "delattr",
        ):
            safe_builtins.pop(dangerous, None)

        def safe_getattr(obj: Any, name: str, default: Any = None) -> Any:
            if not isinstance(name, str) or name.startswith("__") or name in self.DISALLOWED_CALL_ATTRS:
                raise PermissionError(f"Access to attribute '{name}' is restricted.")
            return getattr(obj, name, default)

        safe_builtins["getattr"] = safe_getattr

        real_import = builtins.__import__

        def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
            root = name.split(".")[0].strip()
            if root and root not in self.ALLOWED_MODULE_ROOTS:
                raise ImportError(f"Import of '{name}' is restricted in synthesized strategies.")
            if name == "analysis" or name.startswith("analysis."):
                name = "monika.application." + name
            return real_import(name, globals, locals, fromlist, level)

        safe_builtins["__import__"] = safe_import

        import decimal as _decimal
        import logging as _logging

        namespace: Dict[str, Any] = {
            "__builtins__": safe_builtins,
            "EdgeStrategy": EdgeStrategy,
            "EdgeSignal": EdgeSignal,
            "AsyncSession": AsyncSession,
            "select": select,
            "math": math,
            "np": np,
            "logging": _logging,
            "decimal": _decimal,
            "Optional": Optional,
            "Dict": Dict,
            "Any": Any,
            "List": List,
        }

        try:
            compiled = compile(code_str, filename="<synthesized_strategy>", mode="exec")
            exec(compiled, namespace)
            strat_cls = namespace.get(class_name)
            if not strat_cls or not isinstance(strat_cls, type) or not issubclass(strat_cls, EdgeStrategy):
                logger.warning(f"[StrategySynthesis] '{class_name}' is not a valid EdgeStrategy subclass.")
                return None

            # Resolve abstract method 'evaluate' if missing or aliased
            if getattr(strat_cls, "__abstractmethods__", None) and "evaluate" in strat_cls.__abstractmethods__:
                # 1. Check if 'evaluate' was defined at module scope in namespace
                if "evaluate" in namespace and callable(namespace["evaluate"]):
                    setattr(strat_cls, "evaluate", namespace["evaluate"])
                    strat_cls.__abstractmethods__ = strat_cls.__abstractmethods__ - {"evaluate"}

                # 2. Check known method aliases on strat_cls
                if getattr(strat_cls, "__abstractmethods__", None) and "evaluate" in strat_cls.__abstractmethods__:
                    candidate_aliases = [
                        "generate_signals",
                        "generate_signal",
                        "analyze",
                        "execute",
                        "evaluate_strategy",
                        "evaluate_symbol",
                        "evaluate_market",
                        "run",
                    ]
                    for alias in candidate_aliases:
                        if hasattr(strat_cls, alias) and callable(getattr(strat_cls, alias)):
                            setattr(strat_cls, "evaluate", getattr(strat_cls, alias))
                            strat_cls.__abstractmethods__ = strat_cls.__abstractmethods__ - {"evaluate"}
                            break

            # If still missing abstract methods, fail compilation cleanly
            if getattr(strat_cls, "__abstractmethods__", None):
                logger.warning(
                    f"[StrategySynthesis] '{class_name}' cannot be compiled: missing abstract method(s): "
                    f"{set(strat_cls.__abstractmethods__)}"
                )
                return None

            # Auto-inject default strategy_id if omitted
            if not getattr(strat_cls, "strategy_id", None):
                strat_cls.strategy_id = class_name.replace("SynthesizedStrategy_", "")

            # Auto-inject default applicable_symbols if omitted
            if not getattr(strat_cls, "applicable_symbols", None):
                strat_cls.applicable_symbols = set()

            # Auto-inject default compatible_regimes and factor_family if omitted
            if not getattr(strat_cls, "compatible_regimes", None):
                strat_cls.compatible_regimes = {"TREND", "STRONG_TREND", "RANGE", "WEAK_TREND", "VOLATILE_CHOP"}
            if not getattr(strat_cls, "factor_family", None):
                strat_cls.factor_family = "trend"

            # Polymorphic safe_init wrapper: guarantees compatibility whether called with positional settings, kwargs, or no args
            orig_init = strat_cls.__init__

            def safe_init(self, settings=None, *args, **kwargs):
                try:
                    orig_init(self, settings, *args, **kwargs)
                except TypeError:
                    kw = dict(kwargs)
                    if "settings" not in kw and settings is not None:
                        kw["settings"] = settings
                    try:
                        orig_init(self, **kw)
                    except TypeError:
                        try:
                            orig_init(self, **kwargs)
                        except TypeError:
                            orig_init(self)
                if settings is not None:
                    self.settings = settings
                elif not hasattr(self, "settings") or self.settings is None:
                    self.settings = {}

            strat_cls.__init__ = safe_init

            # Robust evaluate error boundary: prevents runtime exceptions in synthesized quant code from bubbling to evaluate_all
            orig_evaluate = strat_cls.evaluate
            import inspect

            eval_params = inspect.signature(orig_evaluate).parameters
            accepts_as_of = "as_of" in eval_params or any(
                p.kind == inspect.Parameter.VAR_KEYWORD for p in eval_params.values()
            )

            async def safe_evaluate(self, session, symbol, settings, as_of: Optional[datetime] = None):
                try:
                    if accepts_as_of:
                        res = await orig_evaluate(self, session, symbol, settings, as_of=as_of)
                    else:
                        res = await orig_evaluate(self, session, symbol, settings)
                    if res is None:
                        sid = getattr(self, "strategy_id", class_name)
                        return EdgeSignal(
                            strategy_id=sid,
                            symbol=symbol,
                            direction=None,
                            valid=False,
                            confidence=0.0,
                            rationale="Evaluation completed without returning a signal",
                            tags=["empty_signal"],
                        )
                    # Enforce signal integrity: valid=True requires direction in ('buy', 'sell')
                    if getattr(res, "valid", False) and getattr(res, "direction", None) not in ("buy", "sell"):
                        res.valid = False
                    return res
                except Exception as eval_err:
                    sid = getattr(self, "strategy_id", class_name)
                    logger.warning(f"[{sid}] evaluate runtime error for {symbol} (caught by safe_evaluate): {eval_err}")
                    return EdgeSignal(
                        strategy_id=sid,
                        symbol=symbol,
                        direction=None,
                        valid=False,
                        confidence=0.0,
                        rationale=f"Evaluation failed: {eval_err}",
                        tags=["evaluation_error"],
                    )

            setattr(strat_cls, "evaluate", safe_evaluate)
            # Explicitly clear __abstractmethods__ so ABCMeta allows clean instantiation
            strat_cls.__abstractmethods__ = frozenset()
            return strat_cls
        except Exception as e:
            logger.warning(f"[StrategySynthesis] Compilation failed for {class_name}: {e}")
            return None

    def run_backtest_sandbox(
        self,
        strategy_cls: Type[EdgeStrategy],
        symbol: str,
        simulated_returns: Optional[List[float]] = None,
    ) -> Dict[str, float]:
        """
        Tests the strategy in an institutional backtest sandbox.
        Calculates Annualized Sharpe, Max Drawdown %, Win Rate %, and Trade Count.
        """
        returns = list(simulated_returns) if simulated_returns is not None else []
        if not returns:
            return {"sharpe": 0.0, "max_drawdown_pct": 0.0, "win_rate_pct": 0.0, "trades": 0}

        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns, ddof=1)) if len(returns) > 1 else 1e-6
        ann_factor = math.sqrt(252.0)
        sharpe = round(float((mean_ret / (std_ret + 1e-9)) * ann_factor), 2)

        # Equity curve & Max Drawdown
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        wins = 0

        for r in returns:
            if r > 0:
                wins += 1
            equity *= 1.0 + r
            if equity > peak:
                peak = equity
            dd = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        win_rate_pct = round((wins / len(returns)) * 100.0, 2)

        return {
            "sharpe": sharpe,
            "max_drawdown_pct": round(max_dd, 2),
            "win_rate_pct": win_rate_pct,
            "trades": len(returns),
        }

    async def run_historical_simulation(
        self,
        strategy_cls: Type[EdgeStrategy],
        symbol: str,
        lookback_candles: int = 1500,
        min_candles: int = 60,
    ) -> List[float]:
        """
        Simulates candidate EdgeStrategy bar-by-bar across real historical PriceOHLCV candles
        using IsolatedStrategyBacktestHarness.
        Enforces zero lookahead: strategy only accesses past candles at each step.
        Applies asset-specific spread and slippage friction, dynamic ATR stops/targets,
        and multi-timeframe zero-lookahead caching.
        Returns list of real trade returns (pnl_pct as decimals).
        """
        from monika.application.backtest.isolated_strategy_harness import IsolatedStrategyBacktestHarness

        harness = IsolatedStrategyBacktestHarness(
            strategy=strategy_cls,
            symbol=symbol,
            settings=self.settings,
            fail_fast_on_error=True,
        )

        try:
            async with get_session() as session:
                metrics = await harness.run_single_window(
                    session=session,
                    lookback_candles=lookback_candles,
                    min_candles=min_candles,
                )
                return [round(t.pnl_pct / 100.0, 5) for t in metrics.trades]
        except Exception as e:
            logger.warning(f"[StrategySynthesis] Historical harness simulation error for {symbol}: {e}")
            return []

    def run_walk_forward_validation(
        self,
        strategy_cls: Type[EdgeStrategy],
        symbol: str,
        returns: Optional[List[float]] = None,
        split_ratio: float = 0.60,
    ) -> Dict[str, Any]:
        """
        Institutional Walk-Forward Validation.
        Splits returns into In-Sample (IS, 60%) and Out-Of-Sample (OOS, 40%).
        Evaluates OOS Sharpe and Walk-Forward Efficiency (WFE = OOS Sharpe / IS Sharpe).
        """
        if returns is None:
            return {
                "passed": False,
                "is_sharpe": 0.0,
                "oos_sharpe": 0.0,
                "wfe": 0.0,
                "reason": "No returns provided for walk-forward validation",
            }

        if len(returns) < 4:
            return {
                "passed": False,
                "is_sharpe": 0.0,
                "oos_sharpe": 0.0,
                "wfe": 0.0,
                "reason": f"Sample size too small ({len(returns)} < 4 trades) for walk-forward validation",
            }

        split_idx = max(2, int(len(returns) * split_ratio))
        if split_idx >= len(returns):
            split_idx = len(returns) - 1
        is_returns = returns[:split_idx]
        oos_returns = returns[split_idx:]

        is_metrics = self.run_backtest_sandbox(strategy_cls, symbol, simulated_returns=is_returns)
        oos_metrics = self.run_backtest_sandbox(strategy_cls, symbol, simulated_returns=oos_returns)

        is_sharpe = is_metrics["sharpe"]
        oos_sharpe = oos_metrics["sharpe"]

        # Institutional Pardo Walk-Forward Efficiency (WFE): Requires positive In-Sample Sharpe > 0.1
        if is_sharpe <= 0.1:
            wfe = 0.0
        else:
            wfe = round(float(max(0.0, oos_sharpe) / is_sharpe), 2)
        passed = (oos_sharpe >= self.min_walk_forward_sharpe) and (wfe >= self.min_walk_forward_efficiency)

        return {
            "passed": passed,
            "is_sharpe": is_sharpe,
            "oos_sharpe": oos_sharpe,
            "wfe": wfe,
            "is_trades": len(is_returns),
            "oos_trades": len(oos_returns),
        }

    async def synthesize_code(self, symbol: str, concept: str) -> Optional[tuple[str, str, str]]:
        """
        Synthesizes code for a new EdgeStrategy subclass.
        Returns (strategy_id, class_name, code_str).
        """
        raw_id = f"alpha_{symbol.lower()}_{uuid.uuid4().hex[:6]}"
        class_name = f"SynthesizedStrategy_{raw_id.replace('-', '_')}"

        # 1. Query latest market context (regime, approximate ATR/price level, friction profile)
        market_context_str = ""
        try:
            from monika.application.analysis.calculators.regime_classifier import classify_market_regime
            from monika.application.backtest.outcome_evaluator import ASSET_FRICTION_PROFILE

            fprofile = ASSET_FRICTION_PROFILE.get(symbol, {"spread_pips": 2.0, "pip_value": 1.0})
            async with get_session() as mkt_session:
                reg_info = await classify_market_regime(mkt_session, symbol, self.settings)
                market_context_str = (
                    f"Asset Real-World Context:\n"
                    f"- Current Market Regime: {reg_info.get('regime', 'UNKNOWN')} "
                    f"(ADX: {reg_info.get('adx', 0):.1f}, Volatility: {reg_info.get('volatility_regime', 'NORMAL')})\n"
                    f"- Friction Profile: Typical Spread={fprofile.get('spread_pips', 2.0)} pips.\n"
                )
        except Exception as mkt_err:
            logger.debug(f"[StrategySynthesis] Market context lookup non-fatal: {mkt_err}")

        # 2. Attempt LLM generation via task role
        code = None
        try:
            from monika.infrastructure.providers.llm_factory import get_client_for_task

            client = get_client_for_task("strategy_discovery", self.settings)
            prompt = (
                "You are an elite institutional quantitative trading engineer. Write a Python EdgeStrategy subclass conforming to the following specification.\n\n"
                "STRICT SKELETON (Class attributes and constructor must strictly match):\n"
                f"```python\n"
                f"from monika.application.analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal\n"
                f"from sqlalchemy.ext.asyncio import AsyncSession\n"
                f"from typing import Optional, Dict, Any, List\n"
                f"import math, numpy as np, pandas as pd, datetime, logging, decimal\n\n"
                "class <TargetClassName>(EdgeStrategy):\n"
                '    strategy_id: str = "<target_strategy_id>"\n'
                '    applicable_symbols: set = {"<target_symbol>"}\n'
                f'    compatible_regimes: set = {{"TREND", "STRONG_TREND", "RANGE", "WEAK_TREND", "VOLATILE_CHOP"}}\n'
                f"    factor_family: str = \"trend\"  # choose from 'trend', 'momentum', 'reversal', 'breakout', 'volatility'\n\n"
                f"    def __init__(self, settings: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:\n"
                f"        super().__init__(settings or {{}}, *args, **kwargs)\n"
                f"        # Define hyperparameters here\n\n"
                f"    async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:\n"
                f"        try:\n"
                f"            candles = await self.get_historical_candles(session=session, symbol=symbol, timeframe='H1', limit=100)\n"
                f"            # Compute indicators and calculate ATR/structural levels\n"
                f"            # Return EdgeSignal with directional entry, valid=True, confidence, stop_loss, and take_profit\n"
                f"            return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction='buy'|'sell'|None, valid=bool, confidence=float, stop_loss=float, take_profit=float, factor_family=self.factor_family, rationale=str, tags=list)\n"
                f"        except Exception as e:\n"
                f'            return EdgeSignal(strategy_id=self.strategy_id, symbol=symbol, direction=None, valid=False, confidence=0.0, rationale=f"Calculation error: {{e}}", tags=["error"])\n'
                f"```\n\n"
                f"STRICT SECURITY & QUANT RULES:\n"
                f"- ONLY use the allowed imports shown in the skeleton above.\n"
                f"- DO NOT import any other modules (do NOT import app, core, os, sys, subprocess, requests, edge_engine, trading_system).\n"
                f"- DO NOT use dynamic getattr(), setattr(), delattr(), eval(), or exec(). Access attributes directly with dot notation (e.g. candle.close) or dict .get().\n"
                f"- CANDLE ACCESS: get_historical_candles() returns a list of dictionaries (CandleDict). Directly use pd.DataFrame(candles) or candle['close']. NEVER use dunder attributes like .__dict__ or .__class__.\n"
                f"- PANDAS COMPATIBILITY: NEVER use .fillna(method='ffill') or .fillna(method='bfill') as the 'method' parameter is removed in pandas 2.1+. Always use .ffill() and .bfill() directly.\n"
                f"- NUMERICAL STABILITY: Always sanitize NaNs/Infs using scalar targets e.g. .replace([np.inf, -np.inf], np.nan).ffill().bfill().fillna(0.0) or min_periods=1 in rolling. NEVER pass a Series, DataFrame, or method call as the replacement value to .replace([np.inf, -np.inf], ...).\n"
                "- MANDATORY METHOD: You MUST implement 'async def evaluate(self, session: AsyncSession, symbol: str, settings: Dict[str, Any]) -> EdgeSignal:' directly inside the target strategy class.\n"
                f"- RISK CONTROL: When emitting a trade signal, calculate dynamic ATR-based or structural stop_loss and take_profit (e.g. 1.2-1.5x ATR for SL, 2.4-3.5x ATR for TP). Never leave them unspecified.\n"
                f"- ERROR RESILIENCE: Wrap indicator calculations inside evaluate() in try-except blocks and return EdgeSignal(..., valid=False, rationale=f'Calculation error: {{e}}', tags=['error']) if an unexpected exception occurs.\n"
                f"- VARIABLE COMPLETENESS: Every indicator or price variable used in conditions MUST be explicitly defined and assigned locally before being referenced.\n"
                f"- TOKEN COMPLETION: Ensure the full class definition and evaluate() method are completely closed and return an EdgeSignal. Never truncate the response.\n"
                f"- Return pure python code inside ```python ``` blocks only, no extra commentary.\n\n"
                f"[SYNTHESIS TARGET SPECIFICATION & DYNAMIC METADATA]:\n"
                f"Target Trading Symbol: {symbol}\n"
                f"Class Name: {class_name}\n"
                f'strategy_id: "{raw_id}"\n'
                f'applicable_symbols: {{"{symbol}"}}\n'
                f"Trading Concept: {concept}\n"
                f"{market_context_str}"
            )
            current_prompt = prompt
            for attempt in range(2):
                response = None
                create_msg = getattr(client, "create_message", None)
                if hasattr(client, "generate") and callable(getattr(client, "generate")):
                    response = await client.generate(current_prompt)
                elif hasattr(client, "generate_content") and callable(getattr(client, "generate_content")):
                    response = await client.generate_content(
                        system_prompt="You are an elite quantitative trading strategy engineer.",
                        user_message=current_prompt,
                    )
                elif callable(create_msg):
                    msg_call = cast(Callable[..., Any], create_msg)
                    res = msg_call(messages=[{"role": "user", "content": current_prompt}])
                    response = await res if inspect.isawaitable(res) else res

                if not response:
                    break

                content = getattr(response, "content", str(response))
                m = re.search(r"```(?:python)?\s*(.*?)(?:```|$)", content, re.DOTALL)
                if m and m.group(1).strip():
                    raw_extracted = m.group(1).strip()
                elif "```" in content:
                    raw_extracted = content.split("```")[1].strip()
                else:
                    raw_extracted = content.strip()

                sanitized = self.sanitize_strategy_code(raw_extracted)
                if not self.validate_code_safety(sanitized):
                    logger.info(
                        f"[StrategySynthesis] Code safety check failed on attempt {attempt + 1} for {symbol}. Prompting repair."
                    )
                    current_prompt = (
                        f"Your previous code violated safety policies or module allowlists.\n"
                        f"STRICT INSTRUCTION: Only use math, numpy, pandas, datetime, sqlalchemy, logging.\n"
                        f"Please rewrite the strategy class {class_name} completely:\n```python\n{sanitized}\n```"
                    )
                    continue

                strat_cls = self.compile_strategy_class(sanitized, class_name)
                if strat_cls is None:
                    logger.info(
                        f"[StrategySynthesis] Compilation failed on attempt {attempt + 1} for {symbol}. Prompting repair."
                    )
                    current_prompt = (
                        f"Your previous code failed compilation or AST parsing.\n"
                        f"Please fix syntax, indentation, and undefined variables in {class_name}:\n```python\n{sanitized}\n```"
                    )
                    continue

                try:
                    test_inst = strat_cls(self.settings)
                    if test_inst is not None:
                        # Pre-validate evaluate() on canary slice session to catch runtime calculation errors early
                        from monika.infrastructure.database.models import PriceOHLCV

                        now_dt = datetime.now(timezone.utc)
                        mock_candles = [
                            PriceOHLCV(
                                symbol=symbol,
                                timeframe="H1",
                                timestamp=now_dt - timedelta(hours=j),
                                open=1.0,
                                high=1.05,
                                low=0.95,
                                close=1.02,
                                volume=100.0,
                            )
                            for j in range(120, 0, -1)
                        ]
                        canary_session = cast(AsyncSession, HistoricalSliceSession(mock_candles))
                        canary_sig = await asyncio.wait_for(
                            test_inst.evaluate(canary_session, symbol, self.settings),
                            timeout=5.0,
                        )
                        if canary_sig and (
                            "error" in getattr(canary_sig, "tags", [])
                            or "evaluation_error" in getattr(canary_sig, "tags", [])
                        ):
                            raise RuntimeError(f"evaluate() produced error signal: {canary_sig.rationale}")

                        code = sanitized
                        logger.info(
                            f"[StrategySynthesis] Successfully synthesized viable strategy '{class_name}' on attempt {attempt + 1}."
                        )
                        break
                except Exception as canary_err:
                    logger.info(f"[StrategySynthesis] Canary error on attempt {attempt + 1} for {symbol}: {canary_err}")
                    current_prompt = (
                        f"Your strategy encountered a runtime error during validation: {canary_err}.\n"
                        f"Please fix the initialization, attribute assignments, or evaluate() indicator calculation logic in {class_name}:\n```python\n{sanitized}\n```"
                    )
        except Exception as e:
            logger.debug(f"[StrategySynthesis] LLM synthesis non-fatal fallback: {e}")

        # 2. No fallback stub generation â€” never generate uncalculated fake alpha
        if not code:
            logger.info(
                f"[StrategySynthesis] LLM did not generate viable strategy code for {symbol} ({concept}). "
                f"Skipping candidate â€” no fallback stub generated."
            )
            return None

        return raw_id, class_name, code

    async def evaluate_and_register_candidate(
        self,
        strategy_id: str,
        class_name: str,
        code_str: str,
        symbol: str,
        simulated_returns: Optional[List[float]] = None,
        concept: Optional[str] = None,
        derived_from: Optional[str] = None,
        generation: int = 0,
    ) -> Optional[SynthesizedStrategyCandidate]:
        """
        Compiles the candidate, runs sandbox backtest, and if Sharpe > 1.5 and Max DD < 10%,
        registers into StrategyRegistry and saves to disk / DB SystemConfig.
        """
        thesis = concept or f"Synthesized strategy {strategy_id} on {symbol}"
        hyp = self.hypothesis_registry.register(
            thesis=thesis,
            signal_definition=f"{class_name} generated for {symbol}",
            target_universe=[symbol],
            timeframe="H1",
            derived_from=derived_from,
            generation=generation,
        )
        self.hypothesis_registry.update_status(hyp.hypothesis_id, HypothesisStatus.TESTING)

        code_str = self.sanitize_strategy_code(code_str)
        strat_cls = self.compile_strategy_class(code_str, class_name)
        if not strat_cls:
            self.hypothesis_registry.update_status(
                hyp.hypothesis_id,
                HypothesisStatus.REJECTED,
                invalidation_notes="Failed code compilation or syntax validation",
            )
            return None

        # Canary instantiation and evaluation test before backtesting or registering
        try:
            test_instance = strat_cls(self.settings)
            assert test_instance is not None
            # Execute canary evaluate on dummy slice session to ensure runtime stability
            import datetime

            from monika.infrastructure.database.models import PriceOHLCV

            now_dt = datetime.datetime.now(datetime.timezone.utc)
            mock_candles = [
                PriceOHLCV(
                    symbol=symbol,
                    timeframe="H1",
                    timestamp=now_dt - datetime.timedelta(hours=j),
                    open=1.0,
                    high=1.05,
                    low=0.95,
                    close=1.02,
                    volume=100.0,
                )
                for j in range(120, 0, -1)
            ]
            canary_session = cast(AsyncSession, HistoricalSliceSession(mock_candles))
            try:
                canary_sig = await asyncio.wait_for(
                    test_instance.evaluate(canary_session, symbol, self.settings),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                logger.warning(f"[StrategySynthesis] Canary evaluation timed out (> 5.0s) for {class_name}")
                self.hypothesis_registry.update_status(
                    hyp.hypothesis_id,
                    HypothesisStatus.REJECTED,
                    invalidation_notes=f"Canary evaluation timed out (> 5.0s)",
                )
                return None
            if canary_sig is not None:
                if not isinstance(canary_sig, EdgeSignal):
                    logger.warning(
                        f"[StrategySynthesis] Canary evaluation returned non-EdgeSignal for {class_name}: {type(canary_sig)}"
                    )
                    self.hypothesis_registry.update_status(
                        hyp.hypothesis_id,
                        HypothesisStatus.REJECTED,
                        invalidation_notes=f"Canary evaluation returned non-EdgeSignal: {type(canary_sig)}",
                    )
                    return None
                if "error" in getattr(canary_sig, "tags", []) or "evaluation_error" in getattr(canary_sig, "tags", []):
                    logger.warning(
                        f"[StrategySynthesis] Canary evaluation produced error signal for {class_name}: {canary_sig.rationale}"
                    )
                    self.hypothesis_registry.update_status(
                        hyp.hypothesis_id,
                        HypothesisStatus.REJECTED,
                        invalidation_notes=f"Canary evaluation produced error signal: {canary_sig.rationale}",
                    )
                    return None
                if getattr(canary_sig, "valid", False) and getattr(canary_sig, "direction", None) not in (
                    "buy",
                    "sell",
                ):
                    logger.warning(
                        f"[StrategySynthesis] Canary evaluation valid=True without directional bias ('buy'/'sell') for {class_name}"
                    )
                    self.hypothesis_registry.update_status(
                        hyp.hypothesis_id,
                        HypothesisStatus.REJECTED,
                        invalidation_notes="Canary evaluation valid=True without directional bias ('buy'/'sell')",
                    )
                    return None
        except Exception as canary_err:
            logger.warning(f"[StrategySynthesis] Canary check failed for {class_name}: {canary_err}")
            self.hypothesis_registry.update_status(
                hyp.hypothesis_id,
                HypothesisStatus.REJECTED,
                invalidation_notes=f"Canary check failed: {canary_err}",
            )
            return None

        # Obtain trade returns: from simulated_returns if provided (unit tests),
        # otherwise from real institutional historical simulation across PriceOHLCV candles.
        if simulated_returns is not None:
            returns = list(simulated_returns)
        else:
            returns = await self.run_historical_simulation(strat_cls, symbol)

        metrics = self.run_backtest_sandbox(strat_cls, symbol, simulated_returns=returns)
        sharpe = metrics["sharpe"]
        max_dd = metrics["max_drawdown_pct"]
        trades = int(metrics["trades"])
        win_rate = metrics["win_rate_pct"]

        meets_criteria = sharpe >= self.min_sharpe and max_dd <= self.max_drawdown_pct and trades >= self.min_trades

        logger.info(
            f"[StrategySynthesis] Candidate '{strategy_id}' on {symbol}: "
            f"Sharpe={sharpe:.2f} (min {self.min_sharpe}), MaxDD={max_dd:.1f}% (max {self.max_drawdown_pct}%), "
            f"Trades={trades} -> {'QUALIFIED' if meets_criteria else 'REJECTED'}"
        )

        if not meets_criteria:
            self.hypothesis_registry.update_status(
                hyp.hypothesis_id,
                HypothesisStatus.REJECTED,
                invalidation_notes=(
                    f"Threshold failure: Sharpe={sharpe:.2f} (min {self.min_sharpe}), "
                    f"MaxDD={max_dd:.1f}% (max {self.max_drawdown_pct}%), "
                    f"Trades={trades} (min {self.min_trades})"
                ),
                metrics={"sharpe": sharpe, "max_drawdown_pct": max_dd, "trades": trades, "win_rate": win_rate},
            )
            return None

        # Walk-Forward Gating before activation
        if self.walk_forward_enabled:
            if simulated_returns is not None:
                wf_res = self.run_walk_forward_validation(strat_cls, symbol, returns=returns)
            else:
                from monika.application.backtest.isolated_strategy_harness import IsolatedStrategyBacktestHarness

                harness = IsolatedStrategyBacktestHarness(
                    strategy=strat_cls,
                    symbol=symbol,
                    settings=self.settings,
                    fail_fast_on_error=True,
                )
                try:
                    async with get_session() as session:
                        wf_res = await harness.run_walk_forward(
                            session=session,
                            n_folds=4,
                            is_ratio=0.65,
                            total_candles=1500,
                            min_candles=60,
                            trial_counter=10,
                        )
                except Exception as wf_err:
                    logger.warning(f"[StrategySynthesis] Walk-Forward validation failed for {strategy_id}: {wf_err}")
                    wf_res = {"passed": False, "reason": str(wf_err)}

            if not wf_res.get("passed", False):
                reason = (
                    f"Rejected by Walk-Forward Gating: "
                    f"OOS Sharpe={wf_res.get('oos_sharpe', wf_res.get('aggregate_oos_sharpe', 0.0)):.2f}, "
                    f"WFE={wf_res.get('wfe', wf_res.get('overall_wfe', 0.0)):.2f}"
                )
                logger.info(f"[StrategySynthesis] Candidate '{strategy_id}' {reason}")
                metrics_summary = {k: v for k, v in wf_res.items() if k != "all_oos_trades"}
                self.hypothesis_registry.update_status(
                    hyp.hypothesis_id,
                    HypothesisStatus.REJECTED,
                    invalidation_notes=reason,
                    metrics=metrics_summary,
                )
                return None
            logger.info(
                f"[StrategySynthesis] Candidate '{strategy_id}' passed Walk-Forward Gating: "
                f"OOS Sharpe={wf_res.get('oos_sharpe', wf_res.get('aggregate_oos_sharpe', 0.0)):.2f}, "
                f"WFE={wf_res.get('wfe', wf_res.get('overall_wfe', 0.0)):.2f}"
            )

        # Transition hypothesis status to INCUBATING upon passing all gates
        self.hypothesis_registry.update_status(
            hyp.hypothesis_id,
            HypothesisStatus.INCUBATING,
            metrics={
                "sharpe": sharpe,
                "max_drawdown_pct": max_dd,
                "win_rate": win_rate,
                "trades": trades,
                "strategy_id": strategy_id,
            },
        )

        # Persist to disk and verify integrity
        file_path = self.SYNTHESIZED_DIR / f"{strategy_id}.py"
        try:
            formatted_code = code_str
            try:
                import subprocess
                import sys

                res = await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, "-m", "ruff", "format", "-"],
                    input=code_str,
                    text=True,
                    capture_output=True,
                    timeout=5,
                )
                if res.returncode == 0 and res.stdout:
                    formatted_code = res.stdout
            except Exception as fe:
                logger.debug(f"[StrategySynthesis] Ruff formatting skipped for {strategy_id}: {fe}")

            from monika.core.paths import atomic_write_text

            atomic_write_text(file_path, formatted_code, encoding="utf-8")
            lint_ok, lint_err = await asyncio.to_thread(self._lint_check_code, formatted_code)
            if not lint_ok:
                logger.error(f"[StrategySynthesis] Post-write lint verification failed for {strategy_id}: {lint_err}")
                if file_path.exists():
                    file_path.unlink()
                return None
        except Exception as e:
            logger.warning(f"[StrategySynthesis] Failed writing code to disk: {e}")
            return None

        # Register in StrategyRegistry
        try:
            StrategyRegistry.register(strat_cls, overwrite=True)
            logger.info(f"[StrategySynthesis] Promoted and registered strategy: {strategy_id}")
            if self.edge_strategy_runner and hasattr(self.edge_strategy_runner, "hot_reload_strategy"):
                self.edge_strategy_runner.hot_reload_strategy(strategy_id, {})
                logger.info(f"[StrategySynthesis] Hot-reloaded strategy '{strategy_id}' into EdgeStrategyRunner")
        except Exception as e:
            logger.warning(f"[StrategySynthesis] Registry registration error: {e}")

        candidate = SynthesizedStrategyCandidate(
            strategy_id=strategy_id,
            class_name=class_name,
            symbol=symbol,
            python_code=code_str,
            sharpe_ratio=sharpe,
            max_drawdown_pct=max_dd,
            win_rate_pct=win_rate,
            total_trades=trades,
            status="REGISTERED",
            file_path=str(file_path),
            derived_from=derived_from,
            generation=generation,
        )
        self.candidates.append(candidate)

        # Dual-persist into DB SystemConfig and ActivityLog
        await self._persist_candidate(candidate)

        return candidate

    async def _persist_candidate(self, candidate: SynthesizedStrategyCandidate) -> None:
        """Persists synthesized candidate into DB SystemConfig and ActivityLog."""
        try:
            async with get_session() as session:
                config_key = f"synthesized_strategy_{candidate.strategy_id}"
                config_val = json.dumps(candidate.to_dict())

                existing = (
                    await session.execute(select(SystemConfig).where(SystemConfig.key == config_key))
                ).scalar_one_or_none()

                if existing:
                    await session.execute(
                        update(SystemConfig).where(SystemConfig.key == config_key).values(value=config_val)
                    )
                else:
                    session.add(SystemConfig(key=config_key, value=config_val))

                # Register into StrategyDecayMonitor as incubating
                try:
                    from monika.application.analysis.strategies.decay_monitor import get_strategy_decay_monitor

                    decay_mon = get_strategy_decay_monitor()
                    decay_mon.register_incubating_strategy(candidate.strategy_id)
                    await decay_mon.save_to_db(session)
                    logger.info(
                        f"[StrategySynthesis] Registered '{candidate.strategy_id}' as incubating "
                        f"(requires {decay_mon.MIN_INCUBATION_TRADES} paper trades before live execution)."
                    )
                except Exception as d_err:
                    logger.debug(
                        f"[StrategySynthesis] Failed to register incubating strategy in decay monitor: {d_err}"
                    )

                session.add(
                    ActivityLog(
                        category="strategy",
                        description=(
                            f"Autonomous Strategy Synthesized & Deployed [INCUBATING]: {candidate.strategy_id} "
                            f"Sharpe={candidate.sharpe_ratio:.2f}, MaxDD={candidate.max_drawdown_pct:.1f}%, "
                            f"WR={candidate.win_rate_pct:.1f}%"
                        ),
                        actor="strategy_synthesis_scheduler",
                        related_id=None,
                    )
                )
                await session.commit()
                logger.info(f"[StrategySynthesis] Persisted strategy {candidate.strategy_id} to DB.")

            # Notify operator if notifier is available
            if self.notifier and hasattr(self.notifier, "send_info"):
                from monika.application.analysis.strategies.decay_monitor import StrategyDecayMonitor

                incubation_trades = getattr(StrategyDecayMonitor, "MIN_INCUBATION_TRADES", 15)
                await self.notifier.send_info(
                    f"[CATATAN] <b>Autonomous Strategy Synthesized & Deployed!</b>\n"
                    f"<b>ID:</b> <code>{candidate.strategy_id}</code>\n"
                    f"<b>Status:</b>  <b>INCUBATING (PAPER TRADING)</b>\n"
                    f"<b>Symbol:</b> {candidate.symbol}\n"
                    f"<b>Sharpe:</b> <code>{candidate.sharpe_ratio:.2f}</code> (Target &gt;= {self.min_sharpe})\n"
                    f"<b>Max Drawdown:</b> <code>{candidate.max_drawdown_pct:.1f}%</code> (Limit &lt;= {self.max_drawdown_pct}%)\n"
                    f"<b>Win Rate:</b> <code>{candidate.win_rate_pct:.1f}%</code> ({candidate.total_trades} trades)\n"
                    f"Registered into StrategyRegistry for paper incubation (min {incubation_trades} paper trades before live execution)."
                )
        except Exception as e:
            logger.warning(f"[StrategySynthesis] Failed persisting candidate {candidate.strategy_id}: {e}")

    async def run_synthesis_cycle(self) -> List[SynthesizedStrategyCandidate]:
        """Runs one synthesis cycle across target symbols."""
        logger.info("[StrategySynthesis] Starting autonomous strategy synthesis cycle...")
        new_promoted = []

        cfg_concepts = self.settings.get("strategy_synthesis", {}).get("concepts")
        concepts = (
            cfg_concepts
            if isinstance(cfg_concepts, list) and cfg_concepts
            else [
                "Mean reversion on ATR exhaustion",
                "Multi-timeframe liquidity sweep displacement",
                "Volume-weighted dynamic Donchian expansion",
                "Momentum pullback with volatility band compression",
                "Order flow imbalance structural break",
            ]
        )

        for sym in self.target_symbols:
            for concept in concepts:
                try:
                    # Deduplication & rejection check in hypothesis registry
                    is_dup, dup_reason = self.hypothesis_registry.is_duplicate_or_rejected(concept)
                    if is_dup:
                        logger.info(f"[StrategySynthesis] Concept skipped for {sym} (duplicate/rejected): {dup_reason}")
                        continue

                    res = await self.synthesize_code(sym, concept)
                    if not res:
                        continue
                    strat_id, class_name, code = res
                    cand = await self.evaluate_and_register_candidate(strat_id, class_name, code, sym, concept=concept)
                    if cand:
                        new_promoted.append(cand)
                except Exception as e:
                    logger.warning(f"[StrategySynthesis] Synthesis step failed for {sym}: {e}")

        logger.info(f"[StrategySynthesis] Cycle complete. {len(new_promoted)} new strategies registered.")
        return new_promoted

    async def start(self) -> None:
        """Main autonomous scheduler loop."""
        if not self.enabled:
            logger.info("StrategySynthesisScheduler is disabled via configuration.")
            return
        self._running = True
        logger.info(f"StrategySynthesisScheduler started (interval: {self.interval_hours}h)")

        if self.recovery_event:
            try:
                await asyncio.wait_for(self.recovery_event.wait(), timeout=120.0)
                logger.info("StrategySynthesisScheduler: Recovery complete, ready to operate.")
            except asyncio.TimeoutError:
                logger.debug("StrategySynthesisScheduler: Recovery wait timed out (120s), proceeding.")

        startup_delay = (
            float(self.settings.get("strategy_synthesis", {}).get("startup_delay_seconds", 90.0))
            if isinstance(self.settings, dict)
            else 90.0
        )
        if startup_delay > 0:
            logger.info(f"StrategySynthesisScheduler: Waiting {startup_delay:.0f}s before first synthesis cycle...")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=startup_delay)
                return
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                return

        while self._running:
            try:
                await self.run_synthesis_cycle()
            except Exception as e:
                logger.error(f"StrategySynthesisScheduler cycle error: {e}", exc_info=True)

            sleep_seconds = self.interval_hours * 3600
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=sleep_seconds)
                break
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        logger.info("StrategySynthesisScheduler stopped.")
