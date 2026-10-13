"""
System Config Repository.

Encapsulates database access for dynamic runtime configurations and safety flags.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from monika.domain.ports.repository import SystemConfigRepositoryPort
from monika.infrastructure.database.models import SystemConfig


class SystemConfigRepository(SystemConfigRepositoryPort):
    """Repository managing SystemConfig key-value persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Fetch raw string configuration value by key."""
        stmt = select(SystemConfig.value).where(SystemConfig.key == key)
        res = await self.session.execute(stmt)
        val = res.scalar_one_or_none()
        return val if val is not None else default

    async def get_bool(self, key: str, default: bool = False) -> bool:
        """Fetch configuration value parsed as boolean."""
        val = await self.get(key)
        if val is None:
            return default
        return val.strip().lower() in ("true", "1", "yes", "on", "active")

    async def set(self, key: str, value: str, description: Optional[str] = None) -> SystemConfig:
        """Upsert a configuration entry atomically."""
        return await SystemConfig.upsert(self.session, key=key, value=value, description=description)

    async def is_kill_switch_active(self) -> bool:
        """Check whether the global emergency kill switch is engaged."""
        return await self.get_bool("kill_switch", default=False)

    async def set_kill_switch(self, active: bool) -> None:
        """Engage or disengage the global emergency kill switch."""
        await self.set("kill_switch", "true" if active else "false", description="Emergency kill switch status")

    async def is_system_paused(self) -> bool:
        """Check whether trading operations are temporarily paused."""
        return await self.get_bool("system_paused", default=False)

    async def set_system_paused(self, paused: bool) -> None:
        """Pause or unpause trading operations."""
        await self.set("system_paused", "true" if paused else "false", description="Trading operation pause status")

    async def get_risk_override(self) -> Optional[str]:
        """Fetch active risk override payload if configured."""
        return await self.get("risk_override")

    async def set_risk_override(self, override_json: Optional[str]) -> None:
        """Set or clear dynamic risk parameter override."""
        await self.set("risk_override", override_json or "", description="Dynamic risk threshold override")
