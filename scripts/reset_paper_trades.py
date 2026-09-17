#!/usr/bin/env python
"""
==============================================================================
Script: scripts/reset_paper_trades.py
==============================================================================

CLI utility untuk mereset riwayat paper trading (simulasi), mereset loss streak ke 0,
dan membuka seluruh kuncian/suspensi di Monika.

Penggunaan:
    # Mode Preview / Dry-run (tanpa menghapus data)
    python scripts/reset_paper_trades.py

    # Eksekusi reset & buka kuncian dengan konfirmasi
    python scripts/reset_paper_trades.py --confirm

    # Eksekusi tanpa membuat backup (tidak disarankan)
    python scripts/reset_paper_trades.py --confirm --no-backup
"""

import sys
import os
import argparse
import asyncio

# Pastikan trading-agent masuk ke sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRADING_AGENT_DIR = os.path.join(BASE_DIR, "trading-agent")
if TRADING_AGENT_DIR not in sys.path:
    sys.path.insert(0, TRADING_AGENT_DIR)


async def main():
    parser = argparse.ArgumentParser(
        description="Reset paper trading history, reset loss streaks to 0, and clear all suspensions."
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Konfirmasi eksekusi penghapusan database (wajib untuk melakukan perubahan).",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        default=False,
        help="Lewati pembuatan file backup JSON sebelum penghapusan.",
    )
    parser.add_argument(
        "--no-unlock",
        action="store_true",
        default=False,
        help="Jangan membuka kuncian/suspensi (hanya hapus paper trades).",
    )
    args = parser.parse_args()

    from dotenv import load_dotenv
    # Load .env dari direktori trading-agent jika ada
    env_path = os.path.join(TRADING_AGENT_DIR, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv()

    from database.db import AsyncSessionLocal
    from database.models import (
        PaperTradeRecord, Position, MT5Signal, DecisionReflection,
        SystemConfig, RiskState
    )
    from database.cleanup import reset_paper_trading_history
    from sqlalchemy import select, func

    print("=" * 65)
    print(" MONIKA — RESET PAPER TRADING & LOSS STREAK UTILITY")
    print("=" * 65)

    async with AsyncSessionLocal() as session:
        # Audit status saat ini
        pt_count = await session.scalar(select(func.count(PaperTradeRecord.id)))
        pos_count = await session.scalar(
            select(func.count(Position.id)).where(Position.is_paper == True)
        )
        sig_count = await session.scalar(select(func.count(MT5Signal.id)))
        refl_count = await session.scalar(select(func.count(DecisionReflection.id)))

        risk_row = (await session.execute(
            select(RiskState).order_by(RiskState.date.desc()).limit(1)
        )).scalar_one_or_none()
        is_paused = risk_row.trading_paused if risk_row else False

        susp_cfg = (await session.execute(
            select(SystemConfig.value).where(SystemConfig.key == "suspended_symbols")
        )).scalar_one_or_none()

        fc_count = await session.scalar(
            select(func.count(SystemConfig.key)).where(SystemConfig.key.like("flash_crash_blocked_%"))
        )
        autopsy_count = await session.scalar(
            select(func.count(SystemConfig.key)).where(SystemConfig.key.like("autopsy_%"))
        )

        print(f"Status Saat Ini di Database:")
        print(f"  • Paper Trade Records : {pt_count}")
        print(f"  • Paper Positions     : {pos_count}")
        print(f"  • MT5 Signals         : {sig_count}")
        print(f"  • Decision Reflections: {refl_count}")
        print(f"  • Trading Paused      : {is_paused}")
        print(f"  • Suspended Symbols   : {susp_cfg or '[]'}")
        print(f"  • Flash Crash Blocks  : {fc_count}")
        print(f"  • Autopsy Records     : {autopsy_count}")
        print("-" * 65)

        if not args.confirm:
            print("[DRY-RUN / PREVIEW MODE]")
            print("Tidak ada perubahan yang dilakukan ke database.")
            print("Untuk mengeksekusi reset dan membuka kuncian, jalankan:")
            print("    python scripts/reset_paper_trades.py --confirm\n")
            return

        print("[EKSEKUSI RESET SEDANG BERJALAN...]")
        res = await reset_paper_trading_history(
            session=session,
            create_backup=not args.no_backup,
            unlock_all=not args.no_unlock,
        )

        # Verifikasi setelah reset
        pt_after = await session.scalar(select(func.count(PaperTradeRecord.id)))
        pos_after = await session.scalar(
            select(func.count(Position.id)).where(Position.is_paper == True)
        )
        risk_after = (await session.execute(
            select(RiskState).order_by(RiskState.date.desc()).limit(1)
        )).scalar_one_or_none()
        paused_after = risk_after.trading_paused if risk_after else False

        print("\nHasil Eksekusi:")
        if res.get("backup_file"):
            print(f"  [OK] Backup tersimpan di: {res['backup_file']}")
        print(f"  [OK] Paper trades dihapus : {res['paper_trades_deleted']} (sisa: {pt_after})")
        print(f"  [OK] Posisi paper dihapus : {res['positions_deleted']} (sisa: {pos_after})")
        print(f"  [OK] MT5 signals dihapus  : {res['signals_deleted']}")
        print(f"  [OK] Refleksi dihapus     : {res['reflections_deleted']}")
        print(f"  [OK] Autopsi dihapus      : {res['autopsies_deleted']}")
        print(f"  [OK] Flash crash dihapus  : {res['flash_crash_blocks_deleted']}")
        print(f"  [OK] Simbol di-unsuspend  : {res.get('symbols_unsuspended', [])}")
        print(f"  [OK] Ambang batas di-reset: {res['adaptive_thresholds_reset']}")
        print(f"  [OK] Trading paused       : {paused_after} (False = AKTIF)")
        print("\n[SUKSES] Riwayat paper trade bersih (0) & seluruh kuncian telah dibuka!")
        print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
