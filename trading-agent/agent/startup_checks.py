"""
File: trading-agent/agent/startup_checks.py
Startup health and environment validation checks for Trading Agent.
Extracted from main.py for modularity and maintainability.
"""

import ast
import asyncio
import logging
import os
import pathlib
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("TradingAgent.StartupChecks")


def _get_env(key: str, default: Any = None) -> Any:
    """Read env var, honoring test mocks on main.os.getenv if present."""
    try:
        if "main" in sys.modules and hasattr(sys.modules["main"], "os"):
            return sys.modules["main"].os.getenv(key, default)
    except Exception:
        pass
    return os.getenv(key, default)


class StartupChecker:
    """Runs all pre-flight startup validation checks."""

    def __init__(self, settings: dict, db_engine=None, mt5_client=None):
        self.settings = settings or {}
        self.db_engine = db_engine
        self.mt5_client = mt5_client

    async def run_all_checks(self) -> Tuple[bool, List[str]]:
        """Run all startup checks. Returns (passed, list_of_warnings)."""
        ok = True
        warnings: List[str] = []

        # 1. AST task role check
        role_ok, role_warns = self._check_task_roles()
        if not role_ok:
            ok = False
        warnings.extend(role_warns)

        # 2. Critical constants
        const_ok, const_warns = self._check_critical_constants()
        if not const_ok:
            ok = False
        warnings.extend(const_warns)

        # 3. Specialist prompts
        prompt_ok, prompt_warns = self._check_specialist_prompts()
        if not prompt_ok:
            ok = False
        warnings.extend(prompt_warns)

        # 4. PreFlight baselines
        preflight_ok, preflight_warns = self._check_preflight_baselines()
        if not preflight_ok:
            ok = False
        warnings.extend(preflight_warns)

        # 5. Paper trading gate & risk params
        paper_ok, paper_warns = await self._check_paper_trading_gate()
        if not paper_ok:
            ok = False
        warnings.extend(paper_warns)

        # 6. Database schema check
        db_ok, db_warns = await self._check_db_schema()
        warnings.extend(db_warns)
        if not db_ok:
            return False, warnings

        # 7. API keys and model catalog ping
        api_ok, api_warns = await self._check_api_keys()
        if not api_ok:
            ok = False
        warnings.extend(api_warns)

        # 8. External services (Telegram, FRED)
        ext_warns = self._check_external_services()
        warnings.extend(ext_warns)

        # 9. MT5 connectivity
        mt5_ok, mt5_warns = await self._check_mt5_connection()
        if not mt5_ok:
            ok = False
        warnings.extend(mt5_warns)

        # 10. Tool handlers validation
        tools_ok, tools_warns = await self._check_tool_handlers()
        if not tools_ok:
            ok = False
        warnings.extend(tools_warns)

        # 11. Performance notes path & critical model roles
        model_roles_ok, model_roles_warns = self._check_model_roles()
        if not model_roles_ok:
            ok = False
        warnings.extend(model_roles_warns)

        return ok, warnings

    def _check_task_roles(self) -> Tuple[bool, List[str]]:
        ok = True
        warnings = []
        try:
            declared_roles = set(self.settings.get("llm", {}).get("task_roles", {}).keys())
            if declared_roles:
                used_roles = set()
                for py_file in pathlib.Path(".").rglob("*.py"):
                    parts = [p.lower() for p in py_file.parts]
                    if any(p in ("tests", "test", "venv", ".venv", "__pycache__") for p in parts):
                        continue
                    try:
                        tree = ast.parse(py_file.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in (
                            "get_client_for_task",
                            "_get_cached_client",
                        ):
                            role_val = None
                            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                                role_val = node.args[0].value
                            elif node.keywords:
                                for kw in node.keywords:
                                    if kw.arg in ("task_role", "role") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                                        role_val = kw.value.value
                                        break
                            if role_val:
                                used_roles.add(role_val)
                missing_roles = used_roles - declared_roles
                if missing_roles:
                    logger.error(f"[STARTUP CHECK FAIL] Task role dipakai di kode tapi TIDAK ADA di settings.yaml: {missing_roles}")
                    ok = False
                else:
                    logger.info(f"  [OK] All {len(used_roles)} task_role references match settings.yaml")
        except Exception as e:
            logger.warning(f"Task role consistency check failed (non-fatal): {e}")
            warnings.append(f"Task role check warning: {e}")
        return ok, warnings

    def _check_critical_constants(self) -> Tuple[bool, List[str]]:
        try:
            from utils.constants import MARKET_OUTCOME_EXIT_REASONS
            if not MARKET_OUTCOME_EXIT_REASONS:
                raise ValueError("MARKET_OUTCOME_EXIT_REASONS is empty")
            logger.info(f"  [OK] utils.constants importable (MARKET_OUTCOME_EXIT_REASONS={MARKET_OUTCOME_EXIT_REASONS})")
            return True, []
        except (ImportError, ValueError) as e:
            logger.error(f"  [FAIL] utils/constants.py missing or invalid: {e}. Paper tracking will not function.")
            return False, [f"Critical constants missing: {e}"]

    def _check_specialist_prompts(self) -> Tuple[bool, List[str]]:
        try:
            from analysis.stages.per_asset_stage import SPECIALIST_PROMPTS, _render_specialist_prompt
            for role, template in SPECIALIST_PROMPTS.items():
                _render_specialist_prompt(template, "TESTUSD", "TEST", "USD")
            logger.info("  [OK] Specialist prompt templates render without error")
            return True, []
        except Exception as e:
            logger.error(f"  [FAIL] Specialist prompt template render failed: {e}")
            return False, [f"Specialist prompt error: {e}"]

    def _check_preflight_baselines(self) -> Tuple[bool, List[str]]:
        try:
            from analysis.stages.preflight_gate import PreFlightTurnGate, EMPIRICAL_ACTIVE_MEDIANS
            if not EMPIRICAL_ACTIVE_MEDIANS:
                raise ValueError("EMPIRICAL_ACTIVE_MEDIANS is empty")
            logger.info(f"  [OK] PreFlightTurnGate empirical baselines verified ({len(EMPIRICAL_ACTIVE_MEDIANS)} symbols)")
            return True, []
        except Exception as e:
            logger.error(f"  [FAIL] PreFlightTurnGate baseline check failed: {e}")
            return False, [f"PreFlight baseline error: {e}"]

    async def _check_paper_trading_gate(self) -> Tuple[bool, List[str]]:
        ok = True
        warnings = []
        is_dry_run = "--dry-run" in sys.argv

        if not self.settings.get("paper_trading", {}).get("enabled", False):
            logger.error("[FAIL] paper_trading.enabled must be True. Cannot monitor edge without paper trades.")
            ok = False

        risk_cfg = self.settings.get("trading", {}).get("risk", {})
        if risk_cfg.get("intraday_range_strategy_enabled", True):
            logger.info(
                f"  [INFO] Intraday-range strategy ENABLED: TP band "
                f"{risk_cfg.get('intraday_tp_min_adr_pct', 0.5)*100:.0f}-"
                f"{risk_cfg.get('intraday_tp_max_adr_pct', 0.8)*100:.0f}% ADR, "
                f"SL ceiling {risk_cfg.get('intraday_max_sl_adr_pct', 0.35)*100:.0f}% ADR, "
                f"min_rr_ratio={risk_cfg.get('min_rr_ratio', 1.3)}"
            )
        risk_pct = risk_cfg.get("risk_percent_per_trade", 1.0)
        if risk_pct > 1.0:
            logger.warning(f"[WARN] risk_percent_per_trade={risk_pct}% is high. Recommended: ≤1.0% until edge is proven.")
            warnings.append("risk_percent_per_trade is high")

        max_pos = risk_cfg.get("max_concurrent_positions", 5)
        if max_pos > 5:
            logger.warning(f"[WARN] max_concurrent_positions={max_pos} is high. Recommended: ≤5 for risk management.")
            warnings.append("max_concurrent_positions is high")

        db_url = _get_env("DATABASE_URL", "")
        if "sqlite" in str(db_url).lower():
            logger.error(
                "[FAIL] SQLite detected. PostgreSQL is REQUIRED — partial unique indexes "
                "guarding position-duplication behave incorrectly on SQLite regardless of environment."
            )
            ok = False

        if not is_dry_run:
            mt5_path = _get_env("MT5_PATH", "")
            if not mt5_path or not os.path.exists(mt5_path):
                logger.warning(f"[WARN] MT5_PATH not found: {mt5_path}. Live execution will fail.")
                warnings.append(f"MT5_PATH not found: {mt5_path}")

        max_score_disc = risk_cfg.get("max_score_discrepancy_allowed", 1)
        if max_score_disc < 3:
            logger.warning(
                f"[WARN] max_score_discrepancy_allowed={max_score_disc} sangat ketat. "
                f"Non-deterministic factors (RSI, OTE, COT, S/R zone) bisa menambah legitimate +3-4 poin. "
                f"Nilai ini menyebabkan banyak setup valid diblokir. REKOMENDASI: set ke 3."
            )
            warnings.append("max_score_discrepancy_allowed is strict")

        paper_cfg = self.settings.get("paper_trading", {})
        tp_method = paper_cfg.get("tp_detection_method", "NOT_SET")
        if tp_method not in ("close_price", "high_low"):
            logger.error(f"  [FAIL] tp_detection_method tidak valid: {tp_method}. Harus 'close_price' atau 'high_low'.")
            ok = False
        elif tp_method == "high_low":
            logger.warning("  [WARN] tp_detection_method=high_low akan inflate paper win rate. Gunakan 'close_price' untuk hasil realistic.")
            warnings.append("tp_detection_method is high_low")
        else:
            logger.info("  [OK] tp_detection_method=close_price (conservative, accurate)")

        min_paper_trades = self.settings.get("trading", {}).get("min_paper_trades_before_live", 40)
        if min_paper_trades < 30:
            logger.warning(f"  [WARN] min_paper_trades_before_live={min_paper_trades} terlalu rendah. Butuh setidaknya 30 trades.")
            warnings.append("min_paper_trades_before_live too low")

        try:
            from database.db import AsyncSessionLocal
            from utils.analytics.paper_tracker import PaperTracker
            async with AsyncSessionLocal() as session:
                tracker = PaperTracker(self.settings)
                stats = await tracker.get_statistics(session)
                paper_trades = stats.get("total_trades", 0)
                win_rate = stats.get("win_rate_pct", 0)
                min_paper_trades_live = self.settings.get("trading", {}).get("min_paper_trades_before_live", 50)

                if paper_trades == 0:
                    logger.warning(
                        "  [WARN] No paper trades yet. System is in ACCUMULATION phase. "
                        "Ensure --dry-run flag is active. auto_execute will run to accumulate data."
                    )
                elif paper_trades < min_paper_trades_live:
                    logger.info(
                        f"  [INFO] Paper trades: {paper_trades}/{min_paper_trades_live} accumulated. "
                        f"Win rate: {win_rate:.1f}%. Accumulation phase ongoing."
                    )
                else:
                    logger.info(
                        f"  [OK] Paper trades: {paper_trades} (>{min_paper_trades_live}). "
                        f"Win rate: {win_rate:.1f}%. Performance gate: "
                        f"{'PASS' if win_rate >= self.settings.get('trading', {}).get('min_paper_win_rate_pct', 45) else 'FAIL'}"
                    )

                auto_execute = self.settings.get("trading", {}).get("auto_execute", False)
                if not is_dry_run and auto_execute and paper_trades < min_paper_trades_live:
                    logger.error(
                        f"[FAIL] CRITICAL SAFETY BLOCK: auto_execute=True but only {paper_trades} "
                        f"paper trades collected (minimum: {min_paper_trades_live}). "
                        f"CANNOT start in live mode. Set auto_execute=false or collect more paper trades first."
                    )
                    ok = False
        except Exception as e:
            logger.warning(f"  [WARN] Paper trade status check failed: {e}")
            ok = False

        return ok, warnings

    async def _check_db_schema(self) -> Tuple[bool, List[str]]:
        ok = True
        warnings = []
        try:
            from database.db import engine
            from sqlalchemy import text

            db_url = _get_env("DATABASE_URL", "")
            db_type = "SQLite" if "sqlite" in str(db_url).lower() else "PostgreSQL"
            logger.info(f"Database: {db_type} ({str(db_url).split('@')[-1] if '@' in str(db_url) else 'local'})")

            if "sqlite" in str(db_url).lower():
                logger.warning("Using SQLite - NOT recommended for production.")
                if self.settings.get("environment") == "live":
                    logger.critical("CRITICAL: SQLite is not safe for live trading! Migrate to PostgreSQL.")
                    ok = False

            eng = self.db_engine or engine
            async with eng.connect() as conn:
                await conn.execute(text("SELECT 1"))
                logger.info("  [OK] Database connection")

                try:
                    from database.models import Base
                    critical_tables = [
                        "news_items", "economic_calendar", "asset_analysis",
                        "fundamental_briefs", "paper_trade_records", "trade_outcomes",
                        "positions", "risk_state", "system_config", "decision_reflections",
                        "prescreen_log", "candidate_lessons"
                    ]

                    if "postgresql" in str(db_url).lower():
                        res_tables = await conn.execute(text(
                            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                        ))
                        existing_tables = {row[0] for row in res_tables}
                        missing_tables = [t for t in critical_tables if t not in existing_tables]

                        if missing_tables:
                            logger.error(f"  [FAIL] Missing tables in database: {missing_tables}. Run 'alembic upgrade head'.")
                            ok = False
                        else:
                            res_cols = await conn.execute(text(
                                "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'"
                            ))
                            existing_cols: Dict[str, Set[str]] = {}
                            for row in res_cols:
                                existing_cols.setdefault(row[0], set()).add(row[1])

                            schema_gap_found = False
                            for t in critical_tables:
                                if t in Base.metadata.tables:
                                    expected_cols = set(Base.metadata.tables[t].columns.keys())
                                    actual_cols = existing_cols.get(t, set())
                                    missing_cols = expected_cols - actual_cols
                                    if missing_cols:
                                        logger.error(f"  [FAIL] Schema mismatch on table '{t}': missing column(s) {missing_cols}.")
                                        schema_gap_found = True

                            if schema_gap_found:
                                ok = False
                            else:
                                logger.info(f"  [OK] All {len(critical_tables)} critical tables and columns verified")

                            # M-6: Check pgvector extension availability for episodic memory search
                            try:
                                res_ext = await conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'"))
                                has_pgvector = bool(res_ext.scalar())
                                if has_pgvector:
                                    logger.info("  [OK] pgvector extension verified")
                                else:
                                    msg = "pgvector extension not installed in PostgreSQL. Required for vector semantic memory search."
                                    if self.settings.get("environment") == "live":
                                        logger.error(f"  [FAIL] {msg}")
                                        ok = False
                                    else:
                                        logger.warning(f"  [WARN] {msg}")
                                        warnings.append(msg)
                            except Exception as ext_err:
                                logger.debug(f"pgvector check query failed: {ext_err}")
                    else:
                        logger.info(f"  [OK] All {len(critical_tables)} critical tables verified")
                except Exception as e:
                    logger.warning(f"  [WARN] Schema check failed: {e}")

                try:
                    from database.models import SystemConfig
                    from sqlalchemy import delete, select
                    from database.db import AsyncSessionLocal
                    async with AsyncSessionLocal() as startup_session:
                        await startup_session.execute(
                            delete(SystemConfig).where(SystemConfig.key.like("pending_specialist_biases_%"))
                        )
                        # Auto-cleanup legacy blacklisted stub synthesized strategies from SystemConfig
                        res_stubs = await startup_session.execute(
                            select(SystemConfig).where(SystemConfig.key.like("synthesized_strategy_%"))
                        )
                        stub_keys = []
                        for r in res_stubs.scalars().all():
                            if r and r.value and 'direction="buy"' in r.value and 'confidence=0.82' in r.value:
                                stub_keys.append(r.key)
                        if stub_keys:
                            await startup_session.execute(
                                delete(SystemConfig).where(SystemConfig.key.in_(stub_keys))
                            )
                            logger.info(f"  [OK] Cleaned up {len(stub_keys)} legacy blacklisted stub synthesized strategies from SystemConfig")
                        await startup_session.commit()
                    logger.info("  [OK] Cleaned up temporary specialist biases from previous runs")
                except Exception as e:
                    logger.warning(f"  [WARN] Startup specialist biases cleanup failed (non-fatal): {e}")

                try:
                    from utils.analytics.cost_tracker import CostTracker
                    from database.db import AsyncSessionLocal
                    async with AsyncSessionLocal() as budget_session:
                        b_stat = await CostTracker.check_and_update_budget_status(budget_session, self.settings)
                        logger.info(
                            f"  [OK] AI Budget Status: MTD ${b_stat['mtd_cost']:.4f}/${b_stat['monthly_budget']:.2f} "
                            f"({b_stat['usage_pct']:.1f}%), Daily ${b_stat['daily_cost']:.4f}/${b_stat['daily_budget']:.2f} "
                            f"(Paused: {b_stat['is_paused']})"
                        )
                except Exception as e:
                    logger.warning(f"  [WARN] AI Budget synchronization check failed (non-fatal): {e}")

                try:
                    from analysis.memory.chronicle_writer import ChronicleWriter
                    from database.db import AsyncSessionLocal
                    async with AsyncSessionLocal() as chronicle_session:
                        c_writer = ChronicleWriter(self.settings)
                        synced = await c_writer.sync_macro_reality_from_file(chronicle_session)
                        logger.info(f"  [OK] Macro reality synchronized ({synced} active structural regimes verified)")
                except Exception as e:
                    logger.warning(f"  [WARN] Macro reality synchronization failed (non-fatal): {e}")

        except Exception as e:
            logger.error(f"  [FAIL] Database: {e}")
            ok = False

        return ok, warnings

    async def _check_api_keys(self) -> Tuple[bool, List[str]]:
        ok = True
        warnings = []
        env_map = {
            "anthropic": ["ANTHROPIC_API_KEY"],
            "gemini": ["GEMINI_API_KEYS", "GEMINI_PAID_API_KEY", "GEMINI_API_KEY"],
            "openai": ["OPENAI_API_KEY"],
            "deepseek": ["DEEPSEEK_API_KEY"],
            "groq": ["GROQ_API_KEYS", "GROQ_API_KEY"],
            "openrouter": ["OPENROUTER_PAID_API_KEY", "OPENROUTER_API_KEYS", "OPENROUTER_API_KEY"],
            "ollama": [],
        }

        providers_cfg = self.settings.get("llm", {}).get("providers", {})
        model_catalog = self.settings.get("llm", {}).get("model_catalog", {})

        try:
            from analysis.providers.llm_factory import LLMFactory
            factory = LLMFactory(self.settings)

            for provider_name, config in providers_cfg.items():
                if not config.get("enabled", False):
                    continue

                req_keys = env_map.get(provider_name, [])
                keys_missing = False
                if req_keys:
                    if not any(_get_env(k) for k in req_keys):
                        logger.error(f"  [FAIL] None of {req_keys} are set (Required for {provider_name})")
                        ok = False
                        keys_missing = True

                if keys_missing:
                    continue

                preferred_ping_models = {
                    "openrouter": "openrouter/free",
                    "gemini": "gemini-3.5-flash-lite",
                    "groq": "groq-compound",
                    "ollama": "llama3.2",
                }

                test_model = None
                if provider_name in preferred_ping_models and preferred_ping_models[provider_name] in model_catalog:
                    test_model = preferred_ping_models[provider_name]
                else:
                    for m_name, m_info in model_catalog.items():
                        if m_info.get("provider") == provider_name:
                            test_model = m_name
                            break

                if not test_model:
                    logger.warning(f"  [WARN] No model found in catalog for provider '{provider_name}'. Skipping ping test.")
                    continue

                try:
                    client = factory._create_client_instance(test_model, {"max_tokens": 10})
                    if client:
                        logger.info(f"  [TEST] Pinging {provider_name} (model: {test_model})...")
                        res = await client.generate("ping", temperature=0.0)
                        if res is None:
                            raise Exception("API returned None")
                        served_model = getattr(client, "last_served_model", None)
                        served_info = f" (served by: {served_model})" if served_model and served_model != test_model else ""
                        logger.info(f"  [OK] {provider_name} API is functional{served_info}")
                except Exception as e:
                    logger.warning(f"  [WARN] {provider_name} ping failed: {e}. System will rely on fallback providers.")
        except Exception as factory_err:
            logger.error(f"  [FAIL] Error initializing API test loop: {factory_err}")
            ok = False

        # Groq model alias check
        try:
            from analysis.providers.groq_provider import GROQ_MODEL_ALIASES
            if providers_cfg.get("groq", {}).get("enabled", False) and any(_get_env(k) for k in ["GROQ_API_KEYS"]):
                import httpx
                groq_keys_raw = _get_env("GROQ_API_KEYS", "")
                groq_key = groq_keys_raw.split(",")[0].strip() if groq_keys_raw else ""
                if groq_key:
                    try:
                        async with httpx.AsyncClient(timeout=10.0) as http:
                            resp = await http.get(
                                "https://api.groq.com/openai/v1/models",
                                headers={"Authorization": f"Bearer {groq_key}"},
                            )
                            if resp.status_code == 200:
                                available_ids = {m["id"] for m in resp.json().get("data", [])}
                                for alias, groq_id in GROQ_MODEL_ALIASES.items():
                                    if groq_id not in available_ids:
                                        logger.warning(f'  [WARN] Groq alias "{alias}" maps to "{groq_id}" which is NOT in Groq model list.')
                                    else:
                                        logger.info(f'  [OK] Groq alias "{alias}" -> "{groq_id}" validated')
                    except Exception as groq_val_err:
                        logger.warning(f"  [WARN] Groq model validation failed: {groq_val_err}")
        except ImportError:
            pass

        return ok, warnings

    def _check_external_services(self) -> List[str]:
        warnings = []
        token = _get_env("TELEGRAM_BOT_TOKEN", "")
        if token and not str(token).startswith("your_"):
            logger.info("  [OK] Telegram bot token")
        else:
            logger.warning("  [WARN] TELEGRAM_BOT_TOKEN not set — Telegram disabled")
            warnings.append("Telegram disabled")

        if _get_env("FRED_API_KEY"):
            logger.info("  [OK] FRED API key")
        else:
            logger.warning("  [WARN] FRED_API_KEY not set — treasury yield fetcher disabled")
            warnings.append("FRED_API_KEY not set")

        return warnings

    async def _check_mt5_connection(self) -> Tuple[bool, List[str]]:
        ok = True
        warnings = []
        try:
            import MetaTrader5 as mt5
            logger.info("  [OK] MetaTrader5 library available")
            from execution.mt5_client import MT5Client
            test_client = self.mt5_client or MT5Client(self.settings)
            if await test_client.connect():
                logger.info("  [OK] MetaTrader5 connection validated")
                xti_cfg = self.settings.get("trading", {}).get("edge_strategy", {}).get("xti_pairs_readiness", {})
                if xti_cfg.get("enabled", False):
                    brent_sym = xti_cfg.get("brent_symbol", "XBRUSD")
                    info = await test_client.get_symbol_info(brent_sym)
                    if info:
                        logger.info(f"  [OK] Brent '{brent_sym}' available — XTI dual-leg stat-arb enabled")
                    else:
                        logger.error(f"  [FAIL] Brent '{brent_sym}' NOT found on broker — disabling XTI pairs strategy")
                        self.settings.setdefault("trading", {}).setdefault("edge_strategy", {}).setdefault(
                            "xti_pairs_readiness", {}
                        )["enabled"] = False
                await test_client.disconnect()
            else:
                if self.settings.get("paper_trading", {}).get("enabled", False):
                    logger.warning("  [WARN] MetaTrader5 connection failed, but paper trading is enabled")
                else:
                    logger.error("  [FAIL] MetaTrader5 connection failed (required for live trading)")
                    ok = False
        except ImportError:
            logger.warning("  [WARN] MetaTrader5 not installed — live execution disabled")
        except Exception as e:
            logger.warning(f"  [WARN] MT5 connection check exception: {e}")
        return ok, warnings

    async def _check_tool_handlers(self) -> Tuple[bool, List[str]]:
        ok = True
        warnings = []
        try:
            from analysis.tools.tool_executor import ToolExecutor
            from analysis.tools.tools_definitions import ALL_TOOLS
            from database.db import AsyncSessionLocal
            from analysis.tools.registry import default_tool_registry

            async with AsyncSessionLocal() as session:
                executor = ToolExecutor(session)

            # Trigger full handler registration (decorators + module-level ToolDefinition lists)
            try:
                import analysis.tools.handlers  # noqa: F401
            except Exception as reg_err:
                logger.error(f"  [FAIL] Tool handler registration import: {reg_err}")
                ok = False

            domain_attrs = [
                "execution_handlers", "position_handlers", "macro_handlers",
                "sentiment_handlers", "technical_handlers",
            ]

            def _resolves(tool_name: str) -> bool:
                """Mirror ModularToolExecutor.execute dispatch chain (resolution only, no execution)."""
                if hasattr(type(executor), f"_tool_{tool_name}"):
                    return True
                for attr in domain_attrs:
                    dh = getattr(executor, attr, None)
                    if dh is not None and hasattr(dh, tool_name):
                        return True
                if default_tool_registry.get(tool_name) is not None:
                    return True
                return default_tool_registry.resolve_name(tool_name) != tool_name

            missing_handlers = [t["name"] for t in ALL_TOOLS if not _resolves(t["name"])]

            if missing_handlers:
                logger.error(f"  [FAIL] Tools with no resolvable handler (schema-only, would return UnknownToolError): {missing_handlers}")
                ok = False
            else:
                logger.info(f"  [OK] All {len(ALL_TOOLS)} tool schemas resolve to a handler")

            try:
                from database.models import OrderBlock
                logger.info("  [OK] OrderBlock model importable")
            except ImportError as e:
                logger.error(f"  [FAIL] OrderBlock import: {e}")
                ok = False

            try:
                from sqlalchemy import text
                from database.db import engine
                eng = self.db_engine or engine
                async with eng.connect() as conn:
                    await conn.execute(text("SELECT 1 FROM dxy_data LIMIT 1"))
                logger.info("  [OK] DXYData table accessible")
            except Exception as e:
                logger.warning(f"  [WARN] DXYData check: {e} (may be empty)")

        except Exception as e:
            logger.warning(f"  [WARN] Tool validation failed: {e}")

        return ok, warnings

    def _check_model_roles(self) -> Tuple[bool, List[str]]:
        ok = True
        warnings = []
        try:
            from utils.analytics.performance_reviewer import PERFORMANCE_NOTES_PATH
            from skills.loader import _SKILLS_DIR
            if PERFORMANCE_NOTES_PATH.parent.resolve() != _SKILLS_DIR.resolve():
                logger.error(f"[STARTUP CHECK FAIL] performance_notes write path {PERFORMANCE_NOTES_PATH.parent} does not match skills read path {_SKILLS_DIR}")
                ok = False
        except Exception as e:
            logger.error(f"Performance path check failed: {e}")

        critical_roles = [
            "stage1_fundamental", "stage1_escalation", "stage2_per_asset_primary",
            "stage2_per_asset_secondary", "chat_telegram", "stage2_prescreen"
        ]
        task_roles_cfg = self.settings.get("llm", {}).get("task_roles", {})
        # Tool-bearing roles must never fall back to a provider without tool calling
        # (OllamaProvider.run_tool_agent raises NotImplementedError mid-cycle).
        tool_bearing_roles = {
            "stage1_fundamental", "stage1_escalation", "stage2_per_asset_primary",
            "stage2_per_asset_secondary", "chat_telegram", "stage2_prescreen",
            "stage2_session_trigger", "specialist_technical", "specialist_sentiment",
            "specialist_macro", "news_digest", "cot_precompute",
        }
        from analysis.providers.llm_factory import LLMFactory
        resolver = LLMFactory(self.settings)
        for role in critical_roles:
            role_cfg = task_roles_cfg.get(role, {})
            slots = ["primary"] + [f"fallback_{i}" for i in range(1, 9)]
            for slot in slots:
                model_name = role_cfg.get(slot)
                if not model_name:
                    continue
                if model_name not in self.settings.get("llm", {}).get("model_catalog", {}):
                    logger.error(f'[STARTUP CHECK FAIL] task_roles.{role}.{slot}="{model_name}" not found in llm.model_catalog')
                    ok = False
                    continue
                if role in tool_bearing_roles:
                    provider = resolver._resolve_provider(model_name)
                    if provider == "ollama":
                        logger.error(
                            f'[STARTUP CHECK FAIL] task_roles.{role}.{slot}="{model_name}" '
                            f'resolves to provider "ollama" which does not support tool calling.'
                        )
                        ok = False

        try:
            import anthropic
            if _get_env("ANTHROPIC_API_KEY"):
                client = anthropic.AsyncAnthropic()
                logger.info("  [OK] Anthropic client initialized successfully")
        except Exception as e:
            logger.error(f"  [FAIL] Anthropic client init: {e}")
            ok = False

        return ok, warnings


async def run_startup_checks(settings: dict) -> bool:
    """Backward-compatible runner for all startup health checks."""
    checker = StartupChecker(settings)
    ok, _ = await checker.run_all_checks()
    return ok
