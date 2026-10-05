# ==============================================================================
# File: analysis/tools/handlers/execution_handlers.py
# ==============================================================================

"""
MT5 Execution, Headless Compilation, and Terminal Telemetry Handlers.
Provides tools for headless MQL5 EA compilation, local broker log reading,
and MT5 Algo Trading button visual status inspection.
"""

import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.tools.base_handler import ToolHandler
from analysis.tools.registry import register_tool
from utils.infra.platform_compat import safe_subprocess_run

logger = logging.getLogger("TradingAgent.Tools.ExecutionHandlers")


async def handle_compile_mql5_ea(
    args: Dict[str, Any],
    session: Optional[AsyncSession] = None,
    executor: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """Compile MQL5 source file (.mq5) into executable binary (.ex5) using metaeditor64.exe."""
    source_path_raw = args.get("source_path")
    if not source_path_raw:
        return {"status": "error", "error": "Missing required parameter 'source_path'"}

    source_path = Path(source_path_raw).resolve()
    if not source_path.exists():
        return {"status": "error", "error": f"Source file not found: {source_path}"}
    if source_path.suffix.lower() != ".mq5":
        return {"status": "error", "error": f"File must be an MQL5 source file (.mq5): {source_path.name}"}

    # Locate metaeditor64.exe
    from config.settings import load_settings
    settings = load_settings()
    mt5_path = os.getenv("MT5_PATH") or settings.get("mt5", {}).get("path")
    editor_candidates = []
    if mt5_path:
        mt5_dir = Path(mt5_path).parent
        editor_candidates.extend([
            mt5_dir / "metaeditor64.exe",
            mt5_dir / "metaeditor.exe",
        ])
    editor_candidates.extend([
        Path("C:/Program Files/MetaTrader 5/metaeditor64.exe"),
        Path("C:/Program Files/MetaTrader 5/metaeditor.exe"),
        Path("C:/Program Files (x86)/MetaTrader 5/metaeditor.exe"),
    ])

    editor_path = None
    for cand in editor_candidates:
        if cand.exists():
            editor_path = cand
            break

    if not editor_path:
        return {
            "status": "error",
            "error": "metaeditor64.exe not found. Please install MetaTrader 5 or configure MT5_PATH in settings.yaml."
        }

    log_path = source_path.parent / f"{source_path.stem}_compile.log"
    cmd = [
        str(editor_path),
        f"/compile:{source_path}",
        f"/log:{log_path}",
    ]

    try:
        retcode, stdout, stderr = await safe_subprocess_run(cmd, timeout=60)
        ex5_path = source_path.with_suffix(".ex5")

        log_content = ""
        if log_path.exists():
            try:
                log_content = log_path.read_text(encoding="utf-16-le", errors="replace")
            except Exception:
                log_content = log_path.read_text(encoding="utf-8", errors="replace")

        compiled_successfully = ex5_path.exists() and ex5_path.stat().st_size > 0
        return {
            "status": "success" if compiled_successfully else "failed",
            "compiled": compiled_successfully,
            "source_file": str(source_path),
            "output_binary": str(ex5_path) if compiled_successfully else None,
            "binary_size_bytes": ex5_path.stat().st_size if compiled_successfully else 0,
            "editor_used": str(editor_path),
            "log": log_content.strip() or stdout.strip(),
        }
    except Exception as e:
        return {"status": "error", "error": f"Compilation failed: {str(e)}"}


async def handle_get_mt5_broker_logs(
    args: Dict[str, Any],
    session: Optional[AsyncSession] = None,
    executor: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """Read recent lines from the broker's daily text log file in the MetaTrader 5 data directory."""
    lines_to_read = int(args.get("lines", 20))
    target_date = args.get("date") or datetime.now().strftime("%Y%m%d")

    log_candidates = []
    appdata = os.getenv("APPDATA")
    if appdata:
        terminal_base = Path(appdata) / "MetaQuotes" / "Terminal"
        if terminal_base.exists():
            for inst_dir in terminal_base.glob("*"):
                logs_dir = inst_dir / "Logs"
                if logs_dir.exists():
                    log_file = logs_dir / f"{target_date}.log"
                    if log_file.exists():
                        log_candidates.append(log_file)

    from config.settings import load_settings
    settings = load_settings()
    mt5_path = os.getenv("MT5_PATH") or settings.get("mt5", {}).get("path")
    if mt5_path:
        mt5_dir = Path(mt5_path).parent
        install_log = mt5_dir / "Logs" / f"{target_date}.log"
        if install_log.exists():
            log_candidates.append(install_log)

    if not log_candidates:
        return {
            "status": "not_found",
            "date": target_date,
            "message": f"No MT5 broker log file found for date {target_date}.",
            "logs": []
        }

    chosen_log = log_candidates[0]
    try:
        try:
            content = chosen_log.read_text(encoding="utf-16-le", errors="replace")
        except Exception:
            content = chosen_log.read_text(encoding="utf-8", errors="replace")

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        recent_lines = lines[-lines_to_read:] if len(lines) > lines_to_read else lines
        return {
            "status": "success",
            "date": target_date,
            "file": str(chosen_log),
            "total_lines": len(lines),
            "returned_lines": len(recent_lines),
            "logs": recent_lines
        }
    except Exception as e:
        return {"status": "error", "error": f"Failed to read MT5 log: {str(e)}"}


async def handle_get_mt5_terminal_info(
    args: Dict[str, Any],
    session: Optional[AsyncSession] = None,
    executor: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """Retrieve MetaTrader 5 terminal status, trade permissions (Green/Red button), and broker connection."""
    try:
        from execution.mt5_compat import ensure_mt5_module
        mt5 = ensure_mt5_module()
        term_info = mt5.terminal_info()
        if term_info is None:
            return {
                "status": "offline",
                "connected": False,
                "trade_allowed_button": "Merah (Mati)",
                "message": "MT5 terminal not running or not connected via bridge."
            }

        info_dict = term_info._asdict() if hasattr(term_info, "_asdict") else dict(term_info.__dict__)
        trade_allowed = bool(info_dict.get("trade_allowed", False))
        connected = bool(info_dict.get("connected", False))

        return {
            "status": "online",
            "connected": connected,
            "connection_status": "Terhubung" if connected else "Terputus",
            "trade_allowed": trade_allowed,
            "algo_trading_button": "Hijau (Aktif)" if trade_allowed else "Merah (Mati)",
            "community_account": info_dict.get("community_account", False),
            "company": info_dict.get("company", "Unknown Broker"),
            "name": info_dict.get("name", "MetaTrader 5"),
            "path": info_dict.get("path", ""),
            "data_path": info_dict.get("data_path", ""),
            "ping_last_ms": round(float(info_dict.get("ping_last", 0)) / 1000.0, 2),
        }
    except Exception as e:
        return {"status": "error", "error": f"Terminal info query failed: {str(e)}"}


# =============================================================================
# Tool Registry Bindings
# =============================================================================

@register_tool("compile_mql5_ea", aliases=["compile_ea", "compile_mql5"], category="EXECUTION", parallel_safe=False)
class CompileMql5EaHandler(ToolHandler):
    name = "compile_mql5_ea"
    category = "EXECUTION"
    parallel_safe = False

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_compile_mql5_ea(args, session=session, executor=executor, **kwargs)


@register_tool("get_mt5_broker_logs", aliases=["mt5_broker_logs", "read_broker_logs"], category="SYSTEM", parallel_safe=True)
class GetMt5BrokerLogsHandler(ToolHandler):
    name = "get_mt5_broker_logs"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_mt5_broker_logs(args, session=session, executor=executor, **kwargs)


@register_tool("get_mt5_terminal_info", aliases=["mt5_terminal_info", "algo_trading_status"], category="SYSTEM", parallel_safe=True)
class GetMt5TerminalInfoHandler(ToolHandler):
    name = "get_mt5_terminal_info"
    category = "SYSTEM"
    parallel_safe = True

    async def execute(self, args: Dict[str, Any], session: AsyncSession, executor: Optional[Any] = None, **kwargs) -> Any:
        return await handle_get_mt5_terminal_info(args, session=session, executor=executor, **kwargs)
