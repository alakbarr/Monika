import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from monika.infrastructure.database.models import ActivityLog
from monika.infrastructure.providers.llm_factory import get_client_for_task

logger = logging.getLogger("TradingAgent.MemoryCompressor")


async def compress_agent_memory(session: AsyncSession, settings: Optional[dict] = None) -> None:
    """
    Compresses ActivityLog older than 7 days by categorizing and summarizing them.
    Stores the compressed memory as a new log and archives raw logs to preserve audit trails.
    """
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=7)

        # Get logs older than cutoff, ignore already compressed or archived logs
        query = (
            select(ActivityLog)
            .where(
                ActivityLog.timestamp < cutoff,
                ActivityLog.category != "compressed_memory",
                ActivityLog.category != "archived_activity_log",
            )
            .order_by(ActivityLog.category)
        )

        result = await session.execute(query)
        logs = result.scalars().all()

        if not logs:
            logger.info("No old logs found to compress.")
            return

        # Group by category
        grouped_logs = {}
        for log in logs:
            grouped_logs.setdefault(log.category, []).append(log.description)

        logger.info(f"Compressing {len(logs)} old logs across {len(grouped_logs)} categories...")

        # We use the summarizer role for log summarization
        settings = settings or {}
        client = get_client_for_task("summarizer", settings)

        for category, descriptions in grouped_logs.items():
            if len(descriptions) == 0:
                continue

            raw_text = "\n".join(descriptions)

            # If the text is very short, no need to compress it much, but let's do it anyway to consolidate rows
            sys_prompt = "You are an AI assistant specialized in compressing log data. Summarize the key lessons and events from these logs. Be concise and keep actionable insights."
            user_msg = f"Category: {category}\nLogs:\n{raw_text}"

            summary = await client.generate_content(system_prompt=sys_prompt, user_message=user_msg, temperature=0.1)

            if not summary:
                logger.warning(f"Failed to summarize category {category}, skipping.")
                continue

            # Create compressed log
            compressed_log = ActivityLog(
                description=f"Compressed Memory ({category}):\n{summary}",
                category="compressed_memory",
                actor="memory_compressor",
            )
            session.add(compressed_log)

        # Archive old raw logs to retain audit trail per AGENTS.md §1 unless hard delete is explicitly requested
        delete_raw = bool((settings or {}).get("memory", {}).get("delete_raw_logs", False))
        if delete_raw:
            delete_query = delete(ActivityLog).where(
                ActivityLog.timestamp < cutoff,
                ActivityLog.category != "compressed_memory",
                ActivityLog.category != "archived_activity_log",
            )
            await session.execute(delete_query)
            logger.info("Successfully compressed agent memory and purged raw logs.")
        else:
            archive_query = (
                update(ActivityLog)
                .where(
                    ActivityLog.timestamp < cutoff,
                    ActivityLog.category != "compressed_memory",
                    ActivityLog.category != "archived_activity_log",
                )
                .values(category="archived_activity_log")
            )
            await session.execute(archive_query)
            logger.info("Successfully compressed agent memory and archived raw logs.")

        await session.commit()

    except Exception as e:
        logger.error(f"Error compressing memory: {e}")
        await session.rollback()
