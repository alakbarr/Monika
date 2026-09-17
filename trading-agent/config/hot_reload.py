import os
import yaml
import asyncio
import logging
from typing import Optional

logger = logging.getLogger("TradingAgent.ConfigHotReload")


class RiskParameterReloader:
    """Watches configuration file for changes and updates RiskGate parameters dynamically."""

    def __init__(
        self,
        config_path: str,
        risk_gate,
        notifier=None,
        check_interval_seconds: float = 10.0
    ):
        self.config_path = config_path
        self.risk_gate = risk_gate
        self.notifier = notifier
        self.check_interval_seconds = check_interval_seconds
        self.last_mtime: Optional[float] = None
        if os.path.exists(self.config_path):
            try:
                self.last_mtime = os.path.getmtime(self.config_path)
            except Exception:
                pass

    def check_and_reload(self) -> bool:
        """Check if file was modified and reload parameters. Returns True if reloaded."""
        if not os.path.exists(self.config_path):
            return False

        try:
            current_mtime = os.path.getmtime(self.config_path)
            if self.last_mtime is not None and current_mtime <= self.last_mtime:
                return False

            with open(self.config_path, "r", encoding="utf-8") as f:
                new_config = yaml.safe_load(f)

            if new_config and isinstance(new_config, dict):
                # Extract risk section and validate
                risk_dict = (
                    new_config.get("trading", {}).get("risk", {})
                    if "trading" in new_config
                    else new_config.get("risk", new_config)
                )
                try:
                    try:
                        from config.schemas import RiskConfig
                    except ImportError:
                        from .schemas import RiskConfig
                    RiskConfig.model_validate(risk_dict)
                except Exception as val_err:
                    logger.warning(
                        f"[HotReload] Validation failed for new risk config in {self.config_path}, "
                        f"rejecting reload: {val_err}"
                    )
                    return False

                self.risk_gate.update_parameters(new_config)
                self.last_mtime = current_mtime
                logger.info(f"[HotReload] Reloaded risk parameters from {self.config_path}")
                if self.notifier and hasattr(self.notifier, "send_info"):
                    try:
                        asyncio.create_task(self.notifier.send_info("Risk parameters hot-reloaded."))
                    except Exception:
                        pass
                return True
        except Exception as e:
            logger.error(f"[HotReload] Error reloading config from {self.config_path}: {e}")
        return False

    async def watch_and_reload(self, shutdown_event: Optional[asyncio.Event] = None):
        """Continuous background task watching config file."""
        while shutdown_event is None or not shutdown_event.is_set():
            try:
                self.check_and_reload()
            except Exception as e:
                logger.debug(f"[HotReload] Watcher cycle error: {e}")

            try:
                await asyncio.sleep(self.check_interval_seconds)
            except asyncio.CancelledError:
                break
