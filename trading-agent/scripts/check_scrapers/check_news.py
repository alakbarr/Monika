# ==============================================================================
# File: scripts/check_scrapers/check_news.py
# ==============================================================================

"""
Script Pemeriksaan Scraper Berita (Kitco News, TradingView News, 16 RSS Feed Sumber Resmi & Finansial).
Default: headless=False untuk browser scrapers (Kitco & TradingView).
"""

import sys
import os
import time
import argparse
import logging
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

from scrapers.models import ScrapedNews

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("CheckNews")


def print_news_table(news_list: List[ScrapedNews], max_display: int = 5):
    """Mencetak daftar berita ke terminal dalam format ringkas."""
    if not news_list:
        print("   [!] Tidak ada artikel berita yang ditemukan.")
        return

    print(f"\n   {'TIME / DATE':<22} | {'SOURCE':<18} | {'HEADLINE':<60}")
    print("   " + "-" * 105)
    for n in news_list[:max_display]:
        time_str = str(n.timestamp or "-")[:22]
        source_str = str(n.source or "-")[:18]
        headline_str = str(n.title or "-")[:60]
        print(f"   {time_str:<22} | {source_str:<18} | {headline_str:<60}")

    if len(news_list) > max_display:
        print(f"   ... dan {len(news_list) - max_display} artikel lainnya.\n")
    else:
        print("")


def check_kitco(headless: bool = False, limit: int = 5, pause: int = 3) -> dict:
    """Menguji KitcoNewsScraper."""
    logger.info(f"==> Menguji KitcoNewsScraper (Headless: {headless}, Limit: {limit})")
    from scrapers.news.kitco_news import KitcoNewsScraper

    scraper = None
    start_time = time.time()
    try:
        scraper = KitcoNewsScraper(headless=headless)
        news = scraper.fetch_news(limit=limit)
        duration = round(time.time() - start_time, 2)
        logger.info(f"[OK] Kitco News: Berhasil mengekstrak {len(news)} artikel ({duration}s)")
        print_news_table(news, max_display=limit)
        if pause > 0 and not headless:
            logger.info(f"Menahan browser selama {pause} detik sebelum ditutup...")
            time.sleep(pause)
        return {"source": "Kitco News", "type": "Browser", "status": "SUCCESS" if news else "EMPTY", "count": len(news), "duration": duration}
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        logger.error(f"[FAILED] Kitco News gagal: {e}")
        return {"source": "Kitco News", "type": "Browser", "status": "FAILED", "error": str(e), "duration": duration}
    finally:
        if scraper:
            logger.info("Menutup instance browser Kitco...")
            scraper.close()


def check_tradingview(headless: bool = False, limit: int = 5, pause: int = 3) -> dict:
    """Menguji TradingViewNewsScraper."""
    logger.info(f"==> Menguji TradingViewNewsScraper (Headless: {headless}, Limit: {limit})")
    from scrapers.news.tradingview_news import TradingViewNewsScraper

    scraper = None
    start_time = time.time()
    try:
        scraper = TradingViewNewsScraper(headless=headless)
        news = scraper.fetch_news(limit=limit)
        duration = round(time.time() - start_time, 2)
        logger.info(f"[OK] TradingView: Berhasil mengekstrak {len(news)} artikel ({duration}s)")
        print_news_table(news, max_display=limit)
        if pause > 0 and not headless:
            logger.info(f"Menahan browser selama {pause} detik sebelum ditutup...")
            time.sleep(pause)
        return {"source": "TradingView", "type": "Browser", "status": "SUCCESS" if news else "EMPTY", "count": len(news), "duration": duration}
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        logger.error(f"[FAILED] TradingView gagal: {e}")
        return {"source": "TradingView", "type": "Browser", "status": "FAILED", "error": str(e), "duration": duration}
    finally:
        if scraper:
            logger.info("Menutup instance browser TradingView...")
            scraper.close()


