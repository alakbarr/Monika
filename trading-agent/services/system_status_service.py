# ==============================================================================
# File: services/system_status_service.py
# ==============================================================================

"""
System Status Application Service.
Provides unified health checks, component availability, and plugin telemetry
for CLI, Telegram Bot, and Dashboard.
"""

from typing import Dict, Any, List, Optional
import logging

from utils.infra.container import ServiceContainer, get_container
from harness.engine import PluginEngine

logger = logging.getLogger("TradingAgent.Services.SystemStatus")


class SystemStatusService:
    """Consolidates system observability and component state queries."""

    @staticmethod
    def get_system_health(
        container: Optional[ServiceContainer] = None,
        engine: Optional[PluginEngine] = None,
    ) -> Dict[str, Any]:
        """Aggregate health across container services, plugins, and execution channels."""
        c = container or get_container()
        pe = engine or PluginEngine.get_instance()

        mt5_client = c.get("mt5_client")
        mt5_connected = getattr(mt5_client, "connected", False) if mt5_client else False

        execution_service = c.get("execution_service")
        paper_mode = getattr(execution_service, "paper_trading", True) if execution_service else True

        plugins_count = len(pe.registry) if pe else 0
        plugins_running = len([p for p in pe.ordered_plugins if p.status == "RUNNING"]) if pe else 0

        return {
            "status": "HEALTHY" if (mt5_connected or paper_mode) else "DEGRADED",
            "broker": {
                "type": "paper" if paper_mode else "mt5_live",
                "connected": mt5_connected,
            },
            "plugins": {
                "total": plugins_count,
                "running": plugins_running,
            },
            "environment": {
                "paper_trading": paper_mode,
            }
        }

    @staticmethod
    def get_plugin_summary(engine: Optional[PluginEngine] = None) -> List[Dict[str, Any]]:
        """Return a structured summary of all registered plugins."""
        pe = engine or PluginEngine.get_instance()
        if not pe:
            return []

        summary = []
        for p in pe.ordered_plugins:
            summary.append({
                "id": p.metadata.id,
                "name": p.metadata.name,
                "version": p.metadata.version,
                "category": getattr(p.metadata.category, "value", str(p.metadata.category)),
                "enabled": p.is_enabled,
                "status": getattr(p, "status", "UNKNOWN"),
                "is_core": p.metadata.is_core,
            })
        return summary
