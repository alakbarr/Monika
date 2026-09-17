# ==============================================================================
# File: scripts/check_scrapers/check_twitter.py
# ==============================================================================

"""
Script Pemeriksaan Scraper Twitter / X.com (TwitterWatchScraper).
Default: headless=False (jendela browser terbuka untuk melihat sesi, injeksi cookies, dan render timeline).
"""

import sys
import os
import time
import argparse
import logging
from pathlib import Path
from typing import List

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Menambahkan root trading-agent ke sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Muat environment variables dari file .env
try:
    from dotenv import load_dotenv
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    root_dir = os.path.abspath(os.path.join(base_dir, ".."))
    for p in [os.path.join(root_dir, ".env"), os.path.join(base_dir, ".env")]:
        if os.path.exists(p):
            load_dotenv(dotenv_path=p)
            break
except Exception:
    pass

from scrapers.models import ScrapedTweet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("CheckTwitter")


def print_tweets_table(tweets: List[ScrapedTweet], max_display: int = 5):
    """Mencetak daftar tweet ke terminal."""
    if not tweets:
        print("   [!] Tidak ada tweet yang berhasil diekstrak.")
        return

    print(f"\n   {'TIME':<20} | {'USERNAME':<15} | {'CONTENT':<60}")
    print("   " + "-" * 100)
    for t in tweets[:max_display]:
        time_str = str(t.timestamp or "-")[:20]
        user_str = str(f"@{t.username}" if t.username else "-")[:15]
        content_str = str(t.content or "").replace("\n", " ")[:60]
        print(f"   {time_str:<20} | {user_str:<15} | {content_str:<60}")

    if len(tweets) > max_display:
        print(f"   ... dan {len(tweets) - max_display} tweet lainnya.\n")
    else:
        print("")


def check_twitter_sessions(session_dir: Path):
    """Memeriksa ketersediaan file sesi twitter di folder data/sessions/."""
    all_sessions = list(session_dir.glob("twitter_session*.json"))
    active_sessions = [p for p in all_sessions if "poisoned" not in p.name]
    logger.info(f"Pemeriksaan Session Directory ({session_dir}):")
    logger.info(f"- Ditemukan {len(all_sessions)} total file sesi, {len(active_sessions)} aktif.")
    if not active_sessions:
        logger.warning("[WARNING] Tidak ada file sesi twitter aktif (twitter_session*.json). Twitter scraping membutuhkan cookie session valid.")
    else:
        for s in active_sessions:
            logger.info(f"  * {s.name}")


def check_twitter(headless: bool = False, list_url: str = None, max_age: int = 1440, pause: int = 3) -> dict:
    """Menguji TwitterWatchScraper."""
    logger.info(f"==> Menguji TwitterWatchScraper (Headless: {headless}, Max Age: {max_age}m)")
    from scrapers.social.twitter_watch import TwitterWatchScraper

    scraper = None
    start_time = time.time()
    try:
        scraper = TwitterWatchScraper(headless=headless, list_url=list_url)
        check_twitter_sessions(scraper.session_dir)

        tweets = scraper.fetch_latest_tweets(max_age_minutes=max_age)
        duration = round(time.time() - start_time, 2)
        logger.info(f"[OK] Twitter / X: Berhasil mengekstrak {len(tweets)} tweets ({duration}s)")
        print_tweets_table(tweets)

        if pause > 0 and not headless:
            logger.info(f"Menahan browser selama {pause} detik sebelum ditutup...")
            time.sleep(pause)

        return {"source": "Twitter / X.com", "status": "SUCCESS" if tweets else "EMPTY", "count": len(tweets), "duration": duration}
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        logger.error(f"[FAILED] Twitter scraper gagal: {e}")
        return {"source": "Twitter / X.com", "status": "FAILED", "error": str(e), "duration": duration}
    finally:
        if scraper:
            logger.info("Menutup instance browser Twitter...")
            scraper.close()


def main():
    parser = argparse.ArgumentParser(description="Pemeriksaan Scraper Twitter / X.com (TwitterWatchScraper)")
    parser.add_argument("--list-url", type=str, default=None, help="Custom Twitter List URL untuk diuji")
    parser.add_argument("--max-age", type=int, default=1440, help="Batas usia maksimal tweet dalam menit (default: 1440 / 24 jam)")
    parser.add_argument("--headless", action="store_true", help="Jalankan dalam mode headless background (default: False/headed)")
    parser.add_argument("--pause", type=int, default=3, help="Jeda penutupan browser untuk observasi visual dalam detik (default: 3)")

    args = parser.parse_args()
    headless_mode = args.headless

    print("\n" + "=" * 60)
    print("  PEMERIKSAAN SCRAPER TWITTER / X.COM")
    print(f"  Headless: {headless_mode} | Max Age: {args.max_age}m | Pause: {args.pause}s")
    print("=" * 60 + "\n")

    result = check_twitter(headless=headless_mode, list_url=args.list_url, max_age=args.max_age, pause=args.pause)

    print("\n" + "=" * 60)
    print("  RINGKASAN HASIL PEMERIKSAAN TWITTER")
    print("=" * 60)
    status_tag = "[OK]   " if result.get("status") == "SUCCESS" else ("[EMPTY]" if result.get("status") == "EMPTY" else "[FAIL] ")
    count_str = f"{result.get('count', 0)} tweets" if "count" in result else result.get("error", "Error")
    print(f"  {status_tag} {result['source']:<20} | Status: {result['status']:<8} | {count_str} ({result.get('duration', 0)}s)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
