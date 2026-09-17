from typing import Any, Optional
import json
from datetime import datetime, timezone

class ToolResponseValidator:
    
    SANITY_CHECKS = {
        'get_atr': {
            'path': ['atr_14'],
            'min_value': 0.00001,
            'max_value': 10000.0,
            'error_msg': 'ATR_14 value out of valid range'
        },
        'get_vix': {
            'path': ['latest', 'close'],
            'min_value': 5.0,
            'max_value': 200.0,
            'error_msg': 'VIX value out of valid range (5-200)'
        },
        'get_technical_indicators': {
            'required_keys': ['indicators', 'symbol', 'timeframe'],
            'forbidden_stale': True,
            'stale_key': 'staleness_warning',
        },
        'get_fundamental_brief': {
            'required_keys': ['currency_bias', 'confidence', 'risk_sentiment', 'macro_narrative'],
        },
        'get_price_history': {
            'required_keys': ['symbol', 'timeframe', 'bars'],
            'custom_validator': 'validate_price_history'
        },
        'get_cot_report': {
            'required_keys': ['count', 'reports'],
            'custom_validator': 'validate_cot_report'
        },
        'get_swing_points': {
            'required_keys': ['swing_highs', 'swing_lows'],
        },
        'get_fedwatch_probabilities': {
            'required_keys': ['meetings'],
            'custom_validator': 'validate_fedwatch'
        },
        'get_dxy': {
            'required_keys': ['latest', 'trend_5d'],
            'path': ['latest', 'close'],
            'min_value': 80.0,
            'max_value': 130.0,
            'error_msg': 'DXY value out of valid range (80-130)'
        },
        'get_treasury_yields': {
            'required_keys': ['yields_by_tenor'],
        },
        'get_smc_zones': {
            'required_keys': ['order_blocks', 'fvg_zones', 'liquidity_zones'],
        },
    }
    
    @classmethod
    def validate_and_sanitize(cls, tool_name: str, result: dict) -> tuple[dict, bool, str]:
        if not isinstance(result, dict):
            return (result, False, f'Tool {tool_name} returned non-dict: {type(result)}')
        
        if 'error' in result:
            return (result, False, f"Tool {tool_name} error: {result['error']}")
        
        checks = cls.SANITY_CHECKS.get(tool_name, {})
        
        # Required keys check
        required = checks.get('required_keys', [])
        missing = [k for k in required if k not in result]
        if missing:
            return (result, False, f'Tool {tool_name} missing: {missing}')
        
        # Numeric range check
        path = checks.get('path')
        if path:
            try:
                curr: Any = result
                for key in path:
                    curr = curr[key]
                numeric_val = float(curr)
                min_v = checks.get('min_value', float('-inf'))
                max_v = checks.get('max_value', float('inf'))
                if not (min_v <= numeric_val <= max_v):
                    warning = f'{tool_name} value {numeric_val} outside valid range [{min_v}, {max_v}]'
                    return (result, False, warning)
            except (KeyError, TypeError, ValueError):
                pass  # Path doesn't exist or not numeric, skip check
        
        # Staleness warning check
        if checks.get('forbidden_stale') and result.get(checks.get('stale_key', '')):
            stale_msg = result.get(checks.get('stale_key', ''), '')
            if 'STALE DATA' in str(stale_msg).upper():
                return (result, False, f'Tool {tool_name} returned stale data: {stale_msg[:100]}')
        
        custom_validator_name = checks.get('custom_validator')
        if custom_validator_name:
            validator_fn = getattr(cls, f'_{custom_validator_name}', None)
            if validator_fn:
                ok, msg = validator_fn(result)
                if not ok:
                    return result, False, f'{tool_name}: {msg}'

        result['_validated'] = True
        return (result, True, '')
    
    @classmethod
    def _validate_price_history(cls, result: dict) -> tuple[bool, str]:
        bars = result.get('bars', [])
        if not bars:
            return False, 'Price history returned empty bars list'
        # Check for obviously anomalous prices
        for bar in bars[-5:]:  # Check last 5 bars
            for field in ['open', 'high', 'low', 'close']:
                val = bar.get(field, 0)
                if val <= 0:
                    return False, f'Price bar has invalid {field}={val}'
                if bar.get('high', 0) < bar.get('low', 0):
                    return False, f'Price bar has high < low: {bar}'
        return True, ''

    @classmethod
    def _validate_cot_report(cls, result: dict) -> tuple[bool, str]:
        for report in result.get('reports', []):
            lev_long = report.get('leveraged_funds', {}).get('long', 0)
            lev_short = report.get('leveraged_funds', {}).get('short', 0)
            if lev_long < 0 or lev_short < 0:
                return False, f'COT data has negative positions: {report}'
            if lev_long + lev_short > 1_000_000:
                return False, f'COT data has implausible position sizes'
        return True, ''

    @classmethod
    def _validate_fedwatch(cls, result: dict) -> tuple[bool, str]:
        if not result.get('meetings'):
            return False, 'FedWatch returned empty meetings list'
        return True, ''

    @classmethod
    def build_error_context(cls, tool_name: str, error_msg: str) -> str:
        return (
            f"\n[DATA QUALITY WARNING — {tool_name}]\n"
            f"Issue: {error_msg}\n"
            f"MANDATORY: Do NOT use this data for trading decisions this cycle.\n"
            f"If this tool was critical for your decision: submit WAIT.\n"
        )
