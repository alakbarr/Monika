# ==============================================================================
# File: scheduler/digest_slice_scheduler.py
# ==============================================================================

"""
Digest Slice Scheduler: Menjalankan snapshot berkala berita setiap 2 jam.
Mendukung eksekusi terjadwal dan eksekusi event-driven (misal saat BREAKING news).
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from database.db import get_session
from database.models import NewsDigestSlice
from analysis.prefetch.digest_slice_generator import DigestSliceGenerator
from sqlalchemy import select, func

logger = logging.getLogger("TradingAgent.DigestSliceScheduler")


class DigestSliceScheduler:
    """Scheduler background untuk membuat NewsDigestSlice setiap 2 jam."""

    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings or {}
        sched_cfg = self.settings.get('news_classification', {}).get('slice_schedule', {})
        self.interval_minutes: int = sched_cfg.get('interval_minutes', 120)  # Default 2 jam
        self.slice_generator = DigestSliceGenerator(self.settings)
        self._running = False
        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    async def run_once(self, session, trigger: str = 'scheduled') -> Optional[NewsDigestSlice]:
        """Menjalankan satu kali pembuatan slice berita."""
        now_utc = datetime.now(timezone.utc)
        period_start = now_utc - timedelta(minutes=self.interval_minutes)

        # Cek apakah sudah ada slice yang dibuat sangat baru (kurang dari 30 menit) jika trigger='scheduled'
        if trigger == 'scheduled':
            recent_slice_cnt = (await session.execute(
                select(func.count(NewsDigestSlice.id))
                .where(NewsDigestSlice.generated_at >= now_utc - timedelta(minutes=30))
            )).scalar_one_or_none() or 0
            if recent_slice_cnt > 0:
                logger.debug("[DigestSliceScheduler] Slice already generated within last 30 minutes, skipping scheduled tick.")
                return None

        try:
            slice_entry = await self.slice_generator.generate_slice(
                session=session,
                period_start=period_start,
                period_end=now_utc,
                trigger=trigger
            )
            return slice_entry
        except Exception as e:
            logger.error(f"[DigestSliceScheduler] Failed to generate slice: {e}", exc_info=True)
            return None

    async def start(self):
        """Memulai background loop."""
        self._running = True
        logger.info(f"[DigestSliceScheduler] Started. Interval: {self.interval_minutes} minutes.")
        
        # Initial run on startup if no slice exists in last 2 hours
        async with get_session() as session:
            try:
                two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
                recent = (await session.execute(
                    select(NewsDigestSlice).where(NewsDigestSlice.generated_at >= two_hours_ago).limit(1)
                )).scalar_one_or_none()
                if not recent:
                    logger.info("[DigestSliceScheduler] No slice in last 2 hours on startup. Generating initial slice...")
                    await self.run_once(session, trigger='startup')
            except Exception as e:
                logger.warning(f"[DigestSliceScheduler] Startup slice check failed: {e}")

        while self._running:
            try:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_minutes * 60)
                    break
                except asyncio.TimeoutError:
                    pass
                if not self._running:
                    break
                async with get_session() as session:
                    await self.run_once(session, trigger='scheduled')
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[DigestSliceScheduler] Error in background loop: {e}")
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=60)
                    break
                except asyncio.TimeoutError:
                    pass

    def stop(self):
        """Menghentikan scheduler."""
        self._running = False
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("[DigestSliceScheduler] Stopped.")
