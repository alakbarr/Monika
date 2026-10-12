import pytest
from scrapers.news.rss_marketwatch import MarketwatchRssScraper

def test_init():
    scraper = MarketwatchRssScraper()
    assert scraper.source_name is not None
    assert scraper.feed_url is not None
