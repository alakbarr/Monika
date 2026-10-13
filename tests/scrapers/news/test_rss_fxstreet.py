import pytest
from monika.infrastructure.data_ingestion.scrapers.news.rss_fxstreet import FxstreetRssScraper


def test_init():
    scraper = FxstreetRssScraper()
    assert scraper.source_name is not None
    assert scraper.feed_url is not None
