import sys
import os
import asyncio
import logging

# Menambahkan root directory agar bisa mengimpor modul dari trading-agent
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'trading-agent')))

from scrapers.calendar.calendar_forexfactory import ForexFactoryCalendarScraper

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)-8s | %(message)s')
    logger = logging.getLogger("Test")
    
    logger.info("Memulai pengujian ForexFactoryScraper (Headless=False agar terlihat)")
    # Kita menggunakan headless=False secara eksplisit agar Anda dapat melihat tampilan browser
    scraper = ForexFactoryCalendarScraper(headless=False, profile_name="test_ff")
    
    try:
        events = scraper.fetch_events()
        logger.info(f"Berhasil mendapatkan {len(events)} events.")
        for e in events[:5]:
            print(f"- {e.time} | {e.currency} | {e.impact} | {e.event_name}")
        if len(events) > 5:
            print(f"... dan {len(events) - 5} lainnya.")
            
        if len(events) == 0:
            logger.info("Mencoba melakukan dump HTML untuk inspeksi...")
            scraper.page.get("https://www.forexfactory.com/calendar?week=this")
            scraper.page.wait(5)
            html = scraper.page.html
            with open("ff_dump.html", "w", encoding="utf-8") as f:
                f.write(html)
            logger.info("HTML disimpan di ff_dump.html. Silakan periksa isinya.")
            
    except Exception as e:
        logger.error(f"Error saat menjalankan scraper: {e}")
    finally:
        logger.info("Menutup scraper...")
        scraper.close()

if __name__ == "__main__":
    main()
