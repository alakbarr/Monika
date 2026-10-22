import asyncio
import logging
import os
from typing import Any, Optional

import yaml

logger = logging.getLogger("TradingAgent.ConfigHotReload")


class ConfigReloader:
    """Watches configuration file for changes and updates subscribing components dynamically (Phase 6.1)."""

    def __init__(
        self,
        config_path: str,
        risk_gate=None,
        notifier=None,
        check_interval_seconds: float = 10.0,
        subscribers: list | None = None,
    ):
        self.config_path = config_path
        self.risk_gate = risk_gate
        self.notifier = notifier
        self.check_interval_seconds = check_interval_seconds
        self.subscribers = list(subscribers or [])
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self.last_mtime: float | None = None
        if os.path.exists(self.config_path):
            try:
                self.last_mtime = os.path.getmtime(self.config_path)
            except Exception:
                pass

    def subscribe(self, callback) -> None:
        """Register a subscriber callback or object with on_config_reloaded."""
        if callback not in self.subscribers:
            self.subscribers.append(callback)

    def check_and_reload(self) -> bool:
        """Check if file was modified and reload parameters. Returns True if reloaded."""
        if not os.path.exists(self.config_path):
            return False

        try:
            current_mtime = os.path.getmtime(self.config_path)
            if self.last_mtime is not None and current_mtime <= self.last_mtime:
                return False

            try:
                from monika.core.config.settings import load_settings

                new_config = load_settings(self.config_path)
            except Exception as load_err:
                logger.debug(f"[HotReload] load_settings fallback to yaml.safe_load: {load_err}")
                with open(self.config_path, encoding="utf-8") as f:
                    new_config = yaml.safe_load(f)

            if new_config and isinstance(new_config, dict):
                # Extract risk section and validate
                trading_sec = new_config.get("trading")
                if isinstance(trading_sec, dict):
                    risk_dict = trading_sec.get("risk")
                else:
                    risk_dict = new_config.get("risk")

                if isinstance(risk_dict, dict) and risk_dict and self.risk_gate is not None:
                    try:
                        from monika.core.config.schemas import RiskConfig

                        RiskConfig.model_validate(risk_dict)
                    except Exception as val_err:
                        logger.warning(
                            f"[HotReload] Validation failed for new risk config in {self.config_path}, "
                            f"rejecting reload: {val_err}"
                        )
                        return False

                    self.risk_gate.update_parameters(new_config)
                    if hasattr(self.risk_gate, "settings") and isinstance(self.risk_gate.settings, dict):
                        if "agent_architecture" in new_config:
                            self.risk_gate.settings.setdefault("agent_architecture", {}).update(
                                new_config.get("agent_architecture", {})
                            )
                        if "trading" in new_config:
                            self.risk_gate.settings.setdefault("trading", {}).update(new_config.get("trading", {}))

                # Notify all subscribing components
                for sub in self.subscribers:
                    try:
                        if callable(sub):
                            sub(new_config)
                        elif hasattr(sub, "on_config_reloaded"):
                            sub.on_config_reloaded(new_config)
                    except Exception as sub_err:
                        logger.warning(f"[HotReload] Subscriber notification error: {sub_err}")

                self.last_mtime = current_mtime
                logger.info(f"[HotReload] Reloaded configuration from {self.config_path}")
                if self.notifier and hasattr(self.notifier, "send_info"):
                    try:
                        task = asyncio.create_task(self.notifier.send_info("Configuration hot-reloaded."))
                        self._background_tasks.add(task)
                        task.add_done_callback(self._background_tasks.discard)
                    except Exception:
                        pass
                return True
        except Exception as e:
            logger.error(f"[HotReload] Error reloading config from {self.config_path}: {e}")
        return False

    async def watch_and_reload(self, shutdown_event: asyncio.Event | None = None):
        """Continuous background task watching config file."""
        while shutdown_event is None or not shutdown_event.is_set():
            try:
                await asyncio.to_thread(self.check_and_reload)
            except Exception as e:
                logger.debug(f"[HotReload] Watcher cycle error: {e}")

            try:
                await asyncio.sleep(self.check_interval_seconds)
            except asyncio.CancelledError:
                break


class RiskParameterReloader(ConfigReloader):
    """Backward-compatible alias for ConfigReloader focusing on RiskGate."""

    pass


from monika.core.config.atomic_writer import AtomicConfigWriter

__all__ = [
    "ConfigReloader",
    "RiskParameterReloader",
    "AtomicConfigWriter",
]
