# ==============================================================================
# File: analysis/mcp/mcp_schema_cache.py
# ==============================================================================

"""
MCP Tool Schema Disk Cache with SHA-256 Configuration Fingerprinting.
Provides instantaneous tool registration and lazy-boot capabilities without
awaiting slow external process handshakes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("TradingAgent.MCP.SchemaCache")

DEFAULT_SCHEMA_CACHE_DIR = "data/cache/mcp_schemas"


class McpSchemaCache:
    """
    Manages persistent JSON caching of MCP tool definitions.
    Uses SHA-256 fingerprinting of the server configuration to invalidate
    stale cached schemas when command, arguments, or environment changes.
    """

    def __init__(self, cache_dir: str = DEFAULT_SCHEMA_CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(self.cache_dir, exist_ok=True)

    @classmethod
    def compute_config_hash(cls, server_config: Dict[str, Any]) -> str:
        """Computes a deterministic SHA-256 fingerprint of the server configuration."""
        normalized = {
            "command": server_config.get("command"),
            "args": server_config.get("args"),
            "url": server_config.get("url"),
            "transport": server_config.get("transport", "stdio"),
            "env_keys": sorted(list(server_config.get("env", {}).keys())),
        }
        raw = json.dumps(normalized, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_cached_tools(
        self, server_name: str, server_config: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieves cached tool definitions if the configuration fingerprint matches.
        Returns None if cache is missing, corrupted, or stale.
        """
        cache_file = os.path.join(self.cache_dir, f"{server_name}.json")
        if not os.path.exists(cache_file):
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            expected_hash = self.compute_config_hash(server_config)
            if data.get("config_hash") != expected_hash:
                logger.debug(
                    f"[McpSchemaCache] Config fingerprint mismatch for '{server_name}'. Cache invalidated."
                )
                return None

            tools = data.get("tools")
            if isinstance(tools, list):
                logger.debug(
                    f"[McpSchemaCache] Cache hit for '{server_name}': loaded {len(tools)} tools."
                )
                return tools
            return None
        except Exception as exc:
            logger.debug(f"[McpSchemaCache] Failed reading cache for '{server_name}': {exc}")
            return None

    def save_cached_tools(
        self,
        server_name: str,
        server_config: Dict[str, Any],
        tools: List[Dict[str, Any]],
    ) -> None:
        """Saves tool definitions to disk tagged with current config fingerprint."""
        cache_file = os.path.join(self.cache_dir, f"{server_name}.json")
        try:
            payload = {
                "server_name": server_name,
                "config_hash": self.compute_config_hash(server_config),
                "cached_at": time.time(),
                "tools": tools,
            }
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.debug(f"[McpSchemaCache] Saved {len(tools)} tools for '{server_name}' to cache.")
        except Exception as exc:
            logger.debug(f"[McpSchemaCache] Failed writing cache for '{server_name}': {exc}")
