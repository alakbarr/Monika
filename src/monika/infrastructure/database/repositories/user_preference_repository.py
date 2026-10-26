# ==============================================================================
# File: infrastructure/database/repositories/user_preference_repository.py
# ==============================================================================

"""
SQLAlchemy User Preference Repository.

Encapsulates database access and resolution for user preferences, custom
constraints, and persistent chart workspace layouts.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.ports.repository import UserPreferenceRepositoryPort
from monika.infrastructure.database.models import UserPreference

logger = logging.getLogger("TradingAgent.Infrastructure.UserPreferenceRepository")

CHART_WORKSPACE_CATEGORY: str = "chart_workspace"


def _normalize_chart_workspace(raw: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Fallback normalizer for chart workspace configs when indicators module is loaded dynamically."""
    try:
        import monika.domain.indicators.technical as _indicators_tech

        norm_fn = getattr(_indicators_tech, "normalize_chart_workspace_config", None)
        if callable(norm_fn):
            res = norm_fn(raw)
            if isinstance(res, dict):
                return res
    except ImportError, AttributeError:
        pass

    cfg = dict(raw or {})
    cfg.setdefault("scope", "global")
    cfg.setdefault("symbol", "")
    cfg.setdefault("timeframe", "H1")
    cfg.setdefault("indicators", {})
    cfg.setdefault("overlays", {})
    return cfg


def normalize_chart_workspace_config(raw: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Normalize a chart workspace configuration dictionary, preserving scope and symbol."""
    norm = _normalize_chart_workspace(raw)
    if isinstance(raw, dict):
        if "scope" in raw:
            norm["scope"] = raw["scope"]
        if "symbol" in raw:
            norm["symbol"] = raw["symbol"]
    return norm


class SqlAlchemyUserPreferenceRepository(UserPreferenceRepositoryPort):
    """
    SQLAlchemy repository implementation for user preferences and chart workspace layouts.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_preference(
        self,
        category: str,
        key: str,
        user_id: str = "default",
    ) -> Optional[dict[str, Any]]:
        """Fetch a specific preference by category and key."""
        stmt = (
            select(UserPreference)
            .where(
                UserPreference.user_id == user_id,
                UserPreference.category == category,
                UserPreference.key == key,
                UserPreference.is_active.is_(True),
            )
            .order_by(UserPreference.updated_at.desc())
        )
        res = await self._session.execute(stmt)
        pref = res.scalars().first()
        if pref is None or not pref.value_json:
            return None
        try:
            loaded = json.loads(pref.value_json)
            if isinstance(loaded, dict):
                return loaded
            return {"value": loaded}
        except json.JSONDecodeError, TypeError:
            return None

    async def set_preference(
        self,
        category: str,
        key: str,
        value: dict[str, Any],
        user_id: str = "default",
    ) -> dict[str, Any]:
        """Save or update a preference for a category and key."""
        stmt = (
            select(UserPreference)
            .where(
                UserPreference.user_id == user_id,
                UserPreference.category == category,
                UserPreference.key == key,
            )
            .order_by(UserPreference.updated_at.desc())
        )
        res = await self._session.execute(stmt)
        existing = res.scalars().first()
        now = datetime.now(UTC)
        if existing is not None:
            existing.value_json = json.dumps(value)
            existing.is_active = True
            existing.updated_at = now
        else:
            new_pref = UserPreference(
                user_id=user_id,
                category=category,
                key=key,
                value_json=json.dumps(value),
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            self._session.add(new_pref)
        await self._session.flush()
        return value

    async def delete_preference(
        self,
        category: str,
        key: str,
        user_id: str = "default",
    ) -> bool:
        """Delete matching preference row(s) or deactivate them, flushing changes."""
        stmt = select(UserPreference).where(
            UserPreference.user_id == user_id,
            UserPreference.category == category,
            UserPreference.key == key,
        )
        res = await self._session.execute(stmt)
        rows = list(res.scalars().all())
        if not rows:
            return False
        for row in rows:
            await self._session.delete(row)
        await self._session.flush()
        return True

    async def list_preferences(
        self,
        category: str,
        user_id: str = "default",
    ) -> dict[str, dict[str, Any]]:
        """List all active preferences within a category."""
        stmt = (
            select(UserPreference)
            .where(
                UserPreference.user_id == user_id,
                UserPreference.category == category,
                UserPreference.is_active.is_(True),
            )
            .order_by(UserPreference.updated_at.asc())
        )
        res = await self._session.execute(stmt)
        prefs: dict[str, dict[str, Any]] = {}
        for row in res.scalars().all():
            try:
                loaded = json.loads(row.value_json)
                if isinstance(loaded, dict):
                    prefs[row.key] = loaded
                else:
                    prefs[row.key] = {"value": loaded}
            except json.JSONDecodeError, TypeError:
                continue
        return prefs

    async def resolve_chart_workspace_config(
        self,
        symbol: Optional[str] = None,
        user_id: str = "default",
    ) -> dict[str, Any]:
        """Resolve effective chart workspace configuration for symbol or fallback to global."""
        if symbol:
            sym_upper = symbol.strip().upper()
            raw_sym = await self.get_preference(
                category=CHART_WORKSPACE_CATEGORY,
                key=sym_upper,
                user_id=user_id,
            )
            if raw_sym is not None:
                return normalize_chart_workspace_config({**raw_sym, "scope": "symbol", "symbol": sym_upper})

        raw_global = await self.get_preference(
            category=CHART_WORKSPACE_CATEGORY,
            key="global",
            user_id=user_id,
        )
        if raw_global is not None:
            return normalize_chart_workspace_config(
                {**raw_global, "scope": "global", "symbol": (symbol or "").strip().upper()}
            )

        return normalize_chart_workspace_config({"scope": "global", "symbol": (symbol or "").strip().upper()})

    async def get_chart_workspace_bundle(
        self,
        user_id: str = "default",
    ) -> dict[str, Any]:
        """Return global config and all symbol override configs as a bundle."""
        all_prefs = await self.list_preferences(CHART_WORKSPACE_CATEGORY, user_id=user_id)
        raw_global = all_prefs.get("global", {})
        global_cfg = normalize_chart_workspace_config({**raw_global, "scope": "global", "symbol": ""})

        symbol_map: dict[str, dict[str, Any]] = {}
        for key, raw_val in all_prefs.items():
            if key.lower() == "global":
                continue
            sym = key.strip().upper()
            symbol_map[sym] = normalize_chart_workspace_config({**raw_val, "scope": "symbol", "symbol": sym})

        return {
            "global": global_cfg,
            "symbols": symbol_map,
            "symbol_overrides": symbol_map,
        }
