import inspect
import json
import logging
import math
import time
from pathlib import Path
from typing import Any, Dict, Optional, Type

from sqlalchemy import delete, select, update

from monika.application.analysis.strategies.base_strategy import EdgeSignal, EdgeStrategy
from monika.infrastructure.database.models import SystemConfig

logger = logging.getLogger("TradingAgent.StrategyRegistry")


class StrategyRegistry:
    _registry: dict[str, Type[EdgeStrategy]] = {}
    _dynamic_params: dict[str, dict] = {}
    _dynamic_symbol_params: dict[tuple[str, str], dict] = {}
    _blacklisted_ids: set[str] = set()
    QUARANTINED_STRATEGY_IDS: set[str] = {"smc_fvg", "btc_donchian_breakout"}
    _last_load_time: float = 0.0
    _load_interval: float = 60.0
    MAX_SYNTHESIZED_PER_SYMBOL: int = 5
    SYNTHESIZED_DIR: Path = Path(__file__).resolve().parent / "synthesized"

    @classmethod
    def register(cls, strategy_cls: Type[EdgeStrategy], overwrite: bool = True) -> Type[EdgeStrategy]:
        if strategy_cls.strategy_id in cls._registry and not overwrite:
            raise ValueError(f"Duplicate strategy_id: {strategy_cls.strategy_id}")
        cls._registry[strategy_cls.strategy_id] = strategy_cls
        logger.debug(f"[StrategyRegistry] Registered strategy: {strategy_cls.strategy_id}")
        return strategy_cls

    @classmethod
    def get_strategy_counts(cls) -> tuple[int, dict[str, int]]:
        """Returns total registered count and count per instrument."""
        counts: dict[str, int] = {}
        for strat_cls in cls._registry.values():
            symbols = getattr(strat_cls, "applicable_symbols", set())
            if isinstance(symbols, (set, list, tuple)) and symbols:
                for sym in symbols:
                    sym_upper = str(sym).upper()
                    counts[sym_upper] = counts.get(sym_upper, 0) + 1
            else:
                strat_id = getattr(strat_cls, "strategy_id", "")
                parts = strat_id.split("_")
                if len(parts) >= 3 and parts[0] == "alpha":
                    sym_upper = parts[1].upper()
                    counts[sym_upper] = counts.get(sym_upper, 0) + 1
                else:
                    counts["GLOBAL"] = counts.get("GLOBAL", 0) + 1
        sorted_counts = dict(sorted(counts.items(), key=lambda x: (-x[1], x[0])))
        return len(cls._registry), sorted_counts

    @classmethod
    def log_summary(cls) -> None:
        """Logs concise summary of registered strategies: total and per instrument."""
        total, counts = cls.get_strategy_counts()
        if total == 0:
            logger.info("[StrategyRegistry] Registered strategies: 0")
            return
        details = ", ".join(f"{k}: {v}" for k, v in counts.items())
        logger.info(f"[StrategyRegistry] Registered {total} strategies total across instruments: {details}")

    @classmethod
    def get_strategy(cls, strategy_id: str) -> Optional[Type[EdgeStrategy]]:
        return cls._registry.get(strategy_id)

    @classmethod
    def get(cls, strategy_id: str) -> Optional[Type[EdgeStrategy]]:
        return cls._registry.get(strategy_id)

    @classmethod
    def list_strategies(cls) -> list[str]:
        return list(cls._registry.keys())

    @classmethod
    def _validate_dynamic_params(cls, parameters: dict) -> dict:
        """Validates parameter boundaries before dynamic override injection."""
        valid: dict[str, Any] = {}
        for k, v in parameters.items():
            if isinstance(v, (int, float)):
                if math.isnan(v) or math.isinf(v):
                    logger.warning(f"[StrategyRegistry] Discarded invalid param '{k}'={v} (NaN/Inf)")
                    continue
                k_lower = str(k).lower()
                if any(k_lower.endswith(s) for s in ("_period", "_window", "_lookback", "_length", "_bars")) and v <= 0:
                    logger.warning(f"[StrategyRegistry] Discarded non-positive period '{k}'={v}")
                    continue
                if any(k_lower.endswith(s) for s in ("_mult", "_multiplier", "_threshold", "_std")) and v < 0:
                    logger.warning(f"[StrategyRegistry] Discarded negative multiplier '{k}'={v}")
                    continue
            valid[k] = v
        return valid

    @classmethod
    def _apply_dynamic_params_to_strategy(cls, strat: Any, dyn_params: dict) -> None:
        """Applies dynamic parameter overrides to both strat.cfg and instance attributes."""
        if not dyn_params:
            return
        strat.cfg = dict(getattr(strat, "cfg", {}))
        strat.cfg.update(dyn_params)
        for k, v in dyn_params.items():
            if hasattr(strat, k):
                try:
                    setattr(strat, k, v)
                except Exception as attr_err:
                    logger.debug(f"[StrategyRegistry] Failed setting attribute {k} on strategy: {attr_err}")
        if hasattr(strat, "set_parameters") and callable(getattr(strat, "set_parameters")):
            try:
                strat.set_parameters(dyn_params)
            except Exception as set_err:
                logger.debug(f"[StrategyRegistry] set_parameters hook failed: {set_err}")

    @classmethod
    def hot_reload(cls, strategy_id: str, parameters: dict, symbol: Optional[str] = None) -> None:
        """Hot-reloads dynamic parameter overrides for a specific strategy into active memory."""
        if not isinstance(parameters, dict):
            return
        sanitized = cls._validate_dynamic_params(parameters)
        if not sanitized:
            return
        if symbol:
            cls._dynamic_symbol_params.setdefault((strategy_id, symbol.upper()), {}).update(sanitized)
        cls._dynamic_params.setdefault(strategy_id, {}).update(sanitized)
        target = f"'{strategy_id}' on {symbol.upper()}" if symbol else f"'{strategy_id}'"
        logger.info(f"[StrategyRegistry] Hot-reloaded dynamic parameters for {target}: {sanitized}")

    @classmethod
    async def load_dynamic_parameters(cls, session) -> dict[str, dict]:
        """
        Loads dynamic strategy parameters and promoted candidate alpha parameters
        directly from PostgreSQL SystemConfig into active registry memory.
        Also loads and compiles synthesized strategies if not yet registered.
        """
        try:

            async def _safe_scalars(stmt):
                res = await session.execute(stmt)
                if hasattr(res, "scalars"):
                    sc = res.scalars()
                    if hasattr(sc, "__await__"):
                        sc = await sc
                    if hasattr(sc, "all"):
                        rows = sc.all()
                        if hasattr(rows, "__await__"):
                            rows = await rows
                        return rows if isinstance(rows, (list, tuple)) else []
                return []

            # 1. Load direct strategy parameter overrides (key: strategy_params_<strat_id> or strategy_params_<strat_id>_<sym>)
            stmt_params = select(SystemConfig).where(SystemConfig.key.like("strategy_params_%"))
            rows_params = await _safe_scalars(stmt_params)
            for r in rows_params:
                if not r or not getattr(r, "key", None) or not getattr(r, "value", None):
                    continue
                raw_key = r.key.replace("strategy_params_", "")
                sym = None
                strat_id = raw_key
                parts = raw_key.rsplit("_", 1)
                if len(parts) == 2 and len(parts[1]) in (6, 7) and parts[1].isupper():
                    strat_id = parts[0]
                    sym = parts[1]

                try:
                    p_data = json.loads(r.value)
                    if isinstance(p_data, dict):
                        cls.hot_reload(strat_id, p_data, symbol=sym)
                except Exception as parse_err:
                    logger.debug(f"[StrategyRegistry] Failed parsing params for {raw_key}: {parse_err}")

            # 2. Load promoted candidate alpha proposals with PAPER_ACTIVE or ACCEPTED status
            stmt_alphas = select(SystemConfig).where(SystemConfig.key.like("candidate_alpha_%"))
            rows_alphas = await _safe_scalars(stmt_alphas)
            for r in rows_alphas:
                if not r or not getattr(r, "value", None):
                    continue
                try:
                    prop_data = json.loads(r.value)
                    status = prop_data.get("status", "")
                    if status in ("PAPER_ACTIVE", "ACCEPTED", "DEPLOYED"):
                        hyp = prop_data.get("hypothesis", {})
                        strat_type = hyp.get("strategy_type", "")
                        sym = hyp.get("symbol", "")
                        params = hyp.get("parameters", {})
                        if strat_type and params:
                            cls.hot_reload(strat_type, params, symbol=sym or None)
                except Exception as prop_err:
                    logger.debug(f"[StrategyRegistry] Failed loading candidate alpha proposal: {prop_err}")

            # 3. Load StrategyDecayMonitor state first to evaluate live operational health
            decay_mon = None
            try:
                from monika.application.analysis.strategies.decay_monitor import get_strategy_decay_monitor

                decay_mon = get_strategy_decay_monitor()
                await decay_mon.load_from_db(session)
            except Exception as decay_err:
                logger.debug(f"[StrategyRegistry] Early decay monitor load non-fatal: {decay_err}")

            # 4. Load registered synthesized strategies with per-instrument dynamic health quota limit
            stmt_synths = select(SystemConfig).where(SystemConfig.key.like("synthesized_strategy_%"))
            rows_synths = await _safe_scalars(stmt_synths)
            loaded_synths_count = 0
            symbol_active_synths: dict[str, int] = {}

            # Sort candidate rows by dynamic health status and Sharpe ratio descending
            parsed_synths = []
            for r in rows_synths:
                if not r or not getattr(r, "value", None):
                    continue
                try:
                    s_data = json.loads(r.value)
                    s_id = s_data.get("strategy_id", "")
                    health_status = "HEALTHY"
                    if decay_mon and s_id:
                        h = decay_mon.get_health(s_id)
                        health_status = getattr(h.state, "value", "healthy").upper()

                    # Penalize degraded and ignore disabled from quota priority
                    health_score = 100.0
                    if health_status in ("DISABLED", "HALTED", "REJECTED"):
                        health_score = -1000.0
                    elif health_status == "DEGRADED":
                        health_score = -50.0
                    elif health_status == "INCUBATING":
                        health_score = 50.0

                    base_sharpe = float(s_data.get("sharpe_ratio", 0.0) or 0.0)
                    total_rank = health_score + base_sharpe
                    parsed_synths.append((total_rank, health_status, s_data))
                except Exception:
                    continue
            parsed_synths.sort(key=lambda x: x[0], reverse=True)

            for _, h_stat, s_data in parsed_synths:
                try:
                    s_id = s_data.get("strategy_id")
                    sym = str(s_data.get("symbol", "")).upper()
                    if not s_id or s_id in cls._registry or s_id in cls._blacklisted_ids:
                        continue

                    # Guard: do not resurrect quarantined strategies
                    from monika.core.paths import get_repo_root

                    quarantine_file = get_repo_root() / "archive" / "strategies" / "quarantine" / f"{s_id}.py"
                    if quarantine_file.exists() or s_data.get("is_quarantined", False):
                        logger.debug(f"[StrategyRegistry] Skipping {s_id}: strategy is quarantined.")
                        continue

                    # Skip strategies permanently disabled by decay monitor
                    if h_stat in ("DISABLED", "HALTED", "REJECTED"):
                        logger.debug(f"[StrategyRegistry] Skipping {s_id}: decay status is {h_stat}")
                        continue

                    if sym and symbol_active_synths.get(sym, 0) >= cls.MAX_SYNTHESIZED_PER_SYMBOL:
                        logger.debug(
                            f"[StrategyRegistry] Quota reached for {sym} ({cls.MAX_SYNTHESIZED_PER_SYMBOL}), skipping {s_id}"
                        )
                        continue

                    py_code = s_data.get("python_code")
                    cls_name = s_data.get("class_name")
                    if s_id and py_code and cls_name:
                        # Reject stub templates and mock strategies with hardcoded static signals
                        is_stub = (
                            s_id.lower().startswith("mock")
                            or cls_name.lower().startswith("mock")
                            or (
                                ('direction="buy"' in py_code or "direction='buy'" in py_code)
                                and ("confidence=0.8" in py_code)
                            )
                        )
                        if is_stub:
                            cls._blacklisted_ids.add(s_id)
                            logger.info(
                                f"[StrategyRegistry] Skipping and purging blacklisted stub/mock strategy: {s_id}"
                            )
                            if hasattr(session, "execute"):
                                try:
                                    del_stmt = delete(SystemConfig).where(
                                        SystemConfig.key == f"synthesized_strategy_{s_id}"
                                    )
                                    res_del = session.execute(del_stmt)
                                    if inspect.isawaitable(res_del):
                                        res_del = await res_del
                                    if hasattr(session, "commit"):
                                        res_com = session.commit()
                                        if inspect.isawaitable(res_com):
                                            await res_com
                                except Exception as purge_err:
                                    logger.debug(f"[StrategyRegistry] Failed purging stub {s_id} from DB: {purge_err}")
                            continue
                        from monika.application.scheduler.strategy_synthesis_scheduler import StrategySynthesisScheduler

                        synth_sched = StrategySynthesisScheduler({})
                        loaded_cls = synth_sched.compile_strategy_class(py_code, cls_name)
                        if loaded_cls:
                            cls.register(loaded_cls, overwrite=True)
                            loaded_synths_count += 1
                            if sym:
                                symbol_active_synths[sym] = symbol_active_synths.get(sym, 0) + 1
                        else:
                            # Self-healing fallback: Check if a valid version exists on disk
                            disk_path = cls.SYNTHESIZED_DIR / f"{s_id}.py"
                            healed = False
                            if disk_path.exists():
                                try:
                                    disk_code = disk_path.read_text(encoding="utf-8")
                                    disk_cls = synth_sched.compile_strategy_class(disk_code, cls_name)
                                    if disk_cls:
                                        cls.register(disk_cls, overwrite=True)
                                        loaded_synths_count += 1
                                        if sym:
                                            symbol_active_synths[sym] = symbol_active_synths.get(sym, 0) + 1
                                        healed = True
                                        logger.info(
                                            f"[StrategyRegistry] Self-healed strategy '{s_id}' from disk version."
                                        )
                                        if hasattr(session, "execute"):
                                            s_data["python_code"] = disk_code
                                            upd_stmt = (
                                                update(SystemConfig)
                                                .where(SystemConfig.key == f"synthesized_strategy_{s_id}")
                                                .values(value=json.dumps(s_data))
                                            )
                                            res_upd = session.execute(upd_stmt)
                                            if inspect.isawaitable(res_upd):
                                                await res_upd
                                            if hasattr(session, "commit"):
                                                res_c = session.commit()
                                                if inspect.isawaitable(res_c):
                                                    await res_c
                                except Exception as heal_err:
                                    logger.debug(
                                        f"[StrategyRegistry] Disk self-healing attempt failed for {s_id}: {heal_err}"
                                    )
                            if not healed:
                                cls._blacklisted_ids.add(s_id)
                                logger.warning(
                                    f"[StrategyRegistry] Quarantined corrupted synthesized strategy '{s_id}': compilation failed."
                                )
                except Exception as synth_err:
                    logger.debug(f"[StrategyRegistry] Failed restoring synthesized strategy: {synth_err}")

            # 4. Load persisted strategy decay monitor state
            try:
                from monika.application.analysis.strategies.decay_monitor import get_strategy_decay_monitor

                await get_strategy_decay_monitor().load_from_db(session)
            except Exception as decay_err:
                logger.debug(f"[StrategyRegistry] Failed loading decay state: {decay_err}")

            if loaded_synths_count > 0:
                cls.log_summary()

        except Exception as e:
            logger.warning(f"[StrategyRegistry] load_dynamic_parameters non-fatal error: {e}")

        return dict(cls._dynamic_params)

    @classmethod
    async def evaluate_all(
        cls,
        session,
        symbol: str,
        settings: dict,
        force_reload: bool = False,
        current_regime: Optional[str] = None,
        as_of: Optional[Any] = None,
    ) -> list[EdgeSignal]:
        # Optionally load or sync dynamic params if session is available (throttled to avoid DB storms)
        if session and hasattr(session, "execute"):
            now_ts = time.time()
            if force_reload or (now_ts - cls._last_load_time >= cls._load_interval):
                try:
                    await cls.load_dynamic_parameters(session)
                    cls._last_load_time = now_ts
                except Exception as e:
                    logger.debug(f"[StrategyRegistry] dynamic param check during evaluate_all non-fatal: {e}")

        out = []
        for strat_cls in list(cls._registry.values()):
            strat_name = getattr(strat_cls, "strategy_id", getattr(strat_cls, "__name__", "unknown"))
            try:
                strat = None
                # Resilient instantiation hierarchy (positional -> kwargs -> no-args)
                if callable(strat_cls):
                    try:
                        strat = strat_cls(settings)
                    except TypeError:
                        try:
                            strat = strat_cls(**(settings if isinstance(settings, dict) else {}))
                        except TypeError:
                            strat = strat_cls()
                else:
                    strat = strat_cls

                if strat is None:
                    continue

                strat_id = getattr(strat, "strategy_id", None) or strat_name

                if strat_id in cls.QUARANTINED_STRATEGY_IDS or strat_id in cls._blacklisted_ids:
                    logger.debug(f"[{strat_name}] Suppressed: Quarantined due to empirical negative expectancy.")
                    continue

                # Apply dynamic parameter overrides from DB SystemConfig / hot-reload
                dyn_p = dict(cls._dynamic_params.get(strat_id, {}))
                sym_key = (strat_id, symbol.upper())
                if sym_key in cls._dynamic_symbol_params:
                    dyn_p.update(cls._dynamic_symbol_params[sym_key])
                if dyn_p:
                    cls._apply_dynamic_params_to_strategy(strat, dyn_p)

                if not strat.is_enabled(symbol):
                    continue

                # Regime compatibility check
                if current_regime and hasattr(strat, "is_regime_compatible"):
                    if not strat.is_regime_compatible(current_regime):
                        logger.debug(f"[{strat_name}] Suppressed: incompatible with current regime '{current_regime}'")
                        continue

                from monika.application.analysis.strategies.decay_monitor import get_strategy_decay_monitor

                decay_mon = get_strategy_decay_monitor()
                if not decay_mon.is_tradeable(strat_id):
                    logger.debug(
                        f"[{strat_name}] Suppressed by StrategyDecayMonitor "
                        f"(state={decay_mon.get_health(strat_id).state.value})"
                    )
                    continue

                sig = await strat.evaluate(session, symbol, settings)
                if sig is not None and not isinstance(sig, EdgeSignal):
                    logger.warning(
                        f"[{strat_name}] evaluate returned non-EdgeSignal ({type(sig)}) for {symbol}, discarding"
                    )
                    continue
                if sig and sig.valid:
                    # Guard against static uncalculated synthesized stub signals and mocks
                    if strat_id.lower().startswith("mock") or getattr(sig, "strategy_id", "").lower().startswith(
                        "mock"
                    ):
                        logger.warning(f"[{strat_name}] Discarding mock strategy signal for {symbol}")
                        continue
                    if "synthesized_alpha" in getattr(sig, "tags", []) and sig.confidence in (0.8, 0.82):
                        logger.warning(f"[{strat_name}] Discarding unvalidated stub synthesized signal for {symbol}")
                        continue
                    if getattr(sig, "factor_family", None) is None or sig.factor_family == "trend":
                        sig.factor_family = getattr(strat, "factor_family", "trend")

                    # Robust ATR bracket injection for valid signals lacking numeric SL/TP
                    if sig.valid and (sig.stop_loss is None or sig.entry_price is None):
                        try:
                            if hasattr(strat, "get_historical_candles"):
                                candles = await strat.get_historical_candles(session, symbol, "H1", 20)
                                if candles:
                                    current_price = float(candles[-1].close)
                                    if sig.entry_price is None or sig.entry_price <= 0:
                                        sig.entry_price = current_price
                                    if sig.stop_loss is None and sig.direction:
                                        from monika.application.analysis.strategies.base_strategy import EdgeStrategy

                                        sl, tp = EdgeStrategy.derive_atr_brackets(
                                            entry_price=sig.entry_price,
                                            candles=candles,
                                            direction=sig.direction,
                                        )
                                        sig.stop_loss = sl
                                        if sig.take_profit is None:
                                            sig.take_profit = tp
                        except Exception as sl_err:
                            logger.debug(f"[{strat_name}] Dynamic ATR SL/TP injection non-fatal: {sl_err}")

                    out.append(sig)
            except Exception as e:
                logger.warning(f"[{strat_name}] evaluate_all failed for {symbol}: {e}")
                if hasattr(session, "rollback"):
                    try:
                        rb = session.rollback()
                        if inspect.isawaitable(rb):
                            await rb
                    except Exception as rb_err:
                        logger.debug(f"[{strat_name}] rollback after failure (non-fatal): {rb_err}")
        return out

    @classmethod
    async def evaluate_strategy(
        cls,
        strategy_id: str,
        session,
        symbol: str,
        settings: dict,
        force_reload: bool = False,
        current_regime: Optional[str] = None,
    ) -> Optional[EdgeSignal]:
        """Evaluate a single specific strategy by its strategy_id."""
        strat_cls = cls.get_strategy(strategy_id)
        if not strat_cls:
            logger.warning(f"[StrategyRegistry] Strategy '{strategy_id}' not found in registry.")
            return None

        if session and hasattr(session, "execute"):
            now_ts = time.time()
            if force_reload or (now_ts - cls._last_load_time >= cls._load_interval):
                try:
                    await cls.load_dynamic_parameters(session)
                    cls._last_load_time = now_ts
                except Exception as e:
                    logger.debug(f"[StrategyRegistry] dynamic param check non-fatal: {e}")

        strat = None
        if callable(strat_cls):
            try:
                strat = strat_cls(settings)
            except TypeError:
                try:
                    strat = strat_cls(**(settings if isinstance(settings, dict) else {}))
                except TypeError:
                    strat = strat_cls()
        else:
            strat = strat_cls

        if strat is None:
            return None

        dyn_params = dict(cls._dynamic_params.get(strategy_id, {}))
        sym_key = (strategy_id, symbol.upper())
        if sym_key in cls._dynamic_symbol_params:
            dyn_params.update(cls._dynamic_symbol_params[sym_key])
        if dyn_params:
            cls._apply_dynamic_params_to_strategy(strat, dyn_params)

        if current_regime and hasattr(strat, "is_regime_compatible"):
            if not strat.is_regime_compatible(current_regime):
                return None

        try:
            sig_params = inspect.signature(strat.evaluate).parameters
            if "current_regime" in sig_params:
                res = getattr(strat, "evaluate")(session, symbol, settings, current_regime=current_regime)
            else:
                res = strat.evaluate(session, symbol, settings)
        except ValueError, TypeError:
            res = strat.evaluate(session, symbol, settings)
        if inspect.isawaitable(res):
            res = await res
        if res and isinstance(res, EdgeSignal) and res.valid and (res.stop_loss is None or res.entry_price is None):
            try:
                if hasattr(strat, "get_historical_candles"):
                    candles = await strat.get_historical_candles(session, symbol, "H1", 20)
                    if candles:
                        current_price = float(candles[-1].close)
                        if res.entry_price is None or res.entry_price <= 0:
                            res.entry_price = current_price
                        if res.stop_loss is None and res.direction:
                            from monika.application.analysis.strategies.base_strategy import EdgeStrategy

                            sl, tp = EdgeStrategy.derive_atr_brackets(
                                entry_price=res.entry_price,
                                candles=candles,
                                direction=res.direction,
                            )
                            res.stop_loss = sl
                            if res.take_profit is None:
                                res.take_profit = tp
            except Exception as sl_err:
                logger.debug(f"[StrategyRegistry] Dynamic ATR SL/TP injection non-fatal: {sl_err}")
        return res


STRATEGY_REGISTRY = StrategyRegistry._registry
