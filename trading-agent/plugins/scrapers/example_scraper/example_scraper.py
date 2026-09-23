"""
Example News Scraper Reference Plugin for Monika.
Demonstrates external news/data ingestion source plugin without altering core scrapers.
"""

from typing import Dict, Any, Optional


from harness.contract import (
    TradingPlugin,
    PluginMetadata,
    PluginCategory,
    PluginOrigin,
)


def fetch_external_wire_feed(args: Dict[str, Any]) -> Dict[str, Any]:
    """Fetches synthetic financial wire feed items."""
    topic = str(args.get("topic", "forex")).lower()
    return {
        "status": "success",
        "topic": topic,
        "items": [
            {
                "headline": f"External wire: Central Bank policy commentary on {topic}",
                "urgency": "medium",
                "source": "custom_scraper_plugin",
            }
        ],
        "count": 1,
    }


class ExampleScraperPlugin(TradingPlugin):
    """External news scraper reference plugin for market data feeds."""
    metadata = PluginMetadata(
        id="example_scraper_plugin",
        name="Example Scraper Plugin",
        version="1.0.0",
        category=PluginCategory.DATA_SOURCE,
        description="Reference external news scraper plugin for market data feeds",
        origin=PluginOrigin.LOCAL_DIRECTORY,
    )

    async def fetch_feed(self, topic: str = "forex") -> Dict[str, Any]:
        return fetch_external_wire_feed({"topic": topic})


def initialize(manager: Optional[Any] = None, config: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
    """Plugin initialization."""
    pass


def pre_tool_call(tool_name: str = "", args: Optional[Dict[str, Any]] = None, *a, **kwargs) -> Optional[Dict[str, Any]]:
    return args

