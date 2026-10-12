# ==============================================================================
# File: scrapers/news/rss_fxstreet.py
# ==============================================================================

from scrapers.news.rss_base import RssBaseScraper

class FxstreetRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="fxstreet", 
            feed_url="https://www.fxstreet.com/rss/news"
        )
