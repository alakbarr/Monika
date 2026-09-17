# ==============================================================================
# File: scrapers/news/rss_boj.py
# ==============================================================================

"""Bank of Japan official announcements RSS feed. Critical for USDJPY."""
from scrapers.news.rss_base import RssBaseScraper

class BojRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="boj_official",
            feed_url="https://www.boj.or.jp/en/announcements/rss/news_rss.xml",
        )
