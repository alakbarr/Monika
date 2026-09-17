import pytest
from scrapers.news.rss_cnbc import CnbcRssScraper

def test_init():
    scraper = CnbcRssScraper()
    assert scraper.source_name is not None
    assert scraper.feed_url is not None