def get_rss_map():
    from scrapers.news.rss_fed import FedRssScraper
    from scrapers.news.rss_ecb import EcbRssScraper
    from scrapers.news.rss_boe import BoeRssScraper
    from scrapers.news.rss_boj import BojRssScraper
    from scrapers.news.rss_rba import RbaRssScraper
    from scrapers.news.rss_bloomberg import BloombergRssScraper
    from scrapers.news.rss_wsj import WsjRssScraper
    from scrapers.news.rss_marketwatch import MarketwatchRssScraper
    from scrapers.news.rss_dow_jones import DowJonesRssScraper
    from scrapers.news.rss_forexlive import ForexliveRssScraper
    from scrapers.news.rss_fxstreet import FxstreetRssScraper
    from scrapers.news.rss_investing import InvestingRssScraper
    from scrapers.news.rss_coindesk import CoindeskRssScraper
    from scrapers.news.rss_reuters import ReutersRssScraper
    from scrapers.news.rss_cnbc import CnbcRssScraper
    from scrapers.news.rss_ft import FinancialTimesRssScraper

    return {
        "fed": ("Federal Reserve RSS", FedRssScraper),
        "ecb": ("ECB RSS", EcbRssScraper),
        "boe": ("BOE RSS", BoeRssScraper),
        "boj": ("BOJ RSS", BojRssScraper),
        "rba": ("RBA RSS", RbaRssScraper),
        "bloomberg": ("Bloomberg RSS", BloombergRssScraper),
        "wsj": ("WSJ RSS", WsjRssScraper),
        "marketwatch": ("MarketWatch RSS", MarketwatchRssScraper),
        "dow_jones": ("Dow Jones RSS", DowJonesRssScraper),
        "forexlive": ("ForexLive RSS", ForexliveRssScraper),
        "fxstreet": ("FXStreet RSS", FxstreetRssScraper),
        "investing": ("Investing RSS", InvestingRssScraper),
        "coindesk": ("CoinDesk RSS", CoindeskRssScraper),
        "reuters": ("Reuters RSS", ReutersRssScraper),
        "cnbc": ("CNBC RSS", CnbcRssScraper),
        "ft": ("Financial Times RSS", FinancialTimesRssScraper),
    }


def check_single_rss(name_key: str, display_name: str, scraper_cls, limit: int = 5) -> dict:
    """Menguji 1 feed RSS."""
    logger.info(f"==> Menguji {display_name} (Limit: {limit})")
    start_time = time.time()
    scraper = None
    try:
        scraper = scraper_cls()
        news = scraper.fetch_news(limit=limit)
        duration = round(time.time() - start_time, 2)
        logger.info(f"[OK] {display_name}: {len(news)} artikel ({duration}s)")
        print_news_table(news, max_display=min(limit, 3))
        return {"source": display_name, "type": "RSS", "status": "SUCCESS" if news else "EMPTY", "count": len(news), "duration": duration}
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        logger.error(f"[FAILED] {display_name} gagal: {e}")
        return {"source": display_name, "type": "RSS", "status": "FAILED", "error": str(e), "duration": duration}
    finally:
        if scraper and hasattr(scraper, "close"):
            scraper.close()


def main():
    rss_map = get_rss_map()
    all_choices = ["all", "kitco", "tradingview", "rss"] + list(rss_map.keys())

    parser = argparse.ArgumentParser(description="Pemeriksaan Scraper Berita (Kitco, TradingView, dan 16 RSS Feeds)")
    parser.add_argument("--source", choices=all_choices, default="all", help="Pilih sumber berita yang ingin diuji (default: all)")
    parser.add_argument("--limit", type=int, default=5, help="Batas artikel yang diambil per sumber (default: 5)")
    parser.add_argument("--headless", action="store_true", help="Jalankan browser scraper dalam mode headless (default: False/headed)")
    parser.add_argument("--pause", type=int, default=3, help="Jeda penutupan browser untuk observasi visual dalam detik (default: 3)")

    args = parser.parse_args()
    headless_mode = args.headless

    print("\n" + "=" * 65)
    print("  PEMERIKSAAN SCRAPER BERITA & RSS")
    print(f"  Target: {args.source.upper()} | Limit: {args.limit} | Headless: {headless_mode} | Pause: {args.pause}s")
    print("=" * 65 + "\n")

    results = []

    if args.source in ["all", "kitco"]:
        results.append(check_kitco(headless=headless_mode, limit=args.limit, pause=args.pause))

    if args.source in ["all", "tradingview"]:
        results.append(check_tradingview(headless=headless_mode, limit=args.limit, pause=args.pause))

    if args.source in ["all", "rss"]:
        logger.info("\n--- MEMULAI PENGUJIAN 16 RSS FEEDS ---")
        for k, (disp_name, cls) in rss_map.items():
            results.append(check_single_rss(k, disp_name, cls, limit=args.limit))
    elif args.source in rss_map:
        disp_name, cls = rss_map[args.source]
        results.append(check_single_rss(args.source, disp_name, cls, limit=args.limit))

    print("\n" + "=" * 65)
    print("  RINGKASAN HASIL PEMERIKSAAN BERITA")
    print("=" * 65)
    for r in results:
        status_tag = "[OK]   " if r.get("status") == "SUCCESS" else ("[EMPTY]" if r.get("status") == "EMPTY" else "[FAIL] ")
        count_str = f"{r.get('count', 0)} artikel" if "count" in r else r.get("error", "Error")
        type_str = f"[{r.get('type', 'Unknown')}]"
        print(f"  {status_tag} {type_str:<10} {r['source']:<24} | Status: {r['status']:<8} | {count_str} ({r.get('duration', 0)}s)")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
