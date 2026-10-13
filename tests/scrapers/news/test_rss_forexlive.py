import pytest
from monika.infrastructure.data_ingestion.scrapers.news.rss_forexlive import ForexliveRssScraper


def test_init():
    scraper = ForexliveRssScraper()
    assert scraper.source_name is not None
    assert scraper.feed_url is not None
