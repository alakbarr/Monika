"""
Example News Scraper Reference Plugin for Monika.
Demonstrates external news/data ingestion source plugin without altering core scrapers.
"""

from typing import Dict, Any, Optional


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


def initialize(manager: Optional[Any] = None, config: Optional[Dict[str, Any]] = None, *args, **kwargs) -> None:
    """Plugin initialization."""
    pass


def pre_tool_call(tool_name: str = "", args: Optional[Dict[str, Any]] = None, *a, **kwargs) -> Optional[Dict[str, Any]]:
    return args
