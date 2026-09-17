"""
File: trading-agent/agent/monitors/scraper_loop.py
Scraper background loop and news digest classification.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("TradingAgent.ScraperLoop")


async def run_scraper_loop(agent: Any) -> None:
    """Scraper background loop (interval: 1h, Stage 2 every 2h)."""
    logger.info("Scraper background loop started (interval: 1h, Stage 2 every 2h)")
    from database.db import get_session as _gs_scraper
    from database.models import SystemConfig
    from sqlalchemy import select as _sel_scraper

    min_interval_minutes = agent.settings.get("scraping", {}).get("min_interval_minutes", 45)
    cycle_count = 0

    while not agent.shutdown_event.is_set():
        try:
            is_weekend = datetime.now(timezone.utc).weekday() >= 5
            eff_min_interval = 240 if is_weekend else min_interval_minutes
            skip_scrape = False
            async with _gs_scraper() as chk_session:
                cfg = (
                    await chk_session.execute(
                        _sel_scraper(SystemConfig).where(SystemConfig.key == "last_scraper_run_at")
                    )
                ).scalar_one_or_none()
                if cfg and cfg.value:
                    try:
                        last_run = datetime.fromisoformat(cfg.value)
                        if last_run.tzinfo is None:
                            last_run = last_run.replace(tzinfo=timezone.utc)
                        minutes_since = (datetime.now(timezone.utc) - last_run).total_seconds() / 60
                        if minutes_since < eff_min_interval:
                            skip_scrape = True
                            logger.info(
                                f"Scraper loop: scrape terakhir {minutes_since:.0f}menit lalu "
                                f"(< {eff_min_interval}menit{' [weekend]' if is_weekend else ''}) — skip scraping pass ini."
                            )
                    except Exception:
                        pass

            if not skip_scrape:
                from scheduler.scraper_runner import ScraperRunner

                runner = ScraperRunner(agent.settings)
                agent._active_scraper_runner = runner
                try:
                    await runner.run_all()
                finally:
                    runner.stop()
                    agent._active_scraper_runner = None

                async with _gs_scraper() as save_session:
                    cfg = (
                        await save_session.execute(
                            _sel_scraper(SystemConfig).where(SystemConfig.key == "last_scraper_run_at")
                        )
                    ).scalar_one_or_none()
                    now_iso = datetime.now(timezone.utc).isoformat()
                    if cfg:
                        cfg.value = now_iso
                    else:
                        save_session.add(SystemConfig(key="last_scraper_run_at", value=now_iso))
                    await save_session.commit()

            from analysis.prefetch.news_digest import NewsDigestProcessor
            from database.db import get_session

            processor = NewsDigestProcessor(agent.settings)
            async with get_session() as session:
                await processor.classify_unscored_news(session, hours_back=2)
                cycle_count += 1
                if cycle_count % 2 == 0:
                    logger.info(f"Running Stage 2 News Digest (cycle {cycle_count})")
                    await processor.create_news_digest(session, hours_back=12)
        except Exception as e:
            logger.error(f"Scraper loop error (non-fatal): {e}")

        try:
            await asyncio.wait_for(agent.shutdown_event.wait(), timeout=3600)
        except asyncio.TimeoutError:
            pass
