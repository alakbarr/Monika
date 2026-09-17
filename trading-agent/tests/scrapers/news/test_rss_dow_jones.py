import pytest
from scrapers.news.rss_dow_jones import DowJonesRssScraper

def test_init():
    scraper = DowJonesRssScraper()
    assert scraper.source_name is not None
    assert scraper.feed_url is not None
