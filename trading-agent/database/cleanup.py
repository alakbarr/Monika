# ==============================================================================
# File: database/cleanup.py
# ==============================================================================

import logging
from typing import Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import (
    PriceOHLCV, AssetAnalysis, FundamentalBrief, ActivityLog,
    OrderLog, NewsItem, EconomicCalendar, VIXData, RiskState, TechnicalIndicator, ConfluenceFactorOutcome,
    SwingPoint, LiquidityZone, FVGZone, OrderBlock, StructureBreak, TokenUsageLog, PrescreenLog, NewsDigest
)

logger = logging.getLogger("TradingAgent.DBCleanup")


async def cleanup_old_data(session: AsyncSession, settings: Optional[dict] = None):
    """
    Hapus data lama untuk mencegah db bloat, menggunakan kebijakan retensi dari settings['data_retention_days'].

    Catatan Penting: OHLCV D1 disimpan minimal 400 hari agar indikator seperti SMA/EMA 200 (butuh 205 bar) 
    memiliki historis yang cukup. OHLCV H1/H4 mengikuti konfigurasi standar (default: 60 hari).

    Args:
        session: Session async SQLAlchemy.
        settings: Dict konfigurasi (opsional). Jika None, gunakan nilai default bawaan.
    """
    retention_cfg = (settings or {}).get("data_retention_days", {})

    # Batas retensi (hari) per tabel. OHLCV ditangani khusus per timeframe.
    # Floor pengaman wajar: D1 >= 205 hari (SMA200 butuh 205 bar), H1/H4 >= 30 hari, M15 >= 3 hari.
    ohlcv_h1_h4_days = max(int(retention_cfg.get("ohlcv_h1_h4", 60)), 30)
    ohlcv_m15_days   = max(int(retention_cfg.get("ohlcv_m15", 7)), 3)
    ohlcv_d1_days    = max(int(retention_cfg.get("ohlcv_d1", 400)), 205)
    news_days        = int(retention_cfg.get("news_items", 30))
    activity_days    = int(retention_cfg.get("activity_log", 90))
    analysis_days    = int(retention_cfg.get("asset_analysis", 60))
    brief_days       = int(retention_cfg.get("fundamental_brief", 60))
    order_log_days   = int(retention_cfg.get("order_log", 90))
    calendar_days    = int(retention_cfg.get("economic_calendar", 30))
    vix_days         = int(retention_cfg.get("vix_data", 60))
    risk_state_days  = int(retention_cfg.get("risk_state", 90))
    smc_days         = int(retention_cfg.get("smc_zones", 60))
    token_log_days   = int(retention_cfg.get("token_usage_log", 90))
    prescreen_days   = int(retention_cfg.get("prescreen_log", 30))
    digest_days      = int(retention_cfg.get("news_digest", 30))

    now = datetime.now(timezone.utc)
    total_deleted = 0

    try:
        # ---- PriceOHLCV: Retensi per timeframe ----
        # Bar M15: retensi sangat pendek untuk akurasi paper trade
        m15_cutoff = now - timedelta(days=ohlcv_m15_days)
        result = await session.execute(
            delete(PriceOHLCV).where(
                and_(
                    PriceOHLCV.timeframe == "M15",
                    PriceOHLCV.timestamp < m15_cutoff,
                )
            )
        )
        m15_deleted = getattr(result, "rowcount", 0) or 0
        if m15_deleted > 0:
            logger.info(f"Deleted {m15_deleted} old M15 OHLCV rows (kept >= {ohlcv_m15_days} days)")
        total_deleted += m15_deleted

        # Bar D1: simpan >= 400 hari agar SMA_200 bisa dihitung
        d1_cutoff = now - timedelta(days=ohlcv_d1_days)
        result = await session.execute(
            delete(PriceOHLCV).where(
                and_(
                    PriceOHLCV.timeframe == "D1",
                    PriceOHLCV.timestamp < d1_cutoff,
                )
            )
        )
        d1_deleted = getattr(result, "rowcount", 0) or 0
        if d1_deleted > 0:
            logger.info(f"Deleted {d1_deleted} old D1 OHLCV rows (kept >= {ohlcv_d1_days} days)")
        total_deleted += d1_deleted

        # Bar H1/H4: retensi lebih pendek
        h_cutoff = now - timedelta(days=ohlcv_h1_h4_days)
        result = await session.execute(
            delete(PriceOHLCV).where(
                and_(
                    PriceOHLCV.timeframe.in_(["H1", "H4"]),
                    PriceOHLCV.timestamp < h_cutoff,
                )
            )
        )
        h_deleted = getattr(result, "rowcount", 0) or 0
        if h_deleted > 0:
            logger.info(f"Deleted {h_deleted} old H1/H4 OHLCV rows (kept >= {ohlcv_h1_h4_days} days)")
        total_deleted += h_deleted

        # ---- Tabel lainnya: satu batasan per tabel ----
        other_targets = [
            (AssetAnalysis,   "generated_at",  analysis_days,  "AssetAnalysis"),
            (FundamentalBrief,"generated_at",  brief_days,     "FundamentalBrief"),
            (ActivityLog,     "timestamp",     activity_days,  "ActivityLog"),
            (OrderLog,        "timestamp",     order_log_days, "OrderLog"),
            (NewsItem,        "published_at",  news_days,      "NewsItem"),
            (EconomicCalendar,"event_time",    calendar_days,  "EconomicCalendar"),
            (VIXData,         "date",          vix_days,       "VIXData"),
            (RiskState,       "date",          risk_state_days,"RiskState"),
            (TechnicalIndicator, "timestamp",  ohlcv_h1_h4_days, "TechnicalIndicator"),
            (ConfluenceFactorOutcome, "recorded_at", analysis_days, "ConfluenceFactorOutcome"),
            (SwingPoint,      "timestamp",     smc_days,       "SwingPoint"),
            (LiquidityZone,   "identified_at", smc_days,       "LiquidityZone"),
            (FVGZone,         "formed_at",     smc_days,       "FVGZone"),
            (OrderBlock,      "formed_at",     smc_days,       "OrderBlock"),
            (StructureBreak,  "formed_at",     smc_days,       "StructureBreak"),
            (TokenUsageLog,   "timestamp",     token_log_days, "TokenUsageLog"),
            (PrescreenLog,    "checked_at",    prescreen_days, "PrescreenLog"),
            (NewsDigest,      "generated_at",  digest_days,    "NewsDigest"),
        ]

        for model, col_name, days, label in other_targets:
            cutoff = now - timedelta(days=days)
            col = getattr(model, col_name)
            
            # Fix FK violation: Delete dependent NewsClassificationOutcomes first
            if model == NewsItem:
                from database.models import NewsClassificationOutcome
                from sqlalchemy import select
                await session.execute(
                    delete(NewsClassificationOutcome).where(
                        NewsClassificationOutcome.news_item_id.in_(
                            select(NewsItem.id).where(or_(NewsItem.published_at < cutoff, NewsItem.published_at.is_(None)))
                        )
                    )
                )
            elif model == AssetAnalysis:
                from database.models import (
                    TradeTrigger, MT5Signal, TradeOutcome, PaperTradeRecord, Position, DecisionReflection,
                    Order, TradePlan
                )
                from sqlalchemy import select, update
                expired_analysis_ids = select(AssetAnalysis.id).where(AssetAnalysis.generated_at < cutoff)
                # Preserve long-term memory: nullify analysis_id instead of purging reflections
                await session.execute(
                    update(DecisionReflection).where(
                        DecisionReflection.analysis_id.in_(expired_analysis_ids)
                    ).values(analysis_id=None)
                )
                # Nullify FK references in Order and TradePlan to prevent FK constraint failures
                await session.execute(
                    update(Order).where(
                        Order.analysis_id.in_(expired_analysis_ids)
                    ).values(analysis_id=None)
                )
                await session.execute(
                    update(TradePlan).where(
                        TradePlan.analysis_id.in_(expired_analysis_ids)
                    ).values(analysis_id=None)
                )
                await session.execute(
                    delete(ConfluenceFactorOutcome).where(
                        ConfluenceFactorOutcome.analysis_id.in_(expired_analysis_ids)
                    )
                )
                await session.execute(
                    delete(TradeTrigger).where(
                        TradeTrigger.asset_analysis_id.in_(expired_analysis_ids)
                    )
                )
                await session.execute(
                    delete(MT5Signal).where(
                        MT5Signal.asset_analysis_id.in_(expired_analysis_ids)
                    )
                )
                await session.execute(
                    update(TradeOutcome).where(
                        TradeOutcome.analysis_id.in_(expired_analysis_ids)
                    ).values(analysis_id=None)
                )
                await session.execute(
                    update(PaperTradeRecord).where(
                        PaperTradeRecord.analysis_id.in_(expired_analysis_ids)
                    ).values(analysis_id=None)
                )
                await session.execute(
                    update(Position).where(
                        Position.analysis_id.in_(expired_analysis_ids)
                    ).values(analysis_id=None)
                )
            elif model == FundamentalBrief:
                from sqlalchemy import select, update
                expired_brief_ids = select(FundamentalBrief.id).where(FundamentalBrief.generated_at < cutoff)
                await session.execute(
                    update(AssetAnalysis).where(
                        AssetAnalysis.brief_id.in_(expired_brief_ids)
                    ).values(brief_id=None)
                )

            result = await session.execute(
                delete(model).where(or_(col < cutoff, col.is_(None)))
            )
            deleted = getattr(result, "rowcount", 0) or 0
            if deleted > 0:
                logger.info(f"Deleted {deleted} old records from {label} (kept >= {days} days)")
            total_deleted += deleted

        # ---- Inactive TradeTrigger pruning (fired, cancelled, expired, invalid) ----
        from database.models import TradeTrigger
        trigger_cutoff = now - timedelta(days=14)
        result = await session.execute(
            delete(TradeTrigger).where(
                and_(
                    TradeTrigger.status.in_(["fired", "cancelled", "expired", "invalid"]),
                    TradeTrigger.created_at < trigger_cutoff,
                )
            )
        )
        trigger_deleted = getattr(result, "rowcount", 0) or 0
        if trigger_deleted > 0:
            logger.info(f"Deleted {trigger_deleted} old inactive TradeTrigger rows (kept >= 14 days)")
            total_deleted += trigger_deleted

        # ---- SystemConfig keys pruning ----
        from database.models import SystemConfig
        STALE_SYSCONFIG_PREFIXES_MAX_AGE_DAYS = {
            'context_drift_': 3, 'autopsy_': 30, 'submit_attempt_': 7,
            'news_cls_dist_': 14, 'prefilter_audit_sample_': 7, 'adversarial_outcome_': 60,
        }
        sysconfig_deleted = 0
        for prefix, days in STALE_SYSCONFIG_PREFIXES_MAX_AGE_DAYS.items():
            cutoff = now - timedelta(days=days)
            result = await session.execute(
                delete(SystemConfig).where(
                    and_(
                        SystemConfig.key.like(f"{prefix}%"),
                        SystemConfig.updated_at < cutoff
                    )
                )
            )
            sysconfig_deleted += getattr(result, "rowcount", 0) or 0
        if sysconfig_deleted > 0:
            logger.info(f"Deleted {sysconfig_deleted} old SystemConfig keys")
            total_deleted += sysconfig_deleted

        # ---- Drop Expired Declarative Partitions (PostgreSQL SOTA) ----
        try:
            dropped_parts = await drop_expired_partitions(session, older_than_days=ohlcv_d1_days)
            if dropped_parts > 0:
                logger.info(f"Dropped {dropped_parts} expired PostgreSQL OHLCV table partitions.")
        except Exception as part_err:
            logger.debug(f"Partition cleanup skip: {part_err}")

        await session.commit()
        if total_deleted > 0:
            logger.info(f"Database cleanup complete: {total_deleted} total records removed.")
        else:
            logger.debug("Database cleanup complete: no records needed removal.")

    except Exception as e:
        logger.error(f"Database cleanup failed: {e}")
        await session.rollback()


