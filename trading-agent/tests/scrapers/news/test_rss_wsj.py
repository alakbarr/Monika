import pytest
from scrapers.news.rss_wsj import WsjRssScraper

def test_init():
    scraper = WsjRssScraper()
    assert scraper.source_name is not None
    assert scraper.feed_url is not None
