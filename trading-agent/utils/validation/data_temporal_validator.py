"""
IMP-10: Temporal Relationship Tracking untuk Multi-Hop Queries.
Lightweight knowledge graph alternative untuk memvalidasi konsistensi
timestamp antar data sources dalam analysis chain.
"""
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger("TradingAgent.DataTemporalValidator")


class DataTemporalValidator:
    """
    Validates temporal consistency across data sources.
    Lightweight alternative to full Knowledge Graph.
    Ensures that all data used in an analysis chain is temporally coherent.
    """

    @staticmethod
    async def check_data_freshness_chain(session: AsyncSession, symbol: str) -> dict:
        """
        Check apakah semua data yang digunakan dalam analysis chain
        memiliki temporal consistency.

        Returns dict dengan gap analysis dan recommendations.
        """
        from database.models import (
            PriceOHLCV, FundamentalBrief, VIXData, COTReport
        )

        now = datetime.now(timezone.utc)
        gaps = []
        timestamps = {}

        # OHLCV H4
        try:
            h4_ts = (await session.execute(
                select(PriceOHLCV.timestamp)
                .where(PriceOHLCV.symbol == symbol)
                .where(PriceOHLCV.timeframe == 'H4')
                .order_by(PriceOHLCV.timestamp.desc())
                .limit(1)
            )).scalar_one_or_none()
            timestamps['h4_ohlcv'] = h4_ts
        except Exception as e:
            logger.debug(f"H4 OHLCV timestamp fetch failed: {e}")
            try:
                await session.rollback()
            except Exception:
                pass
            h4_ts = None
            timestamps['h4_ohlcv'] = None

        # COT Report
        try:
            cot_ts = (await session.execute(
                select(COTReport.report_date)
                .order_by(COTReport.report_date.desc())
                .limit(1)
            )).scalar_one_or_none()
            timestamps['cot'] = cot_ts
        except Exception as e:
            logger.debug(f"COT timestamp fetch failed: {e}")
            try:
                await session.rollback()
            except Exception:
                pass
            cot_ts = None
            timestamps['cot'] = None

        # Fundamental Brief
        try:
            brief_ts = (await session.execute(
                select(FundamentalBrief.generated_at)
                .order_by(FundamentalBrief.generated_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            timestamps['fundamental_brief'] = brief_ts
        except Exception as e:
            logger.debug(f"FundamentalBrief timestamp fetch failed: {e}")
            try:
                await session.rollback()
            except Exception:
                pass
            brief_ts = None
            timestamps['fundamental_brief'] = None

        # VIX
        try:
            vix_ts = (await session.execute(
                select(VIXData.date)
                .order_by(VIXData.date.desc())
                .limit(1)
            )).scalar_one_or_none()
            timestamps['vix'] = vix_ts
        except Exception as e:
            logger.debug(f"VIX timestamp fetch failed: {e}")
            try:
                await session.rollback()
            except Exception:
                pass
            vix_ts = None
            timestamps['vix'] = None

        # Use H4 as reference
        reference = h4_ts
        if not reference:
            return {
                'coherent': False,
                'gaps': ['No H4 OHLCV data found — cannot validate temporal coherence'],
                'timestamps': {k: v.isoformat() if hasattr(v, 'isoformat') else str(v) if v else None
                               for k, v in timestamps.items()},
                'reference_h4_age_hours': None,
            }

        # Ensure reference is timezone-aware
        if hasattr(reference, 'tzinfo') and reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)

        h4_age_hours = (now - reference).total_seconds() / 3600

        # COT: acceptable if < 14 days from H4 reference
        if cot_ts:
            cot_aware = cot_ts if (hasattr(cot_ts, 'tzinfo') and cot_ts.tzinfo) else (
                datetime(cot_ts.year, cot_ts.month, cot_ts.day, tzinfo=timezone.utc)
                if hasattr(cot_ts, 'year') else None
            )
            if cot_aware:
                cot_age_days = (reference - cot_aware).total_seconds() / 86400
                if cot_age_days > 14:
                    gaps.append(
                        f'COT data {cot_age_days:.0f} days before H4 data — '
                        f'institutional positioning may be stale'
                    )

        # Fundamental brief: should be fresher than 2x H4 age
        if brief_ts:
            brief_aware = brief_ts if (hasattr(brief_ts, 'tzinfo') and brief_ts.tzinfo) else \
                brief_ts.replace(tzinfo=timezone.utc)
            brief_age_hours = (now - brief_aware).total_seconds() / 3600
            if brief_age_hours > max(h4_age_hours * 2, 6.0):
                gaps.append(
                    f'Fundamental brief ({brief_age_hours:.1f}h old) is much older than H4 data '
                    f'({h4_age_hours:.1f}h) — macro context may not reflect current market'
                )

        # H4 data staleness check (aware of forex weekend vs crypto 24/7)
        is_crypto = symbol.upper() in ("BTCUSD", "ETHUSD", "SOLUSD", "BTC", "ETH")
        is_forex_weekend = now.weekday() == 5 or (now.weekday() == 6 and now.hour < 21) or (now.weekday() == 4 and now.hour >= 22)
        
        if not is_crypto and is_forex_weekend:
            if h4_age_hours > 60:
                gaps.append(
                    f'H4 OHLCV is {h4_age_hours:.1f}h old over weekend — data feed may be stale'
                )
        else:
            if h4_age_hours > 5:
                gaps.append(
                    f'H4 OHLCV is {h4_age_hours:.1f}h old — MT5 may be disconnected or data feed stale'
                )

        return {
            'coherent': len(gaps) == 0,
            'gaps': gaps,
            'timestamps': {
                k: v.isoformat() if hasattr(v, 'isoformat') else str(v) if v else None
                for k, v in timestamps.items()
            },
            'reference_h4_age_hours': h4_age_hours,
        }

    @staticmethod
    async def validate_and_warn(session: AsyncSession, symbol: str) -> str:
        """
        Convenience method: run check and return warning string for bundle injection.
        Returns empty string if coherent, warning text if gaps found.
        """
        try:
            result = await DataTemporalValidator.check_data_freshness_chain(session, symbol)
            if not result['coherent']:
                warning_lines = ['⚠️ TEMPORAL DATA COHERENCE WARNINGS:']
                for gap in result['gaps']:
                    warning_lines.append(f'  - {gap}')
                warning_lines.append('Consider these gaps when weighting your confluence factors.')
                return '\n'.join(warning_lines)
        except Exception as e:
            logger.debug(f'Temporal validation failed (non-fatal): {e}')
        return ''
