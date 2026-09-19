# ==============================================================================
# File: utils/notifier.py
# ==============================================================================

import os
import re
import asyncio
import logging
from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger("TradingAgent.Notifier")

import json
from pathlib import Path
from collections import deque
from typing import ClassVar

_OUTBOX_FILE = Path(__file__).parent.parent.parent / "data" / "notifier_outbox.json"

def sanitize_telegram_html(text: str) -> str:
    """
    Sanitizes arbitrary text containing Telegram HTML formatting.
    Escapes standalone '<', '>', and '&' that are not part of valid Telegram HTML tags
    (<b>, <strong>, <i>, <em>, <u>, <ins>, <s>, <strike>, <del>, <span>, <tg-spoiler>, <a>, <code>, <pre>, <blockquote>).
    """
    if not text or not isinstance(text, str):
        return ""
    tag_regex = re.compile(
        r'<\/?(?:b|strong|i|em|u|ins|s|strike|del|span|tg-spoiler|a|code|pre|blockquote)(?:\s+[^<>]*)?>',
        re.IGNORECASE
    )
    parts = []
    last_idx = 0
    for m in tag_regex.finditer(text):
        non_tag = text[last_idx:m.start()]
        non_tag = non_tag.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        non_tag = non_tag.replace('&amp;lt;', '&lt;').replace('&amp;gt;', '&gt;').replace('&amp;amp;', '&amp;')
        parts.append(non_tag)
        parts.append(m.group(0))
        last_idx = m.end()

    trailing = text[last_idx:]
    trailing = trailing.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    trailing = trailing.replace('&amp;lt;', '&lt;').replace('&amp;gt;', '&gt;').replace('&amp;amp;', '&amp;')
    parts.append(trailing)
    return "".join(parts)


