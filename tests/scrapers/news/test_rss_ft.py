import pytest
from scrapers.news.rss_ft import FinancialTimesRssScraper

def test_init():
    scraper = FinancialTimesRssScraper()
    assert scraper.source_name is not None
    assert scraper.feed_url is not None
