import pytest
from scrapers.news.rss_reuters import ReutersRssScraper

def test_init():
    scraper = ReutersRssScraper()
    assert scraper.source_name is not None
    assert scraper.feed_url is not None
