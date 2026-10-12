# ==============================================================================
# File: scrapers/news/rss_fed.py
# ==============================================================================
"""
Federal Reserve press release RSS feed scraper.

Source: federalreserve.gov official RSS — primary source for FOMC statements,
rate decisions, minutes, and speeches. Zero scraping risk (official feed).
Higher signal-to-noise than third-party news coverage.
"""

from scrapers.news.rss_base import RssBaseScraper


class FedRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="federal_reserve_official",
            feed_url="https://www.federalreserve.gov/feeds/press_all.xml",
        )
