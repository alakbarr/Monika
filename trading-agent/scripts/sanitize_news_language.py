# ==============================================================================
# File: scripts/sanitize_news_language.py
# ==============================================================================

"""
Script Utilitas Audit & Remediator Bahasa Berita (news_items).

Fungsi:
1. Memindai database PostgreSQL news_items untuk mendeteksi record berita
   (khususnya sumber twitter) yang terkontaminasi translasi otomatis Bahasa Indonesia.
2. Mode default (--dry-run): Menampilkan statistik dan daftar record yang terdampak.
3. Mode eksekusi (--apply): Menandai record terjemahan lama (prefilter_flags='TRANSLATED_LEGACY',
   impact='LOW') agar tidak mengotori pipeline analitik dan news digest backfill.
"""

import sys
import os
import argparse
import asyncio
import logging
from typing import List, Tuple

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Tambahkan root trading-agent ke sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select, func, update
from database.db import get_session
from database.models import NewsItem

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("SanitizeNewsLanguage")

# Indikator kata Bahasa Indonesia yang umum muncul dalam terjemahan mesin berita pasar
INDONESIAN_MARKERS = [
    "mengatakan", "terhadap", "bahwa", "kenaikan", "penurunan",
    "tingkat", "ekspor", "imbal hasil", "selamat", "sentimen terpukul",
    "memuncak", "pejabat", "catatan rapat", "notulen", "diposting ulang",
    "meretweet", "disematkan", "utang federal", "melampaui perkiraan",
    "dibuka campuran", "indeks acuan", "bertenor", "perusahaan minyak"
]


async def scan_indonesian_news(session) -> List[NewsItem]:
    """Memindai seluruh NewsItem sumber Twitter yang terindikasi teks Bahasa Indonesia."""
    query = select(NewsItem).where(NewsItem.source == "twitter").order_by(NewsItem.fetched_at.desc())
    result = await session.execute(query)
    all_twitter_news = result.scalars().all()

    affected_items = []
    for item in all_twitter_news:
        text = f"{item.title or ''} {item.summary or ''}".lower()
        if any(marker in text for marker in INDONESIAN_MARKERS):
            affected_items.append(item)

    return affected_items


async def run_sanitization(apply_changes: bool = False, limit_display: int = 15):
    """Menjalankan proses audit / sanitasi pada database PostgreSQL."""
    logger.info("==> Memulai pemindaian berita Bahasa Indonesia di database...")

    async with get_session() as session:
        total_news = (await session.execute(select(func.count(NewsItem.id)))).scalar_one()
        total_twitter = (await session.execute(
            select(func.count(NewsItem.id)).where(NewsItem.source == "twitter")
        )).scalar_one()

        affected = await scan_indonesian_news(session)

        logger.info(f"Total NewsItem di database: {total_news}")
        logger.info(f"Total Berita Twitter: {total_twitter}")
        logger.info(f"Ditemukan {len(affected)} berita Twitter dengan indikasi terjemahan Bahasa Indonesia.")

        if not affected:
            logger.info("[OK] Tidak ditemukan record berita yang terkontaminasi.")
            return

        print("\n" + "=" * 90)
        print(f" {'ID':<8} | {'FETCHED AT':<24} | {'TITLE':<52}")
        print("=" * 90)
        for item in affected[:limit_display]:
            time_str = item.fetched_at.strftime("%Y-%m-%d %H:%M:%S") if item.fetched_at else "-"
            title_str = (item.title or "")[:50]
            print(f" {item.id:<8} | {time_str:<24} | {title_str:<52}")

        if len(affected) > limit_display:
            print(f" ... dan {len(affected) - limit_display} record lainnya.")
        print("=" * 90 + "\n")

        if apply_changes:
            logger.info(f"Menerapkan remediasi pada {len(affected)} record...")
            affected_ids = [item.id for item in affected]
            await session.execute(
                update(NewsItem)
                .where(NewsItem.id.in_(affected_ids))
                .values(
                    impact="LOW",
                    prefilter_flags="TRANSLATED_LEGACY"
                )
            )
            await session.commit()
            logger.info(f"[SUCCESS] Berhasil memperbarui {len(affected)} record dengan flag 'TRANSLATED_LEGACY' & impact='LOW'.")
        else:
            logger.info("[DRY-RUN] Tidak ada perubahan database yang disimpan. Gunakan flag '--apply' untuk mengeksekusi remediasi.")


def main():
    parser = argparse.ArgumentParser(description="Audit & Sanitize Indonesian-translated news items in DB")
    parser.add_argument("--apply", action="store_true", help="Eksekusi perubahan status pada database")
    parser.add_argument("--limit", type=int, default=15, help="Jumlah sampel yang ditampilkan")
    args = parser.parse_args()
    import sys
    if sys.platform == "win32":
        asyncio.run(run_sanitization(apply_changes=args.apply, limit_display=args.limit), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(run_sanitization(apply_changes=args.apply, limit_display=args.limit))


if __name__ == "__main__":
    main()
