import pytest
from scrapers.news.rss_coindesk import CoindeskRssScraper

def test_init():
    scraper = CoindeskRssScraper()
    assert scraper.source_name is not None
    assert scraper.feed_url is not None
