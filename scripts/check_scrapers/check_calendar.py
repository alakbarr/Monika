# ==============================================================================
# File: scripts/check_scrapers/check_calendar.py
# ==============================================================================

"""
Script Pemeriksaan Scraper Kalender Ekonomi (ForexFactory, Investing.com, Finnhub).
Default: headless=False (jendela browser terbuka agar bisa diamati langsung).
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

from scrapers.models import CalendarEvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("CheckCalendar")


def print_events_table(events: List[CalendarEvent], max_display: int = 10):
    """Mencetak daftar event kalender ke terminal dalam format tabel ringkas."""
    if not events:
        print("   [!] Tidak ada data event yang ditemukan.")
        return

    print(f"\n   {'TIME':<20} | {'CUR':<5} | {'IMPACT':<8} | {'EVENT NAME':<40} | {'ACTUAL':<10} | {'FORECAST':<10} | {'PREVIOUS':<10}")
    print("   " + "-" * 115)
    for e in events[:max_display]:
        time_str = str(e.time or "-")[:20]
        cur_str = str(e.currency or "-")[:5]
        impact_str = str(e.impact or "-")[:8]
        name_str = str(e.event_name or "-")[:40]
        actual_str = str(e.actual or "-")[:10]
        forecast_str = str(e.forecast or "-")[:10]
        prev_str = str(e.previous or "-")[:10]
        print(f"   {time_str:<20} | {cur_str:<5} | {impact_str:<8} | {name_str:<40} | {actual_str:<10} | {forecast_str:<10} | {prev_str:<10}")

    if len(events) > max_display:
        print(f"   ... dan {len(events) - max_display} event lainnya.\n")
    else:
        print("")


def check_forexfactory(headless: bool = False, pause: int = 3) -> dict:
    """Menguji scraper ForexFactory."""
    logger.info(f"==> Menguji ForexFactoryCalendarScraper (Headless: {headless})")
    from scrapers.calendar.calendar_forexfactory import ForexFactoryCalendarScraper

    scraper = None
    start_time = time.time()
    try:
        scraper = ForexFactoryCalendarScraper(headless=headless, profile_name="check_ff_calendar")
        events = scraper.fetch_events()
        duration = round(time.time() - start_time, 2)
        logger.info(f"[OK] ForexFactory: Berhasil mengekstrak {len(events)} events ({duration}s)")
        print_events_table(events)
        if pause > 0 and not headless:
            logger.info(f"Menahan browser selama {pause} detik sebelum ditutup...")
            time.sleep(pause)
        return {"source": "ForexFactory", "status": "SUCCESS" if events else "EMPTY", "count": len(events), "duration": duration}
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        logger.error(f"[FAILED] ForexFactory gagal: {e}")
        return {"source": "ForexFactory", "status": "FAILED", "error": str(e), "duration": duration}
    finally:
        if scraper:
            logger.info("Menutup instance browser ForexFactory...")
            scraper.close()


def check_investing(headless: bool = False, pause: int = 3) -> dict:
    """Menguji scraper Investing.com."""
    logger.info(f"==> Menguji InvestingCalendarScraper (Headless: {headless})")
    from scrapers.calendar.calendar_investing import InvestingCalendarScraper

    scraper = None
    start_time = time.time()
    try:
        scraper = InvestingCalendarScraper(headless=headless, profile_name="check_investing_calendar")
        events = scraper.fetch_events()
        duration = round(time.time() - start_time, 2)
        logger.info(f"[OK] Investing.com: Berhasil mengekstrak {len(events)} events ({duration}s)")
        print_events_table(events)
        if pause > 0 and not headless:
            logger.info(f"Menahan browser selama {pause} detik sebelum ditutup...")
            time.sleep(pause)
        return {"source": "Investing.com", "status": "SUCCESS" if events else "EMPTY", "count": len(events), "duration": duration}
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        logger.error(f"[FAILED] Investing.com gagal: {e}")
        return {"source": "Investing.com", "status": "FAILED", "error": str(e), "duration": duration}
    finally:
        if scraper:
            logger.info("Menutup instance browser Investing.com...")
            scraper.close()


def check_finnhub() -> dict:
    """Menguji scraper Finnhub Calendar (REST API)."""
    logger.info("==> Menguji FinnhubCalendarScraper (REST API)")
    from scrapers.calendar.calendar_finnhub import FinnhubCalendarScraper

    start_time = time.time()
    try:
        scraper = FinnhubCalendarScraper()
        if not scraper.api_key:
            logger.warning("[WARNING] FINNHUB_API_KEY tidak disetel di environment. Request mungkin gagal/terbatas.")
        events = scraper.fetch_today_events()
        duration = round(time.time() - start_time, 2)
        logger.info(f"[OK] Finnhub: Berhasil mengambil {len(events)} events ({duration}s)")
        print_events_table(events)
        return {"source": "Finnhub (API)", "status": "SUCCESS" if events else "EMPTY", "count": len(events), "duration": duration}
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        logger.error(f"[FAILED] Finnhub gagal: {e}")
        return {"source": "Finnhub (API)", "status": "FAILED", "error": str(e), "duration": duration}


def main():
    parser = argparse.ArgumentParser(description="Pemeriksaan Scraper Kalender Ekonomi (ForexFactory, Investing.com, Finnhub)")
    parser.add_argument("--source", choices=["all", "forexfactory", "investing", "finnhub"], default="all", help="Pilih scraper kalender yang ingin diuji (default: all)")
    parser.add_argument("--headless", action="store_true", help="Jalankan dalam mode headless background (default: False/headed)")
    parser.add_argument("--pause", type=int, default=3, help="Jeda penutupan browser untuk observasi visual dalam detik (default: 3)")

    args = parser.parse_args()
    headless_mode = args.headless

    print("\n" + "=" * 60)
    print("  PEMERIKSAAN SCRAPER KALENDER EKONOMI")
    print(f"  Target: {args.source.upper()} | Headless: {headless_mode} | Pause: {args.pause}s")
    print("=" * 60 + "\n")

    results = []

    if args.source in ["all", "forexfactory"]:
        results.append(check_forexfactory(headless=headless_mode, pause=args.pause))

    if args.source in ["all", "investing"]:
        results.append(check_investing(headless=headless_mode, pause=args.pause))

    if args.source in ["all", "finnhub"]:
        results.append(check_finnhub())

    print("\n" + "=" * 60)
    print("  RINGKASAN HASIL PEMERIKSAAN KALENDER")
    print("=" * 60)
    for r in results:
        status_tag = "[OK]   " if r.get("status") == "SUCCESS" else ("[EMPTY]" if r.get("status") == "EMPTY" else "[FAIL] ")
        count_str = f"{r.get('count', 0)} events" if "count" in r else r.get("error", "Error")
        print(f"  {status_tag} {r['source']:<20} | Status: {r['status']:<8} | {count_str} ({r.get('duration', 0)}s)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
