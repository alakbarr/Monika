import pytest
from scrapers.news.rss_bloomberg import BloombergRssScraper

def test_init():
    scraper = BloombergRssScraper()
    assert scraper.source_name is not None
    assert scraper.feed_url is not None
