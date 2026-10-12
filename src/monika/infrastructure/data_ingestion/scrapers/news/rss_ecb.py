# ==============================================================================
# File: scrapers/news/rss_ecb.py
# ==============================================================================
"""
European Central Bank press release RSS feed scraper.

Source: ecb.europa.eu official press releases — primary source for ECB rate
decisions, statements, and speeches. Critical for EURUSD and GBPUSD analysis.
"""

from scrapers.news.rss_base import RssBaseScraper


class EcbRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="ecb_official",
            feed_url="https://www.ecb.europa.eu/rss/press.html",
        )
