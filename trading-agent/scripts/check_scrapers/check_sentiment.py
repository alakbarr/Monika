# ==============================================================================
# File: scripts/check_scrapers/check_sentiment.py
# ==============================================================================

"""
Script Pemeriksaan Scraper Sentimen Ritel Pasar (FXSSI, MyFxBook, Binance Futures).
Default: headless=False (jendela browser terbuka untuk FXSSI & MyFxBook).
"""

import sys
import os
import time
import asyncio
import argparse
import logging

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("CheckSentiment")


def print_ratios_table(source_name: str, ratios: dict):
    """Mencetak persentase long/short rasio per instrumen."""
    if not ratios:
        print(f"   [!] Tidak ada data rasio untuk {source_name}.")
        return

    print(f"\n   {'INSTRUMENT':<12} | {'LONG %':<10} | {'SHORT %':<10} | {'L/S RATIO':<12}")
    print("   " + "-" * 52)
    for symbol, val in ratios.items():
        long_pct = f"{val.get('long_percent', 0):.1f}%"
        short_pct = f"{val.get('short_percent', 0):.1f}%"
        ls_ratio = f"{val.get('long_short_ratio', 0):.2f}"
        print(f"   {symbol:<12} | {long_pct:<10} | {short_pct:<10} | {ls_ratio:<12}")
    print("")


def check_fxssi(headless: bool = False, pause: int = 3) -> dict:
    """Menguji FXSSISentimentFetcher (DrissionPage browser)."""
    logger.info(f"==> Menguji FXSSISentimentFetcher (Headless: {headless})")
    from scrapers.sentiment.fxssi_sentiment import FXSSISentimentFetcher

    start_time = time.time()
    try:
        fetcher = FXSSISentimentFetcher(session=None, headless=headless)
        result = fetcher.fetch_sync()
        duration = round(time.time() - start_time, 2)
        ratios = result.get("ratios", {})
        if ratios:
            logger.info(f"[OK] FXSSI: Berhasil mengekstrak rasio {len(ratios)} aset ({duration}s)")
            print_ratios_table("FXSSI", ratios)
        else:
            logger.warning(f"[EMPTY] FXSSI gagal parse atau data kosong: {result.get('error')}")

        if pause > 0 and not headless:
            logger.info(f"Menahan jeda {pause} detik...")
            time.sleep(pause)

        return {"source": "FXSSI (Browser)", "status": "SUCCESS" if ratios else "EMPTY", "count": len(ratios), "duration": duration, "error": result.get("error")}
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        logger.error(f"[FAILED] FXSSI gagal: {e}")
        return {"source": "FXSSI (Browser)", "status": "FAILED", "error": str(e), "duration": duration}


def check_myfxbook(headless: bool = False, pause: int = 3) -> dict:
    """Menguji MyFxBookSentimentFetcher (DrissionPage browser)."""
    logger.info(f"==> Menguji MyFxBookSentimentFetcher (Headless: {headless})")
    from scrapers.sentiment.myfxbook_sentiment import MyFxBookSentimentFetcher

    start_time = time.time()
    try:
        fetcher = MyFxBookSentimentFetcher(session=None, headless=headless)
        result = fetcher.fetch_sync()
        duration = round(time.time() - start_time, 2)
        ratios = result.get("ratios", {})
        if ratios:
            logger.info(f"[OK] MyFxBook: Berhasil mengekstrak rasio {len(ratios)} aset ({duration}s)")
            print_ratios_table("MyFxBook", ratios)
        else:
            logger.warning(f"[EMPTY] MyFxBook gagal parse atau data kosong: {result.get('error')}")

        if pause > 0 and not headless:
            logger.info(f"Menahan jeda {pause} detik...")
            time.sleep(pause)

        return {"source": "MyFxBook (Browser)", "status": "SUCCESS" if ratios else "EMPTY", "count": len(ratios), "duration": duration, "error": result.get("error")}
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        logger.error(f"[FAILED] MyFxBook gagal: {e}")
        return {"source": "MyFxBook (Browser)", "status": "FAILED", "error": str(e), "duration": duration}


async def check_binance() -> dict:
    """Menguji BinanceSentimentFetcher (REST API)."""
    logger.info("==> Menguji BinanceSentimentFetcher (REST API)")
    from scrapers.sentiment.binance_sentiment import BinanceSentimentFetcher

    start_time = time.time()
    try:
        fetcher = BinanceSentimentFetcher(session=None)
        result = await fetcher.fetch()
        duration = round(time.time() - start_time, 2)
        ratios = result.get("ratios", {})
        if ratios:
            logger.info(f"[OK] Binance: Berhasil mengambil rasio {len(ratios)} crypto symbols ({duration}s)")
            print_ratios_table("Binance Futures", ratios)
        else:
            logger.warning(f"[EMPTY] Binance kosong atau error: {result.get('error')}")

        return {"source": "Binance Futures (API)", "status": "SUCCESS" if ratios else "EMPTY", "count": len(ratios), "duration": duration, "error": result.get("error")}
    except Exception as e:
        duration = round(time.time() - start_time, 2)
        logger.error(f"[FAILED] Binance gagal: {e}")
        return {"source": "Binance Futures (API)", "status": "FAILED", "error": str(e), "duration": duration}


def main():
    parser = argparse.ArgumentParser(description="Pemeriksaan Scraper Sentimen Ritel (FXSSI, MyFxBook, Binance)")
    parser.add_argument("--source", choices=["all", "fxssi", "myfxbook", "binance"], default="all", help="Pilih sumber sentimen yang ingin diuji (default: all)")
    parser.add_argument("--headless", action="store_true", help="Jalankan browser scraper dalam mode headless (default: False/headed)")
    parser.add_argument("--pause", type=int, default=3, help="Jeda penutupan browser untuk observasi visual dalam detik (default: 3)")

    args = parser.parse_args()
    headless_mode = args.headless

    print("\n" + "=" * 60)
    print("  PEMERIKSAAN SCRAPER SENTIMEN PASAR")
    print(f"  Target: {args.source.upper()} | Headless: {headless_mode} | Pause: {args.pause}s")
    print("=" * 60 + "\n")

    results = []

    if args.source in ["all", "fxssi"]:
        results.append(check_fxssi(headless=headless_mode, pause=args.pause))

    if args.source in ["all", "myfxbook"]:
        results.append(check_myfxbook(headless=headless_mode, pause=args.pause))

    if args.source in ["all", "binance"]:
        import sys
        if sys.platform == "win32":
            res_binance = asyncio.run(check_binance(), loop_factory=asyncio.SelectorEventLoop)
        else:
            res_binance = asyncio.run(check_binance())
        results.append(res_binance)

    print("\n" + "=" * 60)
    print("  RINGKASAN HASIL PEMERIKSAAN SENTIMEN")
    print("=" * 60)
    for r in results:
        status_tag = "[OK]   " if r.get("status") == "SUCCESS" else ("[EMPTY]" if r.get("status") == "EMPTY" else "[FAIL] ")
        count_str = f"{r.get('count', 0)} symbols" if "count" in r and r.get("count", 0) > 0 else r.get("error", "Error/Empty")
        print(f"  {status_tag} {r['source']:<24} | Status: {r['status']:<8} | {count_str} ({r.get('duration', 0)}s)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
