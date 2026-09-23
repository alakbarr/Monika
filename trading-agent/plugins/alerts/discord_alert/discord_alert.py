"""
Discord & Webhook Alert Channel Reference Plugin for Monika.
Demonstrates custom notification and risk alert dispatch plugin.
"""

from typing import Dict, Any, Optional


from harness.contract import (
    TradingPlugin,
    PluginMetadata,
    PluginCategory,
    PluginOrigin,
    OrderStateChangedEvent,
    RiskBreachEvent,
)


def dispatch_discord_alert(args: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatches formatted message payload to configured webhook channel."""
    channel = str(args.get("channel", "trading-alerts"))
    message = str(args.get("message", "Test alert notification"))
    level = str(args.get("level", "INFO")).upper()
    return {
        "status": "dispatched",
        "channel": channel,
        "level": level,
        "message_preview": message[:80],
    }


class DiscordAlertPlugin(TradingPlugin):
    """Notification plugin for dispatching trade execution alerts to Discord."""
    metadata = PluginMetadata(
        id="discord_alert_plugin",
        name="Discord Alert Plugin",
        version="1.0.0",
        category=PluginCategory.NOTIFICATION,
        description="Notification plugin for dispatching trade execution alerts to Discord",
        origin=PluginOrigin.LOCAL_DIRECTORY,
    )

    async def on_order_state(self, event: OrderStateChangedEvent) -> None:
        order_ref = event.order_id or event.symbol
        dispatch_discord_alert({
            "channel": self.config.get("channel", "trading-alerts"),
            "message": f"Order {order_ref} transition: {event.old_state} -> {event.new_state}",
            "level": "INFO",
        })

    async def on_risk_breach(self, event: RiskBreachEvent) -> None:
        dispatch_discord_alert({
            "channel": self.config.get("channel", "trading-alerts"),
            "message": f"RISK BREACH: {event.breach_type} on {event.symbol} (severity={event.severity})",
            "level": "WARNING" if event.severity == "warning" else "ERROR",
        })



def initialize(manager: Optional[Any] = None, config: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
    """Plugin initialization."""
    pass


def post_order(order_info: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
    """Dispatches webhook notification upon order execution."""
    pass


def on_shutdown(*args, **kwargs) -> None:
    """Clean up webhook connections on shutdown."""
    pass

