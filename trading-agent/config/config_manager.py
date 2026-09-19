"""
File: config/config_manager.py
Universal Subsystem Hot-Reload Manager and Event Bus for Monika.
Allows zero-downtime reconfiguration of risk parameters, LLM model roles,
scheduler intervals, and scraping sources across all 18+ async background tasks.
"""

import os
import yaml
import logging
import asyncio
from typing import Dict, Any, Callable, List, Optional, Set
from pathlib import Path

logger = logging.getLogger("TradingAgent.ConfigManager")


class ConfigManager:
    """Central configuration event bus and hot-reload supervisor."""

    _instance: Optional["ConfigManager"] = None
    _subscribers: Dict[str, List[Callable[[Dict[str, Any]], None]]] = {}
    _last_mtimes: Dict[str, float] = {}
    _is_watching: bool = False
    _watch_task: Optional[asyncio.Task] = None

    def __init__(self, config_paths: Optional[List[str]] = None):
        self.config_paths = config_paths or ["config/settings.yaml"]
        self._record_mtimes()

    @classmethod
    def get_instance(cls, config_paths: Optional[List[str]] = None) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = ConfigManager(config_paths)
        return cls._instance

    def _record_mtimes(self) -> None:
        for p in self.config_paths:
            if os.path.exists(p):
                try:
                    self._last_mtimes[p] = os.path.getmtime(p)
                except Exception:
                    pass

    @classmethod
    def subscribe(cls, topic: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribes a subsystem callback to a config topic (e.g. 'risk', 'llm', 'scheduler')."""
        cls._subscribers.setdefault(topic, []).append(callback)
        logger.debug(f"Subscribed callback to config topic: {topic}")

    @classmethod
    def publish(cls, topic: str, payload: Dict[str, Any]) -> None:
        """Notifies all subscribers of a configuration change."""
        subscribers = cls._subscribers.get(topic, [])
        for cb in subscribers:
            try:
                cb(payload)
            except Exception as err:
                logger.error(f"Error in config subscriber ({topic}): {err}", exc_info=True)

    def check_for_updates(self) -> Dict[str, Any]:
        """Checks if any configuration files were modified, reloads, and publishes diffs."""
        from config.settings import load_settings

        changed = False
        for p in self.config_paths:
            if os.path.exists(p):
                try:
                    current_mtime = os.path.getmtime(p)
                    if current_mtime > self._last_mtimes.get(p, 0.0):
                        self._last_mtimes[p] = current_mtime
                        changed = True
                except Exception:
                    pass

        if not changed:
            return {}

        logger.info("Configuration file modification detected. Reloading and dispatching events...")
        try:
            new_settings = load_settings(validate=True, return_model=False)
        except Exception as err:
            logger.error(f"Reload failed due to invalid configuration: {err}")
            return {}

        # Broadcast domain-specific topics
        if "trading" in new_settings and "risk" in new_settings["trading"]:
            self.publish("risk", new_settings["trading"]["risk"])

        if "llm" in new_settings:
            self.publish("llm", new_settings["llm"])

        if "scheduler" in new_settings:
            self.publish("scheduler", new_settings["scheduler"])

        if "scraping" in new_settings:
            self.publish("scraping", new_settings["scraping"])

        self.publish("all", new_settings)
        return new_settings

    async def start_watcher(self, interval_seconds: float = 3.0) -> None:
        """Starts background watcher task for real-time config reloads."""
        if self._is_watching:
            return
        self._is_watching = True

        async def _loop():
            while self._is_watching:
                try:
                    self.check_for_updates()
                except Exception as e:
                    logger.debug(f"Config watcher loop error: {e}")
                await asyncio.sleep(interval_seconds)

        self._watch_task = asyncio.create_task(_loop())
        logger.info(f"ConfigManager file watcher started (poll interval: {interval_seconds}s)")

    def stop_watcher(self) -> None:
        """Stops background file watcher."""
        self._is_watching = False
        if self._watch_task:
            self._watch_task.cancel()
            self._watch_task = None
        logger.info("ConfigManager file watcher stopped")
