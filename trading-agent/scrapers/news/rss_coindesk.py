# ==============================================================================
# File: scrapers/news/rss_coindesk.py
# ==============================================================================

from scrapers.news.rss_base import RssBaseScraper

class CoindeskRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="coindesk", 
            feed_url="https://www.coindesk.com/arc/outboundfeeds/rss/"
        )
