# ==============================================================================
# File: scrapers/news/rss_ft.py
# ==============================================================================

from scrapers.news.rss_base import RssBaseScraper

class FinancialTimesRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="financial_times_markets",
            feed_url="https://www.ft.com/markets?format=rss"
        )
