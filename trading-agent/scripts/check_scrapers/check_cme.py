# ==============================================================================
# File: scripts/check_scrapers/check_cme.py
# ==============================================================================

"""
Script Pemeriksaan Scraper CME FedWatch Tool.
Default: headless=False (jendela browser terbuka agar bisa melihat iframe QuikStrike dan data probabilitas).
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

from scrapers.models import FedMeeting

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("CheckCME")


def print_fed_meetings(meetings: List[FedMeeting]):
    """Mencetak data probabilitas rapat FOMC ke terminal."""
    if not meetings:
        print("   [!] Tidak ada data meeting CME FedWatch yang ditemukan.")
        return

    print("\n   " + "=" * 70)
    print("   DISTRIBUSI PROBABILITAS SUKU BUNGA THE FED (FOMC MEETINGS)")
    print("   " + "=" * 70)

    for m in meetings:
        print(f"\n   [DATE] Meeting Date: {m.meeting_date} (Current Rate Ref: {m.current_rate_ref}%)")
        print(f"          Most Likely Action: {m.most_likely}")
        print(f"          {'TARGET RANGE':<18} | {'PROBABILITY':<12} | {'ACTION':<10}")
        print("          " + "-" * 45)
        for p in m.probabilities:
            prob_pct = f"{p.probability:.1f}%"
            print(f"          {p.target_range:<18} | {prob_pct:<12} | {p.action:<10}")
    print("\n")


def check_cme_fedwatch(headless: bool = False, pause: int = 3) -> dict:
    """Menguji FedWatchScraper."""
    logger.info(f"==> Menguji FedWatchScraper (Headless: {headless})")
    from scrapers.macro.cme_fedwatch import FedWatchScraper

    scraper = None
    start_time = time.time()
    try:
        scraper = FedWatchScraper(headless=headless)
        meetings = scraper.fetch_probabilities()
        duration = round(time.time() - start_time, 2)
        logger.info(f"[OK] CME FedWatch: Berhasil mengekstrak {len(meetings)} meetings ({duration}s)")
        print_fed_meetings(meetings)
        if pause > 0 and not headless:
            logger.info(f"Menahan browser selama {pause} detik sebelum ditutup...")
            time.sleep(pause)
        return {"source": "CME FedWatch", "status": "SUCCESS" if meetings else "EMPTY", "count": len(meetings), "duration": duration}
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        logger.error(f"[FAILED] CME FedWatch gagal: {e}")
        return {"source": "CME FedWatch", "status": "FAILED", "error": str(e), "duration": duration}
    finally:
        if scraper:
            logger.info("Menutup instance browser CME FedWatch...")
            scraper.close()


def main():
    parser = argparse.ArgumentParser(description="Pemeriksaan Scraper CME FedWatch Tool")
    parser.add_argument("--headless", action="store_true", help="Jalankan dalam mode headless background (default: False/headed)")
    parser.add_argument("--pause", type=int, default=3, help="Jeda penutupan browser untuk observasi visual dalam detik (default: 3)")

    args = parser.parse_args()
    headless_mode = args.headless

    print("\n" + "=" * 60)
    print("  PEMERIKSAAN SCRAPER CME FEDWATCH TOOL")
    print(f"  Headless: {headless_mode} | Pause: {args.pause}s")
    print("=" * 60 + "\n")

    result = check_cme_fedwatch(headless=headless_mode, pause=args.pause)

    print("\n" + "=" * 60)
    print("  RINGKASAN HASIL PEMERIKSAAN CME FEDWATCH")
    print("=" * 60)
    status_tag = "[OK]   " if result.get("status") == "SUCCESS" else ("[EMPTY]" if result.get("status") == "EMPTY" else "[FAIL] ")
    count_str = f"{result.get('count', 0)} FOMC meetings" if "count" in result else result.get("error", "Error")
    print(f"  {status_tag} {result['source']:<20} | Status: {result['status']:<8} | {count_str} ({result.get('duration', 0)}s)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
