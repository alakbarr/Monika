# ==============================================================================
# File: scrapers/news/rss_boe.py
# ==============================================================================
"""
Bank of England news RSS feed scraper.

Source: bankofengland.co.uk official RSS — primary source for BOE rate decisions,
MPC minutes, and speeches. Critical for GBPUSD analysis.
"""

from scrapers.news.rss_base import RssBaseScraper


class BoeRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="boe_official",
            feed_url="https://www.bankofengland.co.uk/rss/news",
        )
