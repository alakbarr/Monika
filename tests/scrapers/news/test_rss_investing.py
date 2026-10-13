import pytest
from monika.infrastructure.data_ingestion.scrapers.news.rss_investing import InvestingRssScraper


def test_init():
    scraper = InvestingRssScraper()
    assert scraper.source_name is not None
    assert scraper.feed_url is not None
