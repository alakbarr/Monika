import json
import logging
from datetime import datetime, timezone
from typing import Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger('TradingAgent.CoreDataValidator')


class CoreDataValidator:
    """
    Validates core shared data before it's broadcast to all Stage 2 agents.
    
    Implements the key insight from SSVP research: selective validation of
    shared state to prevent simultaneous contamination of all agents.
    """
    
    def __init__(self, session: AsyncSession, settings: dict):
        self.session = session
        self.settings = settings
    
    async def validate_and_fetch_core_data(self) -> Tuple[bool, dict, list[str]]:
        """
        Fetch dan validate semua core shared data.
        
        Returns:
            (is_valid: bool, core_data: dict, issues: list[str])
        """
        issues = []
        core_data = {}
        
        # 1. Validate FundamentalBrief
        brief_valid, brief_data, brief_issue = await self._validate_brief()
        if not brief_valid:
            issues.append(brief_issue)
        else:
            core_data['fundamental_brief'] = brief_data
        
        # 2. Validate VIX
        vix_valid, vix_data, vix_issue = await self._validate_vix()
        if not vix_valid:
            issues.append(vix_issue)
        else:
            core_data['vix'] = vix_data
        
        # 3. Validate DXY
        dxy_valid, dxy_data, dxy_issue = await self._validate_dxy()
        if not dxy_valid:
            issues.append(dxy_issue)
        else:
            core_data['dxy'] = dxy_data
        
        # 4. Cross-validate: DXY trend vs USD bias in brief
        if brief_valid and dxy_valid:
            cross_valid, cross_issue = self._cross_validate_dxy_vs_brief(
                dxy_data, brief_data
            )
            if not cross_valid:
                issues.append(cross_issue)
                core_data['cross_validation_warning'] = cross_issue
        
        # Determine overall validity
        # Critical issues = brief invalid
        # Non-critical issues = vix/dxy stale but still usable with warning
        critical_invalid = not brief_valid
        
        if critical_invalid:
            logger.error(f"CoreDataValidator: Critical failure — {'; '.join(issues)}")
            return (False, core_data, issues)
        
        if issues:
            logger.warning(f"CoreDataValidator: Non-critical issues — {'; '.join(issues)}")
        
        return (True, core_data, issues)
    
    async def _validate_brief(self) -> Tuple[bool, dict, str]:
        from database.models import FundamentalBrief
        
        brief = (await self.session.execute(
            select(FundamentalBrief).order_by(FundamentalBrief.generated_at.desc()).limit(1)
        )).scalar_one_or_none()
        
        if not brief:
            return (False, {}, "No fundamental brief in database")
        
        max_age = self.settings.get('data_quality', {}).get('max_brief_age_analysis_hours', 12.0)
        age_hours = (
            datetime.now(timezone.utc) - (
                brief.generated_at.replace(tzinfo=timezone.utc)
                if brief.generated_at.tzinfo is None
                else brief.generated_at
            )
        ).total_seconds() / 3600
        
        if age_hours > max_age:
            return (False, {}, f"Brief is {age_hours:.1f}h old (limit: {max_age}h)")
        
        if not brief.structured_json:
            return (False, {}, "Brief missing structured_json")
        
        try:
            structured = json.loads(brief.structured_json)
        except Exception:
            return (False, {}, "Brief structured_json is malformed JSON")
        
        # Validate required fields
        currency_bias = structured.get('currency_bias', {})
        required_currencies = ['USD', 'EUR', 'GBP', 'JPY', 'AUD', 'XAU']
        missing = [c for c in required_currencies if c not in currency_bias]
        
        if len(missing) > 3:  # Allow up to 3 missing (e.g., weekend BTC-only mode)
            return (False, {}, f"Brief missing currency biases: {missing}")
        
        return (True, {
            'id': brief.id,
            'generated_at': brief.generated_at.isoformat(),
            'age_hours': round(age_hours, 2),
            'structured': structured,
            'currency_bias': currency_bias,
            'risk_sentiment': structured.get('risk_sentiment', 'mixed'),
            'confidence': structured.get('confidence', 0.5)
        }, "")
    
    async def _validate_vix(self) -> Tuple[bool, dict, str]:
        from database.models import VIXData
        
        vix = (await self.session.execute(
            select(VIXData).order_by(VIXData.date.desc()).limit(1)
        )).scalar_one_or_none()
        
        if not vix:
            return (False, {}, "No VIX data")
        
        now = datetime.now(timezone.utc)
        vix_date = vix.date
        
        # Ensure vix_date is datetime for subtraction
        if not isinstance(vix_date, datetime):
            import datetime as _dt
            if isinstance(vix_date, _dt.date):
                vix_date = datetime.combine(vix_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            else:
                logger.error(f"[CoreDataValidator] VIX date is not datetime: {type(vix_date)}")
                
        if hasattr(vix_date, 'tzinfo') and vix_date.tzinfo is None:
            vix_date = vix_date.replace(tzinfo=timezone.utc)
        
        age_days = (now - vix_date).days
        is_weekend = now.weekday() >= 5
        
        if age_days > 5 and not is_weekend:
            return (False, {}, f"VIX data is {age_days} days old (non-weekend)")
        
        if vix.close <= 0 or vix.close > 200:
            return (False, {}, f"VIX value {vix.close} is implausible")
        
        return (True, {
            'close': vix.close,
            'date': vix.date.strftime('%Y-%m-%d'),
            'age_days': age_days
        }, "")
    
    async def _validate_dxy(self) -> Tuple[bool, dict, str]:
        from database.models import DXYData
        
        rows = (await self.session.execute(
            select(DXYData).order_by(DXYData.date.desc()).limit(5)
        )).scalars().all()
        
        if not rows:
            return (False, {}, "No DXY data")
        
        latest = rows[0]
        if latest.close <= 80 or latest.close >= 130:
            return (False, {}, f"DXY value {latest.close} is implausible")
        
        trend = 'unknown'
        if len(rows) >= 3:
            trend = 'strengthening' if rows[0].close > rows[-1].close else 'weakening'
        
        return (True, {
            'latest_close': latest.close,
            'trend_5d': trend,
            'date': latest.date.strftime('%Y-%m-%d')
        }, "")
    
    def _cross_validate_dxy_vs_brief(
        self, dxy_data: dict, brief_data: dict
    ) -> Tuple[bool, str]:
        """
        Cross-validate: apakah DXY trend konsisten dengan USD bias di brief?
        
        DXY strengthening = USD bullish
        DXY weakening = USD bearish
        """
        from utils.market.bias_utils import normalize_bias
        dxy_trend = dxy_data.get('trend_5d', 'unknown')
        currency_bias = brief_data.get('currency_bias', {})
        usd_bias = normalize_bias(currency_bias.get('USD', 'neutral'))
        
        if dxy_trend == 'unknown' or usd_bias == 'neutral':
            return (True, "")  # Cannot cross-validate, skip
        
        contradicts = (
            (dxy_trend == 'strengthening' and usd_bias == 'bearish') or
            (dxy_trend == 'weakening' and usd_bias == 'bullish')
        )
        
        if contradicts:
            return (
                False,
                f"CORE DATA CONTRADICTION: DXY={dxy_trend} but brief says USD='{usd_bias}'. "
                f"DXY is price-based (more current). Brief USD bias may be stale. "
                f"Stage 2 agents should weight DXY signal over brief for USD direction."
            )
        
        return (True, "")
