# ==============================================================================
# File: scrapers/news/rss_wsj.py
# ==============================================================================

from monika.infrastructure.data_ingestion.scrapers.news.rss_base import RssBaseScraper

class WsjRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="wsj_markets", 
            feed_url="https://feeds.a.dj.com/rss/RSSMarketsMain.xml"
        )
