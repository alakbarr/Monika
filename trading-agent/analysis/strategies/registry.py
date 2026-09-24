import json
import logging
import time
import inspect
from pathlib import Path
from typing import Type, Optional, Dict, Any
from sqlalchemy import select, delete, update
from database.models import SystemConfig
from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal

logger = logging.getLogger("TradingAgent.StrategyRegistry")

class StrategyRegistry:
    _registry: dict[str, Type[EdgeStrategy]] = {}
    _dynamic_params: dict[str, dict] = {}
    _blacklisted_ids: set[str] = set()
    _last_load_time: float = 0.0
    _load_interval: float = 60.0

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
    def list_strategies(cls) -> list[str]:
        return list(cls._registry.keys())

    @classmethod
    def hot_reload(cls, strategy_id: str, parameters: dict) -> None:
        """Hot-reloads dynamic parameter overrides for a specific strategy into active memory."""
        if not isinstance(parameters, dict):
            return
        cls._dynamic_params.setdefault(strategy_id, {}).update(parameters)
        logger.info(f"[StrategyRegistry] Hot-reloaded dynamic parameters for '{strategy_id}': {parameters}")

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

            # 1. Load direct strategy parameter overrides (key: strategy_params_<strat_id>)
            stmt_params = select(SystemConfig).where(SystemConfig.key.like("strategy_params_%"))
            rows_params = await _safe_scalars(stmt_params)
            for r in rows_params:
                if not r or not getattr(r, "key", None) or not getattr(r, "value", None):
                    continue
                strat_id = r.key.replace("strategy_params_", "")
                try:
                    p_data = json.loads(r.value)
                    if isinstance(p_data, dict):
                        cls.hot_reload(strat_id, p_data)
                except Exception as parse_err:
                    logger.debug(f"[StrategyRegistry] Failed parsing params for {strat_id}: {parse_err}")

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
                        params = hyp.get("parameters", {})
                        if strat_type and params:
                            cls.hot_reload(strat_type, params)
                except Exception as prop_err:
                    logger.debug(f"[StrategyRegistry] Failed loading candidate alpha proposal: {prop_err}")

            # 3. Load registered synthesized strategies
            stmt_synths = select(SystemConfig).where(SystemConfig.key.like("synthesized_strategy_%"))
            rows_synths = await _safe_scalars(stmt_synths)
            loaded_synths_count = 0
            for r in rows_synths:
                if not r or not getattr(r, "value", None):
                    continue
                try:
                    s_data = json.loads(r.value)
                    s_id = s_data.get("strategy_id")
                    if not s_id or s_id in cls._registry or s_id in cls._blacklisted_ids:
                        continue
                    py_code = s_data.get("python_code")
                    cls_name = s_data.get("class_name")
                    if s_id and py_code and cls_name:
                        # Reject stub templates with hardcoded static signals
                        if 'direction="buy"' in py_code and 'confidence=0.82' in py_code:
                            cls._blacklisted_ids.add(s_id)
                            logger.info(f"[StrategyRegistry] Skipping and purging blacklisted stub synthesized strategy: {s_id}")
                            if hasattr(session, "execute"):
                                try:
                                    del_stmt = delete(SystemConfig).where(SystemConfig.key == f"synthesized_strategy_{s_id}")
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
                        from scheduler.strategy_synthesis_scheduler import StrategySynthesisScheduler
                        synth_sched = StrategySynthesisScheduler({})
                        loaded_cls = synth_sched.compile_strategy_class(py_code, cls_name)
                        if loaded_cls:
                            cls.register(loaded_cls, overwrite=True)
                            loaded_synths_count += 1
                        else:
                            # Self-healing fallback: Check if a valid version exists on disk
                            disk_path = Path(__file__).resolve().parent / "synthesized" / f"{s_id}.py"
                            healed = False
                            if disk_path.exists():
                                try:
                                    disk_code = disk_path.read_text(encoding="utf-8")
                                    disk_cls = synth_sched.compile_strategy_class(disk_code, cls_name)
                                    if disk_cls:
                                        cls.register(disk_cls, overwrite=True)
                                        loaded_synths_count += 1
                                        healed = True
                                        logger.info(f"[StrategyRegistry] Self-healed strategy '{s_id}' from disk version.")
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
                                    logger.debug(f"[StrategyRegistry] Disk self-healing attempt failed for {s_id}: {heal_err}")
                            if not healed:
                                cls._blacklisted_ids.add(s_id)
                                logger.warning(f"[StrategyRegistry] Quarantined corrupted synthesized strategy '{s_id}': compilation failed.")
                except Exception as synth_err:
                    logger.debug(f"[StrategyRegistry] Failed restoring synthesized strategy: {synth_err}")

            if loaded_synths_count > 0:
                cls.log_summary()

        except Exception as e:
            logger.warning(f"[StrategyRegistry] load_dynamic_parameters non-fatal error: {e}")

        return dict(cls._dynamic_params)

    @classmethod
    async def evaluate_all(cls, session, symbol: str, settings: dict, force_reload: bool = False) -> list[EdgeSignal]:
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

                # Apply dynamic parameter overrides from DB SystemConfig / hot-reload
                if strat_id in cls._dynamic_params:
                    strat.cfg = dict(getattr(strat, "cfg", {}))
                    strat.cfg.update(cls._dynamic_params[strat_id])

                if not strat.is_enabled(symbol):
                    continue

                sig = await strat.evaluate(session, symbol, settings)
                if sig is not None and not isinstance(sig, EdgeSignal):
                    logger.warning(f"[{strat_name}] evaluate returned non-EdgeSignal ({type(sig)}) for {symbol}, discarding")
                    continue
                if sig and sig.valid:
                    # Guard against static uncalculated synthesized stub signals
                    if "synthesized_alpha" in getattr(sig, "tags", []) and sig.confidence == 0.82:
                        logger.warning(f"[{strat_name}] Discarding unvalidated stub synthesized signal for {symbol}")
                        continue
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
