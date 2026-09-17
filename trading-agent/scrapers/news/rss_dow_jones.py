# ==============================================================================
# File: scrapers/news/rss_dow_jones.py
# ==============================================================================

from scrapers.news.rss_base import RssBaseScraper

class DowJonesRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="dow_jones_newswires", 
            feed_url="https://feeds.a.dj.com/rss/RSSWorldNews.xml"
        )