async def drop_expired_partitions(session: AsyncSession, older_than_days: int = 180) -> int:
    """
    Drop PostgreSQL partitions from price_ohlcv_partitioned whose upper bound is older than cutoff.
    Eliminates MVCC dead-tuples and vacuum bloat via instantaneous DDL DROP.
    """
    try:
        bind = session.bind or session.get_bind()
        if not bind or getattr(bind.dialect, "name", "") != "postgresql":
            return 0

        from sqlalchemy import text
        query = text("""
            SELECT c.relname AS partition_name
            FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid
            JOIN pg_class p ON p.oid = i.inhparent
            WHERE p.relname = 'price_ohlcv_partitioned'
              AND c.relname != 'price_ohlcv_part_default';
        """)
        rows = (await session.execute(query)).fetchall()
        now = datetime.now(timezone.utc)
        cutoff_year = (now - timedelta(days=older_than_days)).year
        cutoff_month = (now - timedelta(days=older_than_days)).month

        dropped_count = 0
        for row in rows:
            part_name = row[0]
            parts = part_name.split("_")
            if len(parts) >= 3 and parts[-2].startswith("y") and parts[-1].startswith("m"):
                try:
                    p_year = int(parts[-2][1:])
                    p_month = int(parts[-1][1:])
                    if (p_year < cutoff_year) or (p_year == cutoff_year and p_month < cutoff_month):
                        logger.warning(f"[PartitionPruning] Dropping expired partition: {part_name}")
                        await session.execute(text(f"DROP TABLE IF EXISTS {part_name} CASCADE;"))
                        dropped_count += 1
                except Exception as parse_err:
                    logger.debug(f"Partition parse skip: {parse_err}")
        return dropped_count
    except Exception as e:
        logger.debug(f"drop_expired_partitions failed (non-fatal): {e}")
        return 0


