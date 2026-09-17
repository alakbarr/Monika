# ==============================================================================
# File: scrapers/news/rss_investing.py
# ==============================================================================

from scrapers.news.rss_base import RssBaseScraper

class InvestingRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="investing_world_news", 
            feed_url="https://www.investing.com/rss/news_287.rss"
        )
