import time
from pathlib import Path
from monika.infrastructure.data_ingestion.scrapers.profile_reaper import BrowserProfileReaper


def test_profile_reaper_prune_caches(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(BrowserProfileReaper, "get_profiles_dir", classmethod(lambda cls: tmp_path))

    # Setup dummy browser profile with cache subdirs
    prof1 = tmp_path / "investing_calendar"
    cache_dir = prof1 / "Default" / "Cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    dummy_file = cache_dir / "data_0"
    dummy_file.write_bytes(b"x" * 2000)

    # Prune with 0.001MB limit to trigger deletion
    freed = BrowserProfileReaper.prune_profile_caches(max_cache_size_mb=0.001)
    assert freed >= 2000
    assert not cache_dir.exists()


def test_profile_reaper_prune_stale_test_profiles(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(BrowserProfileReaper, "get_profiles_dir", classmethod(lambda cls: tmp_path))

    # Create dummy stale test profile
    test_prof = tmp_path / "test_dummy_profile"
    test_prof.mkdir(parents=True, exist_ok=True)

    # Fake mtime older than 8 days
    old_time = time.time() - (8 * 86400)
    import os

    os.utime(test_prof, (old_time, old_time))

    removed = BrowserProfileReaper.prune_stale_test_profiles(max_age_days=7.0)
    assert removed == 1
    assert not test_prof.exists()
