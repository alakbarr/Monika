# ==============================================================================
# File: scrapers/news/rss_forexlive.py
# ==============================================================================

from scrapers.news.rss_base import RssBaseScraper

class ForexliveRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="forexlive_main", 
            feed_url="https://www.forexlive.com/feed"
        )