async def reset_paper_trading_history(
    session: AsyncSession,
    create_backup: bool = True,
    backup_dir: Optional[str] = None,
    unlock_all: bool = True,
) -> dict:
    """
    Mereset seluruh riwayat paper trading (simulasi) dan data terkait secara aman.
    
    Tindakan:
    1. Mencadangkan data paper trade, posisi paper, sinyal, refleksi, dan autopsi ke file JSON.
    2. Menghapus rekaman paper trade dari database:
       - ConfluenceFactorOutcome (paper_trade_id IS NOT NULL)
       - PaperTradeRecord (menyebabkan loss streak otomatis reset ke 0)
       - Position (is_paper == True)
       - MT5Signal (terkait tiket atau analisis paper)
       - DecisionReflection (terkait analisis paper)
    3. Jika unlock_all=True:
       - Menghapus key autopsy_* dan position_exit_review_last_* di SystemConfig
       - Menghapus key flash_crash_blocked_* di SystemConfig
       - Mengosongkan suspended_symbols di SystemConfig
       - Mereset adaptive_threshold_* ke adjustment 0
       - Mereset RiskState.trading_paused ke False
       - Mereset pause flags sistem ke 'false'
    
    Args:
        session: AsyncSession SQLAlchemy aktif.
        create_backup: Apakah membuat backup JSON sebelum penghapusan.
        backup_dir: Direktori penyimpanan backup. Jika None, gunakan 'trading-agent/database/backups'.
        unlock_all: Apakah membuka seluruh kuncian/suspensi dan mereset streak.
        
    Returns:
        dict ringkasan operasi pembersihan dan backup.
    """
    import os
    import json
    from sqlalchemy import select, update
    from database.models import (
        PaperTradeRecord, Position, MT5Signal, DecisionReflection,
        ConfluenceFactorOutcome, SystemConfig, RiskState, TradeOutcome, TradePlanLeg
    )

    now = datetime.now(timezone.utc)
    summary = {
        "status": "success",
        "backup_file": None,
        "paper_trades_deleted": 0,
        "positions_deleted": 0,
        "signals_deleted": 0,
        "reflections_deleted": 0,
        "factor_outcomes_deleted": 0,
        "autopsies_deleted": 0,
        "exit_reviews_deleted": 0,
        "flash_crash_blocks_deleted": 0,
        "symbols_unsuspended": [],
        "adaptive_thresholds_reset": 0,
        "trading_unpaused": False,
    }

    try:
        # 1. Kumpulkan data untuk dicadangkan
        paper_trades = (await session.execute(select(PaperTradeRecord))).scalars().all()
        positions = (await session.execute(
            select(Position).where(Position.is_paper == True)  # noqa: E712
        )).scalars().all()

        paper_analysis_ids = [p.analysis_id for p in paper_trades if p.analysis_id is not None]
        for pos in positions:
            if pos.analysis_id is not None and pos.analysis_id not in paper_analysis_ids:
                paper_analysis_ids.append(pos.analysis_id)

        paper_tickets = [p.mt5_ticket for p in positions if p.mt5_ticket is not None]

        signal_conds = []
        if paper_tickets:
            signal_conds.append(MT5Signal.mt5_ticket.in_(paper_tickets))
        if paper_analysis_ids:
            signal_conds.append(MT5Signal.asset_analysis_id.in_(paper_analysis_ids))

        signals = []
        if signal_conds:
            signals_query = select(MT5Signal).where(or_(*signal_conds))
            signals = (await session.execute(signals_query)).scalars().all()

        reflections = []
        if paper_analysis_ids:
            reflections = (await session.execute(
                select(DecisionReflection).where(DecisionReflection.analysis_id.in_(paper_analysis_ids))
            )).scalars().all()

        factor_outcomes = (await session.execute(
            select(ConfluenceFactorOutcome).where(ConfluenceFactorOutcome.paper_trade_id.isnot(None))
        )).scalars().all()

        autopsies = (await session.execute(
            select(SystemConfig).where(SystemConfig.key.like('autopsy_%'))
        )).scalars().all()

        exit_reviews = (await session.execute(
            select(SystemConfig).where(SystemConfig.key.like('position_exit_review_last_%'))
        )).scalars().all()

        flash_crash_blocks = (await session.execute(
            select(SystemConfig).where(SystemConfig.key.like('flash_crash_blocked_%'))
        )).scalars().all()

        # 2. Buat backup file JSON jika diminta
        if create_backup:
            if not backup_dir:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                backup_dir = os.path.join(base_dir, "backups")
            os.makedirs(backup_dir, exist_ok=True)

            timestamp_str = now.strftime("%Y%m%d_%H%M%S")
            backup_filename = f"paper_trades_backup_{timestamp_str}.json"
            backup_filepath = os.path.join(backup_dir, backup_filename)

            def _dt(v):
                return v.isoformat() if isinstance(v, datetime) else v

            backup_payload = {
                "created_at": now.isoformat(),
                "paper_trades": [
                    {
                        "id": p.id,
                        "analysis_id": p.analysis_id,
                        "symbol": p.symbol,
                        "direction": p.direction,
                        "entry_price": p.entry_price,
                        "stop_loss": p.stop_loss,
                        "take_profit": p.take_profit,
                        "opened_at": _dt(p.opened_at),
                        "filled_at": _dt(p.filled_at),
                        "closed_at": _dt(p.closed_at),
                        "exit_price": p.exit_price,
                        "exit_reason": p.exit_reason,
                        "detection_method": p.detection_method,
                        "risk_pct": p.risk_pct,
                        "pnl_pct": p.pnl_pct,
                        "status": p.status,
                    }
                    for p in paper_trades
                ],
                "positions": [
                    {
                        "id": pos.id,
                        "order_id": pos.order_id,
                        "analysis_id": pos.analysis_id,
                        "mt5_ticket": pos.mt5_ticket,
                        "symbol": pos.symbol,
                        "direction": pos.direction,
                        "volume": pos.volume,
                        "entry_price": pos.entry_price,
                        "sl": pos.sl,
                        "tp": pos.tp,
                        "opened_at": _dt(pos.opened_at),
                        "closed_at": _dt(pos.closed_at),
                        "status": pos.status,
                        "is_paper": pos.is_paper,
                    }
                    for pos in positions
                ],
                "mt5_signals": [
                    {
                        "id": s.id,
                        "analysis_id": s.asset_analysis_id,
                        "symbol": s.symbol,
                        "action": s.action,
                        "status": s.status,
                        "mt5_ticket": s.mt5_ticket,
                        "created_at": _dt(s.created_at),
                        "executed_at": _dt(s.executed_at),
                    }
                    for s in signals
                ],
                "decision_reflections": [
                    {
                        "id": r.id,
                        "analysis_id": r.analysis_id,
                        "symbol": r.symbol,
                        "status": r.status,
                        "created_at": _dt(r.created_at),
                    }
                    for r in reflections
                ],
                "confluence_factor_outcomes": [
                    {
                        "id": c.id,
                        "paper_trade_id": c.paper_trade_id,
                        "symbol": c.symbol,
                        "factor_name": c.factor_name,
                    }
                    for c in factor_outcomes
                ],
                "autopsies": [{c.key: c.value} for c in autopsies],
                "exit_reviews": [{c.key: c.value} for c in exit_reviews],
                "flash_crash_blocks": [{c.key: c.value} for c in flash_crash_blocks],
            }

            with open(backup_filepath, "w", encoding="utf-8") as f:
                json.dump(backup_payload, f, indent=2)

            summary["backup_file"] = backup_filepath
            logger.info(f"[ResetPaper] Backup saved to: {backup_filepath}")

        # 3. Hapus data paper trades secara berurutan
        res_cfo = await session.execute(
            delete(ConfluenceFactorOutcome).where(ConfluenceFactorOutcome.paper_trade_id.isnot(None))
        )
        summary["factor_outcomes_deleted"] = getattr(res_cfo, "rowcount", 0) or len(factor_outcomes)

        res_pt = await session.execute(delete(PaperTradeRecord))
        summary["paper_trades_deleted"] = getattr(res_pt, "rowcount", 0) or len(paper_trades)

        paper_pos_ids = [pos.id for pos in positions if pos.id is not None]
        if paper_pos_ids:
            # Nullify FK references to paper positions to prevent FK constraint violations
            await session.execute(
                update(TradeOutcome).where(TradeOutcome.position_id.in_(paper_pos_ids)).values(position_id=None)
            )
            await session.execute(
                update(TradePlanLeg).where(TradePlanLeg.position_id.in_(paper_pos_ids)).values(position_id=None)
            )
            await session.execute(
                update(DecisionReflection).where(DecisionReflection.position_id.in_(paper_pos_ids)).values(position_id=None)
            )

        res_pos = await session.execute(
            delete(Position).where(Position.is_paper == True)  # noqa: E712
        )
        summary["positions_deleted"] = getattr(res_pos, "rowcount", 0) or len(positions)

        if signal_conds:
            res_sig = await session.execute(
                delete(MT5Signal).where(or_(*signal_conds))
            )
            summary["signals_deleted"] = getattr(res_sig, "rowcount", 0) or len(signals)

        if paper_analysis_ids:
            res_ref = await session.execute(
                delete(DecisionReflection).where(DecisionReflection.analysis_id.in_(paper_analysis_ids))
            )
            summary["reflections_deleted"] = getattr(res_ref, "rowcount", 0) or len(reflections)

        # 4. Buka seluruh kuncian & suspensi jika unlock_all=True
        if unlock_all:
            res_auto = await session.execute(delete(SystemConfig).where(SystemConfig.key.like('autopsy_%')))
            summary["autopsies_deleted"] = getattr(res_auto, "rowcount", 0) or len(autopsies)

            res_ex = await session.execute(delete(SystemConfig).where(SystemConfig.key.like('position_exit_review_last_%')))
            summary["exit_reviews_deleted"] = getattr(res_ex, "rowcount", 0) or len(exit_reviews)

            res_fc = await session.execute(delete(SystemConfig).where(SystemConfig.key.like('flash_crash_blocked_%')))
            summary["flash_crash_blocks_deleted"] = getattr(res_fc, "rowcount", 0) or len(flash_crash_blocks)

            # Kosongkan suspended_symbols
            susp_cfg = (await session.execute(
                select(SystemConfig).where(SystemConfig.key == 'suspended_symbols')
            )).scalar_one_or_none()
            if susp_cfg:
                try:
                    old_susp = json.loads(susp_cfg.value or "[]")
                    summary["symbols_unsuspended"] = [s.get("symbol") for s in old_susp if s.get("symbol")]
                except Exception:
                    pass
                susp_cfg.value = "[]"
            else:
                session.add(SystemConfig(key="suspended_symbols", value="[]"))

            # Reset adaptive_threshold_* ke 0
            adapt_cfgs = (await session.execute(
                select(SystemConfig).where(SystemConfig.key.like('adaptive_threshold_%'))
            )).scalars().all()
            for ac in adapt_cfgs:
                ac.value = json.dumps({"adjustment": 0, "set_at": now.isoformat()})
            summary["adaptive_thresholds_reset"] = len(adapt_cfgs)

            # Reset RiskState.trading_paused
            recent_risk = (await session.execute(
                select(RiskState).order_by(RiskState.date.desc()).limit(10)
            )).scalars().all()
            for r in recent_risk:
                r.trading_paused = False
            summary["trading_unpaused"] = True

            # Pastikan pause flags sistem di-set false
            for pkey in ("kill_switch", "system_paused", "budget_pause", "trading_paused", "manual_trading_paused"):
                pcfg = (await session.execute(
                    select(SystemConfig).where(SystemConfig.key == pkey)
                )).scalar_one_or_none()
                if pcfg:
                    pcfg.value = "false"
                else:
                    session.add(SystemConfig(key=pkey, value="false"))

        await session.commit()
        logger.info(
            f"[ResetPaper] Reset complete: {summary['paper_trades_deleted']} paper trades deleted, "
            f"{summary['positions_deleted']} positions deleted, all locks cleared."
        )
        return summary

    except Exception as e:
        logger.error(f"[ResetPaper] Failed to reset paper trading history: {e}")
        await session.rollback()
        raise
