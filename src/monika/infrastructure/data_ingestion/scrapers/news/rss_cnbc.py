# ==============================================================================
# File: scrapers/news/rss_cnbc.py
# ==============================================================================

from scrapers.news.rss_base import RssBaseScraper

class CnbcRssScraper(RssBaseScraper):
    def __init__(self):
        super().__init__(
            source_name="cnbc_economy",
            feed_url="https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15837362"
        )
