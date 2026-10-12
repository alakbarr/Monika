# ==============================================================================
# File: utils/infra/discord_notifier.py
# ==============================================================================

"""
Discord Webhook Notifier & Rich Embed Dispatcher (Async).
Provides multi-channel broadcast for trade fills, order status changes,
risk breaches, and system health alerts to Discord channels via webhooks (Q134).
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp
import utils.clock as clock

logger = logging.getLogger("TradingAgent.DiscordNotifier")


class DiscordNotifier:
    """Dispatches rich embeds and trade alerts to Discord via webhooks."""

    def __init__(self, webhook_url: Optional[str] = None, enabled: Optional[bool] = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL", "")
        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = bool(self.webhook_url)

    @classmethod
    def from_settings(cls, settings: Optional[dict] = None) -> "DiscordNotifier":
        """Instantiate from settings.yaml notifications.discord section."""
        cfg = (settings or {}).get("notifications", {}).get("discord", {})
        url = cfg.get("webhook_url") or os.getenv("DISCORD_WEBHOOK_URL", "")
        enabled = cfg.get("enabled", bool(url))
        return cls(webhook_url=url, enabled=enabled)

    async def send_message(self, content: str) -> bool:
        """Send a plain text message to the Discord webhook."""
        if not self.enabled or not self.webhook_url:
            return False

        payload = {"content": content}
        return await self._dispatch(payload)

    async def send_embed(
        self,
        title: str,
        description: str,
        color: int = 0x3498DB,  # Blue default
        fields: Optional[List[Dict[str, Any]]] = None,
        footer: str = "Monika Trading Desk",
    ) -> bool:
        """Send a formatted embed card."""
        if not self.enabled or not self.webhook_url:
            return False

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": clock.now().isoformat(),
            "footer": {"text": footer},
        }
        if fields:
            embed["fields"] = fields

        payload = {"embeds": [embed]}
        return await self._dispatch(payload)

    async def send_trade_alert(self, trade_data: Dict[str, Any]) -> bool:
        """
        Dispatches a standardized trade execution alert.
        trade_data: {symbol, direction, volume, price, sl, tp, ticket, pnl, event_type}
        """
        if not self.enabled or not self.webhook_url:
            return False

        symbol = trade_data.get("symbol", "UNKNOWN")
        direction = str(trade_data.get("direction", "BUY")).upper()
        volume = trade_data.get("volume", 0.0)
        price = trade_data.get("price", 0.0)
        sl = trade_data.get("sl")
        tp = trade_data.get("tp")
        ticket = trade_data.get("ticket", "-")
        event = trade_data.get("event_type", "ORDER_EXECUTED")

        # Color: Green (0x2ECC71) for BUY, Red (0xE74C3C) for SELL/CLOSED
        color = 0x2ECC71 if direction == "BUY" else 0xE74C3C
        title = f"🔔 Trade Alert: {event} | {symbol} {direction}"
        desc = f"Order **#{ticket}** for **{volume:.2f} lots** of **{symbol}** filled at **{price:.5f}**."

        fields = [
            {"name": "Symbol", "value": str(symbol), "inline": True},
            {"name": "Direction", "value": direction, "inline": True},
            {"name": "Volume", "value": f"{volume:.2f} Lots", "inline": True},
            {"name": "Price", "value": f"{price:.5f}", "inline": True},
            {"name": "Stop Loss", "value": f"{sl}" if sl else "None", "inline": True},
            {"name": "Take Profit", "value": f"{tp}" if tp else "None", "inline": True},
        ]

        if "pnl" in trade_data:
            pnl_val = trade_data["pnl"]
            fields.append({"name": "Realized PnL", "value": f"${pnl_val:+,.2f}", "inline": True})

        return await self.send_embed(title=title, description=desc, color=color, fields=fields)

    async def send_risk_alert(self, title: str, details: str, severity: str = "HIGH") -> bool:
        """Dispatch critical risk or circuit breaker alert."""
        if not self.enabled or not self.webhook_url:
            return False

        color = 0xE67E22 if severity == "MEDIUM" else 0x992D22  # Orange or Dark Red
        embed_title = f"⚠️ [RISK ALERT - {severity}] {title}"
        fields = [
            {"name": "Severity", "value": severity, "inline": True},
            {"name": "System Time", "value": clock.now().strftime("%Y-%m-%d %H:%M:%S UTC"), "inline": True},
        ]
        return await self.send_embed(title=embed_title, description=details, color=color, fields=fields)

    async def _dispatch(self, payload: dict) -> bool:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10.0)) as resp:
                    if resp.status in (200, 204):
                        return True
                    else:
                        text = await resp.text()
                        logger.warning(f"[DiscordNotifier] Webhook returned status {resp.status}: {text}")
                        return False
        except Exception as e:
            logger.error(f"[DiscordNotifier] Webhook dispatch error: {e}")
            return False