class AgentNotifier:
    """Mengirim notifikasi atau alert kritis ke admin via Telegram dengan Outbox Retry Queue persisten."""
    _outbox: ClassVar[deque] = deque(maxlen=50)
    _loaded_from_disk: ClassVar[bool] = False

    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN") or None
        self.admin_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID") or None  # Fixed: was TELEGRAM_ADMIN_ID
        self.bot = Bot(token=self.token) if self.token else None
        self._ensure_loaded()

    @classmethod
    def _ensure_loaded(cls):
        if cls._loaded_from_disk:
            return
        cls._loaded_from_disk = True
        try:
            if _OUTBOX_FILE.exists():
                raw = _OUTBOX_FILE.read_text(encoding="utf-8")
                items = json.loads(raw)
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict) and "text" in item:
                            cls._outbox.append(item)
        except Exception as e:
            logger.debug(f"Could not load notifier outbox from disk: {e}")

    @classmethod
    def _save_outbox_to_disk(cls):
        try:
            _OUTBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = list(cls._outbox)
            _OUTBOX_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug(f"Could not save notifier outbox to disk: {e}")

    async def flush_outbox(self) -> int:
        """Mencoba mengirim ulang pesan-pesan yang tertunda di outbox saat koneksi pulih."""
        self._ensure_loaded()
        if not self.bot or not self.admin_id or not self._outbox:
            return 0
        sent_count = 0
        while self._outbox:
            item = self._outbox[0]
            msg_text = item.get("text")
            try:
                try:
                    clean_html = sanitize_telegram_html(msg_text)
                    await self.bot.send_message(chat_id=self.admin_id, text=clean_html, parse_mode="HTML")
                except TelegramError:
                    plain_text = re.sub(r'<[^>]+>', '', msg_text)
                    await self.bot.send_message(chat_id=self.admin_id, text=plain_text)
                self._outbox.popleft()
                sent_count += 1
                self._save_outbox_to_disk()
            except Exception as e:
                logger.debug(f"Outbox retry failed: {e}")
                break
        if sent_count > 0:
            logger.info(f"Successfully flushed {sent_count} pending alerts from outbox.")
        return sent_count

    async def flush_outbox_loop(self, interval_seconds: int = 60):
        """Background coroutine to periodically retry flushing pending outbox alerts."""
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self.flush_outbox()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Periodic outbox flusher encountered non-fatal error: {e}")

    async def _send(self, message: str, prefix: str = "", reply_markup=None):
        if not self.bot or not self.admin_id:
            logger.debug(f"Notifier skipping message (no token/admin): {message}")
            return
            
        full_msg = f"{prefix}\n{message}" if prefix else message
        # Flush any previously pending outbox messages first
        await self.flush_outbox()

        try:
            try:
                clean_html = sanitize_telegram_html(full_msg)
                send_kwargs = {"chat_id": self.admin_id, "text": clean_html, "parse_mode": "HTML"}
                if reply_markup is not None:
                    send_kwargs["reply_markup"] = reply_markup
                await self.bot.send_message(**send_kwargs)
            except TelegramError as e:
                logger.warning(f"HTML parse failed on Telegram notification ({e}), retrying plain text...")
                plain_text = re.sub(r'<[^>]+>', '', full_msg)
                plain_kwargs = {"chat_id": self.admin_id, "text": plain_text}
                if reply_markup is not None:
                    plain_kwargs["reply_markup"] = reply_markup
                await self.bot.send_message(**plain_kwargs)
            
            # Log to ActivityLog
            try:
                from database.db import get_session
                from database.models import ActivityLog
                
                async with get_session() as session:
                    clean_msg = re.sub(r'<[^>]+>', '', full_msg)
                    session.add(ActivityLog(
                        category="telegram",
                        description=clean_msg[:500],
                        actor="system",
                    ))
                    await session.commit()
            except Exception as log_err:
                logger.debug(f"Failed to log Telegram message to DB: {log_err}")
                
        except (TelegramError, Exception) as e:
            logger.error(f"Failed to send Telegram notification: {e}. Enqueuing to outbox.")
            self._outbox.append({"text": full_msg, "prefix": prefix})
            self._save_outbox_to_disk()

    async def send_critical(self, message):
        msg_str = str(message) if not isinstance(message, str) else message
        await self._send(msg_str, prefix="🚨 <b>CRITICAL ERROR</b> 🚨")

    async def send_warning(self, message):
        msg_str = str(message) if not isinstance(message, str) else message
        await self._send(msg_str, prefix="⚠️ <b>WARNING</b> ⚠️")

    async def send_info(self, message, reply_markup=None):
        msg_str = str(message) if not isinstance(message, str) else message
        await self._send(msg_str, prefix="ℹ️ <b>INFO</b>", reply_markup=reply_markup)

    async def send_proposal(self, message: str, reply_markup=None):
        """Send actionable trade proposal with interactive inline keyboard confirmation buttons."""
        msg_str = str(message) if not isinstance(message, str) else message
        await self._send(msg_str, prefix="", reply_markup=reply_markup)

    async def send_markdown(self, message):
        msg_str = str(message) if not isinstance(message, str) else message
        await self._send(msg_str, prefix="")

    async def send(self, message: str):
        """Mengirim pesan format kustom secara langsung tanpa prefix ganda."""
        msg_str = str(message) if not isinstance(message, str) else message
        await self._send(msg_str, prefix="")

    async def send_message(self, message: str):
        """Alias method untuk send()."""
        await self.send(message)

    async def send_alert(self, message: str):
        """Mengirim alert peringatan / degradasi sistem."""
        await self.send_warning(message)

    async def send_cycle_summary(self, summary: dict):
        lines = ["🔄 <b>CYCLE COMPLETE</b> 🔄"]
        if "elapsed_total_s" in summary:
            lines.append(f"⏱️ Duration: {summary['elapsed_total_s']:.1f}s")
        if "api_cost_usd" in summary:
            lines.append(f"💰 Cost: ${summary['api_cost_usd']:.4f}")
            
        assets = summary.get("per_asset", {})
        if assets:
            lines.append("\n<b>Decisions:</b>")
            for sym, r in assets.items():
                if isinstance(r, dict):
                    decision = r.get("decision", "unknown").upper()
                    conf = r.get("confidence", 0)
                    if decision == "SKIP":
                        reason = (
                            "cooldown" if r.get("skipped_by_cooldown")
                            else "prescreen" if r.get("skipped_by_prescreen")
                            else "data_quality" if r.get("skipped_by_data_quality")
                            else "weekend" if r.get("skipped_by_weekend_guard")
                            else "stale_brief" if r.get("skipped_by_brief_staleness")
                            else "no_brief" if r.get("skipped_no_brief")
                            else "bypassed"
                        )
                        lines.append(f"• {sym}: SKIP ({reason})")
                    else:
                        lines.append(f"• {sym}: {decision} (conf: {conf:.2f})")
                    
        await self._send("\n".join(lines))


def get_notifier() -> AgentNotifier:
    """Helper factory function to get an AgentNotifier instance."""
    return AgentNotifier()

