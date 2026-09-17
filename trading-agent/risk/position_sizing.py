# ==============================================================================
# File: risk/position_sizing.py
# ==============================================================================

"""
Position Sizing Engine — Perhitungan lot berbasis risiko persentase (fixed-fractional).

Sesuai spesifikasi §9:
  - risk_amount = equity * (risk_percent_per_trade / 100)
  - sl_distance = abs(entry_price - stop_loss)
  - lot_size = risk_amount / (sl_distance * nilai_kontrak_per_lot)

Semua perhitungan bersifat deterministik (tanpa AI) dan disimpan di orders_log.
Menggunakan fallback tabel instrumen jika MT5 tidak aktif.
"""

import logging
import math
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any
import utils.clock as clock

logger = logging.getLogger("TradingAgent.PositionSizing")


# ---------------------------------------------------------------------------
# Metadata Instrumen (Fallback statis — Nilai MT5 live jadi prioritas)
# ---------------------------------------------------------------------------

@dataclass
class InstrumentSpec:
    """Spesifikasi instrumen trading."""
    symbol: str
    pip_size: float          # size of 1 pip (e.g. 0.0001 for EURUSD, 0.01 for XAUUSD)
    pip_value_usd: float     # USD value of 1 pip per 1 standard lot
    contract_size: float     # units per lot (100 for gold oz, 100_000 for FX)
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01
    digits: int = 5
    stops_level_pips: float = 0.0
    _source: str = "default"

    @property
    def pip_value_per_lot(self) -> float:
        """Alias: Nilai USD dari 1 pip per 1 lot."""
        return self.pip_value_usd


# Spesifikasi default saat MT5 offline
DEFAULT_INSTRUMENTS: dict[str, InstrumentSpec] = {
    "XAUUSD": InstrumentSpec(
        symbol="XAUUSD",
        pip_size=0.01,
        pip_value_usd=1.0,      # $1 per 0.01 pip per lot (100 oz × $0.01)
        contract_size=100,
        digits=2,
    ),
    "EURUSD": InstrumentSpec(
        symbol="EURUSD",
        pip_size=0.0001,
        pip_value_usd=10.0,
        contract_size=100_000,
        digits=5,
    ),
    "GBPUSD": InstrumentSpec(
        symbol="GBPUSD",
        pip_size=0.0001,
        pip_value_usd=10.0,
        contract_size=100_000,
        digits=5,
    ),
    "USDJPY": InstrumentSpec(
        symbol="USDJPY",
        pip_size=0.01,
        pip_value_usd=6.67,     # fallback only - akan di-override dynamically
        contract_size=100_000,
        digits=3,
    ),
    "AUDUSD": InstrumentSpec(
        symbol="AUDUSD",
        pip_size=0.0001,
        pip_value_usd=10.0,
        contract_size=100_000,
        digits=5,
    ),
    "XTIUSD": InstrumentSpec(
        symbol="XTIUSD",
        pip_size=0.01,
        pip_value_usd=1.0,  # Varies — $1 per 0.01 per lot typically
        contract_size=100,
        digits=2,
    ),
    "BTCUSD": InstrumentSpec(
        symbol="BTCUSD",
        pip_size=1.0,        # 1 USD = 1 pip
        pip_value_usd=1.0,   # WAS: 0.1 → FIX: $1 per pip per lot (1 BTC × $1)
        contract_size=1,
        min_lot=0.01,
        max_lot=10.0,        # cap at 10 BTC (reasonable for retail)
        lot_step=0.01,
        digits=2,
    ),
    "XBRUSD": InstrumentSpec(
        symbol="XBRUSD",
        pip_size=0.01,
        pip_value_usd=1.0,   # $1 per 0.01 per lot (100 bbl/contracts)
        contract_size=1000,
        digits=2,
    ),
    "USDCAD": InstrumentSpec(
        symbol="USDCAD",
        pip_size=0.0001,
        pip_value_usd=10.0,
        contract_size=100_000,
        digits=5,
    ),
    "USDCHF": InstrumentSpec(
        symbol="USDCHF",
        pip_size=0.0001,
        pip_value_usd=10.0,
        contract_size=100_000,
        digits=5,
    ),
    "ETHUSD": InstrumentSpec(
        symbol="ETHUSD",
        pip_size=0.1,
        pip_value_usd=1.0,
        contract_size=1,
        min_lot=0.01,
        max_lot=50.0,
        lot_step=0.01,
        digits=2,
    ),
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class SizingResult:
    """Hasil perhitungan ukuran posisi (lot)."""
    symbol: str
    direction: str                  # "buy" or "sell"
    entry_price: float
    stop_loss: float
    take_profit: Optional[float]

    # Inputs
    account_equity: float
    risk_percent: float

    # Derived
    risk_amount_usd: float          # equity × risk_pct
    sl_distance_price: float        # |entry - sl|
    sl_distance_pips: float         # distance in pips
    pip_value_per_lot: float        # USD per pip per 1.0 lot
    raw_lots: float                 # unrounded result
    recommended_lots: float         # rounded to lot_step, clamped to [min, max_lot]

    # Risk/reward
    rr_ratio: Optional[float]       # take_profit distance / stop_loss distance

    # Status
    is_valid: bool                  # False if any constraint violated
    rejection_reasons: list[str] = field(default_factory=list)

    # Metadata
    calculated_at: datetime = field(default_factory=clock.now)
    instrument_spec_source: str = "default"  # "mt5_live", "cache", or "default"

    @property
    def sl_pips(self) -> float:
        """Alias untuk sl_distance_pips demi kompatibilitas logging & risk gate."""
        return self.sl_distance_pips

    def summary(self) -> str:
        status = "OK" if self.is_valid else f"REJECTED({', '.join(self.rejection_reasons)})"
        rr = f"{self.rr_ratio:.2f}" if self.rr_ratio else "N/A"
        return (
            f"{self.symbol} {self.direction.upper()} | "
            f"Lots={self.recommended_lots} | "
            f"Risk=${self.risk_amount_usd:.2f} ({self.risk_percent}%) | "
            f"SL={self.sl_distance_pips:.1f}pips | "
            f"RR=1:{rr} | {status}"
        )


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

class PositionSizer:
    """Menghitung rekomendasi ukuran lot berdasarkan parameter risiko dan equity."""

    def __init__(self, settings: dict, mt5_client=None):
        """
        Args:
        settings:   Full settings dict (uses trading.risk section).
        mt5_client: Optional live MT5Client for live symbol info.
        Falls back to DEFAULT_INSTRUMENTS if None or disconnected.
        """
        self.settings = settings
        risk_cfg = settings.get("trading", {}).get("risk", {})
        self.risk_percent: float   = risk_cfg.get("risk_percent_per_trade", 1.0)
        self.min_rr: float         = risk_cfg.get("min_rr_ratio", 1.3)
        self._mt5 = mt5_client

    @classmethod
    def update_usdjpy_cache(cls, rate: float):
        cls._usdjpy_rate_cache = {'rate': rate, 'ts': datetime.now(timezone.utc)}

    async def _get_regime_size_multiplier(self, session, symbol: str, as_of: Optional[datetime] = None) -> float:
        try:
            from analysis.calculators.regime_classifier import classify_market_regime
            regime = await classify_market_regime(session, symbol, self.settings, as_of=as_of)
            mult = regime.get('size_multiplier', 1.0)
            if mult < 1.0:
                logger.info(f"[{symbol}] Regime-based size reduction: {mult:.2f}x "
                            f"(regime={regime['regime']}, quality={regime['composite_quality']:.2f})")
            return mult
        except Exception as e:
            logger.debug(f'Regime classification failed for sizing, defaulting to 1.0: {e}')
            return 1.0

    async def calculate_with_session(
        self,
        session,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        account_equity: Optional[float] = None,
        risk_percent_override: Optional[float] = None,
        vix_level: Optional[float] = None,
        as_of: Optional[datetime] = None,
        **kwargs,
    ) -> SizingResult:
        """Version baru dengan akses DB untuk pip value dinamis."""
        try:
            entry_price = float(entry_price)
        except (TypeError, ValueError):
            entry_price = 0.0
        try:
            stop_loss = float(stop_loss) if stop_loss is not None else 0.0
        except (TypeError, ValueError):
            stop_loss = 0.0
        if take_profit is not None:
            try:
                take_profit = float(take_profit)
            except (TypeError, ValueError):
                take_profit = None

        # Fail-closed protection for blown account:
        if account_equity is not None and account_equity <= 0:
            return self._invalid(
                symbol, direction, entry_price, stop_loss, take_profit,
                account_equity, risk_percent_override if risk_percent_override is not None else self.risk_percent,
                ["Account equity is zero or negative (blown account protection)"]
            )

        if account_equity is None:
            if self._mt5 is not None:
                try:
                    info = await self._mt5.get_account_info()
                    if info and "equity" in info:
                        live_equity = float(info.get("equity") or 0.0)
                        if live_equity <= 0:
                            return self._invalid(
                                symbol, direction, entry_price, stop_loss, take_profit,
                                live_equity, risk_percent_override if risk_percent_override is not None else self.risk_percent,
                                ["Live account equity is zero or negative (blown account protection)"]
                            )
                        account_equity = live_equity
                except Exception as e:
                    logger.debug(f"Could not retrieve live MT5 equity for sizing: {e}")
            if account_equity is None or account_equity <= 0:
                raw_bal = self.settings.get("paper_trading", {}).get("initial_balance") if isinstance(self.settings, dict) else None
                account_equity = float(raw_bal) if raw_bal is not None else 10000.0

        risk_pct = risk_percent_override if risk_percent_override is not None else self.risk_percent
        
        # Apply VIX dynamic risk adjustment using settings thresholds
        risk_cfg = getattr(self, "settings", {}).get("trading", {}).get("risk", {})
        vix_thresholds = risk_cfg.get("vix_thresholds", {})
        
        if risk_cfg.get("vix_risk_adjustment", True):
            normal    = vix_thresholds.get("normal",    15)
            caution   = vix_thresholds.get("caution",   20)
            defensive = vix_thresholds.get("defensive", 25)
            pause_thr = vix_thresholds.get("pause",     30)
            
            # If VIX is unavailable, treat as defensive
            effective_vix = vix_level if vix_level is not None else defensive
            
            if effective_vix < normal:
                pass  # normal risk
            elif normal <= effective_vix < caution:
                risk_pct *= 0.85
            elif caution <= effective_vix < defensive:
                risk_pct *= 0.70
            elif defensive <= effective_vix < pause_thr:
                risk_pct *= 0.50
            else:
                risk_pct *= 0.25

        regime_multiplier = await self._get_regime_size_multiplier(session, symbol, as_of=as_of)
        risk_pct = risk_pct * regime_multiplier
        
        if regime_multiplier < 1.0:
            logger.info(f"Regime-based size reduction for {symbol}: {regime_multiplier:.2f}x (ADX-based)")

        # TimesFM 3.0 Dispersion / Tail-Risk Sizing Adjustment
        try:
            from indicators.timesfm_engine import TimesFMEngine
            from analysis.calculators.timesfm_alpha import TimesFMAlphaCalculator
            tfm_engine = TimesFMEngine(self.settings)
            tfm_fc = await tfm_engine.get_latest_forecast(session, symbol, timeframe='H1', max_age_hours=8.0)
            if tfm_fc:
                vol_ratio = float(tfm_fc.get('volatility_expansion_ratio', 1.0))
                if vol_ratio >= 1.40:
                    risk_pct *= 0.75
                    logger.info(f"[{symbol}] TimesFM high dispersion tail-risk reduction applied: 0.75x (expansion_ratio={vol_ratio:.2f})")

                # Quantile Asymmetry directional skew sizing multiplier
                quantiles = tfm_fc.get("quantiles", {})
                if quantiles:
                    skew_alpha = TimesFMAlphaCalculator.calculate_skew_from_quantiles(
                        quantiles, current_price=entry_price
                    )
                    skew_mult = TimesFMAlphaCalculator.get_sizing_multiplier(skew_alpha, direction=direction)
                    if skew_mult != 1.0:
                        risk_pct *= skew_mult
                        logger.info(
                            f"[{symbol}] TimesFM skew multiplier applied: {skew_mult:.2f}x "
                            f"(bias={skew_alpha.get('bias')}, skew={skew_alpha.get('skew_ratio')})"
                        )
        except Exception as tfm_err:
            logger.debug(f"[{symbol}] TimesFM sizing adjustment non-fatal: {tfm_err}")

        # Paper Trading Streak Loss Mitigation: scale down risk if losing streak >= 3 and policy == 'warn_and_scale'
        try:
            paper_cfg = getattr(self, "settings", {}).get("trading", {}).get("paper_trading", {}) if isinstance(getattr(self, "settings", None), dict) else {}
            streak_policy = paper_cfg.get("streak_loss_policy", "warn_and_scale")
            if streak_policy == "warn_and_scale":
                from database.models import PaperTradeRecord
                from sqlalchemy import select
                recent = (await session.execute(
                    select(PaperTradeRecord)
                    .where(PaperTradeRecord.symbol == symbol)
                    .where(PaperTradeRecord.status == 'closed')
                    .order_by(PaperTradeRecord.closed_at.desc())
                    .limit(3)
                )).scalars().all()
                if len(recent) >= 3 and all((t.pnl_pct is not None and t.pnl_pct < 0) or t.exit_reason == 'sl_hit' for t in recent):
                    scale_mult = float(paper_cfg.get("streak_risk_scale_factor", 0.5))
                    risk_pct *= scale_mult
                    logger.info(f"[{symbol}] Streak loss risk scaling applied: {scale_mult:.2f}x (3+ consecutive losses)")
        except Exception as streak_err:
            logger.debug(f"[{symbol}] Streak loss sizing adjustment non-fatal: {streak_err}")
                
        spec = await self._get_instrument_spec_dynamic(session, symbol)
        if spec is None:
            return self._invalid(symbol, direction, entry_price, stop_loss, take_profit,
                                 account_equity, risk_pct, [f"Instrument specifications unavailable for {symbol}"])
        rejections: list[str] = []

        # 1. Basic sanity checks
        if entry_price <= 0 or stop_loss <= 0:
            return self._invalid(symbol, direction, entry_price, stop_loss, take_profit,
                                 account_equity, risk_pct, ["entry_price or stop_loss is zero/negative"])

        if direction == "buy" and stop_loss >= entry_price:
            rejections.append("For BUY: stop_loss must be below entry_price")
        elif direction == "sell" and stop_loss <= entry_price:
            rejections.append("For SELL: stop_loss must be above entry_price")

        if take_profit is not None and take_profit > 0:
            if direction == "buy" and take_profit <= entry_price:
                rejections.append("For BUY: take_profit must be above entry_price")
            elif direction == "sell" and take_profit >= entry_price:
                rejections.append("For SELL: take_profit must be below entry_price")

        if not account_equity or account_equity <= 0:
            rejections.append("account_equity must be positive")

        # 2. Calculate SL distance using Decimal fixed-point precision
        d_entry = Decimal(str(entry_price))
        d_sl = Decimal(str(stop_loss))
        d_pip_size = Decimal(str(spec.pip_size))
        d_digits = Decimal(10) ** -spec.digits

        d_sl_distance_price = abs(d_entry - d_sl).quantize(d_digits, rounding=ROUND_HALF_UP)
        sl_distance_price = float(d_sl_distance_price)
        if sl_distance_price < spec.pip_size:
            rejections.append(f"SL distance ({sl_distance_price}) is smaller than 1 pip ({spec.pip_size})")

        d_sl_distance_pips = d_sl_distance_price / d_pip_size if d_pip_size > 0 else Decimal("0")
        sl_distance_pips = float(d_sl_distance_pips)

        # Broker stops_level validation
        if spec.stops_level_pips > 0 and sl_distance_pips < spec.stops_level_pips:
            rejections.append(
                f"SL distance ({sl_distance_pips} pips) is smaller than broker minimum stops level ({spec.stops_level_pips} pips)"
            )

        # 3. Calculate raw risk amount
        d_equity = Decimal(str(account_equity))
        d_risk_pct = Decimal(str(risk_pct))
        d_risk_amount_usd = d_equity * (d_risk_pct / Decimal("100.0"))
        risk_amount_usd = float(d_risk_amount_usd)

        # 4. Calculate raw lot size
        d_pip_val = Decimal(str(spec.pip_value_per_lot))
        d_denom = d_sl_distance_pips * d_pip_val
        if d_denom == 0:
            raw_lots = 0.0
        else:
            d_raw_lots = d_risk_amount_usd / d_denom
            raw_lots = float(d_raw_lots)

        # 5. Round to lot step and clamp
        recommended_lots = self._round_lots(raw_lots, spec.lot_step)
        if recommended_lots < spec.min_lot:
            rejections.append(f"Calculated lot size ({recommended_lots}) is below broker minimum ({spec.min_lot})")
        
        max_risk_cap = float(self.settings.get("trading", {}).get("risk", {}).get("max_risk_amount_usd", 1000.0))
        actual_risk_usd = recommended_lots * sl_distance_pips * spec.pip_value_per_lot
        if actual_risk_usd > max_risk_cap:
            rejections.append(f"Actual risk (${actual_risk_usd:.2f}) exceeds configured risk limit of ${max_risk_cap:.2f}")
        recommended_lots = max(spec.min_lot, recommended_lots)
        
        # TAMBAHKAN: cap to max_lot
        if spec.max_lot > 0:
            recommended_lots = min(spec.max_lot, recommended_lots)

        # Volatility-Budget Parity Sizing (Enhancement 10)
        vol_parity_cfg = self.settings.get("trading", {}).get("risk", {}).get("volatility_parity", {})
        if vol_parity_cfg.get("enabled", False) and entry_price > 0 and sl_distance_price > 0:
            target_usd = float(d_risk_amount_usd)
            if spec.pip_size > 0 and spec.pip_value_per_lot > 0:
                value_per_unit = spec.pip_value_per_lot / spec.pip_size
                desired_lot = target_usd / (sl_distance_price * value_per_unit)
                if desired_lot < spec.min_lot:
                    rejections.append(f"Volatility-parity lot ({desired_lot:.4f}) < broker min_lot ({spec.min_lot}); skipped to prevent oversizing")
                    recommended_lots = 0.0
                else:
                    recommended_lots = self._round_lots(desired_lot, spec.lot_step)
                    if spec.max_lot > 0:
                        recommended_lots = min(spec.max_lot, recommended_lots)
            
        # TAMBAHKAN: sanity check — if lot size would create notional > 20% of equity, reduce
        if spec.contract_size > 0 and entry_price > 0:
            is_forex = len(symbol) == 6 and symbol[:3].isalpha() and symbol[3:].isalpha()
            if is_forex and symbol.startswith("USD"):
                notional = recommended_lots * spec.contract_size
            elif is_forex and not symbol.endswith("USD"):
                notional = recommended_lots * spec.contract_size * 1.5  # safe upper bound for cross pairs
            else:
                notional = recommended_lots * spec.contract_size * entry_price
                
            max_notional = account_equity * 20  # max 20x equity (leverage cap)
            if notional > max_notional:
                if is_forex and symbol.startswith("USD"):
                    capped_lots = max_notional / spec.contract_size
                elif is_forex and not symbol.endswith("USD"):
                    capped_lots = max_notional / (spec.contract_size * 1.5)
                else:
                    capped_lots = max_notional / (spec.contract_size * entry_price)
                
                capped_lots = self._round_lots(capped_lots, spec.lot_step)
                if capped_lots < spec.min_lot:
                    rejections.append(f"Notional cap reduced lot size below minimum ({spec.min_lot})")
                capped_lots = max(spec.min_lot, capped_lots)
                
                if capped_lots < recommended_lots:
                    logger.info(
                        f"[{symbol}] Lot size capped from {recommended_lots} to {capped_lots} "
                        f"(notional exposure limit: {max_notional:.0f} USD)"
                    )
                    recommended_lots = capped_lots
        


        # 6. R:R ratio check
        rr_ratio: Optional[float] = None
        if take_profit is not None:
            tp_distance = abs(take_profit - entry_price)
            rr_ratio = tp_distance / sl_distance_price if sl_distance_price > 0 else None
            if rr_ratio is not None and rr_ratio < self.min_rr:
                rejections.append(
                    f"R:R ratio {rr_ratio:.2f} is below minimum {self.min_rr:.1f}. "
                    f"Move TP or tighten SL."
                )

        is_valid = len(rejections) == 0
        if not is_valid:
            recommended_lots = 0.0

        result = SizingResult(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            account_equity=account_equity,
            risk_percent=risk_pct,
            risk_amount_usd=risk_amount_usd,
            sl_distance_price=sl_distance_price,
            sl_distance_pips=sl_distance_pips,
            pip_value_per_lot=spec.pip_value_per_lot,
            raw_lots=raw_lots,
            recommended_lots=recommended_lots,
            rr_ratio=rr_ratio,
            is_valid=is_valid,
            rejection_reasons=rejections,
            instrument_spec_source=getattr(spec, '_source', 'default'),
        )

        log_level = logging.INFO if is_valid else logging.WARNING
        logger.log(log_level, f"PositionSizing: {result.summary()}")
        return result

    def calculate(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        take_profit: Optional[float],
        account_equity: float,
        risk_percent_override: Optional[float] = None,
        vix_level: Optional[float] = None,
    ) -> SizingResult:
        """
        Menghitung lot untuk trade yang diusulkan (synchronous fallback).
        
        PERINGATAN (R-7): Method synchronous ini TIDAK menerapkan ADX regime sizing 
        multiplier (0.5x di ranging market / ADX < 20). Untuk production, selalu gunakan
        `calculate_with_session()` yang memiliki akses DB dan menerapkan semua multipliers.
        
        Gunakan `calculate()` HANYA untuk:
        - Testing / unit tests (tanpa DB)
        - Kalkulasi preview/estimasi (bukan untuk eksekusi nyata)
        
        Untuk eksekusi nyata, lihat execution_service.py yang sudah menggunakan
        `calculate_with_session()`.
        """
        import warnings
        warnings.warn(
            "PositionSizer.calculate() is a sync fallback that does NOT apply the ADX "
            "regime size multiplier (0.5x in ranging markets). "
            "Use calculate_with_session() for production execution.",
            DeprecationWarning,
            stacklevel=2
        )
        logger.warning(
            '[PositionSizer] calculate() (sync) called — ADX regime multiplier NOT applied. '
            'Use calculate_with_session() for production trading.'
        )
        risk_pct = risk_percent_override if risk_percent_override is not None else self.risk_percent
        try:
            entry_price = float(entry_price)
        except (TypeError, ValueError):
            entry_price = 0.0
        try:
            stop_loss = float(stop_loss)
        except (TypeError, ValueError):
            stop_loss = 0.0
        if take_profit is not None:
            try:
                take_profit = float(take_profit)
            except (TypeError, ValueError):
                take_profit = None
        
        # Apply VIX dynamic risk adjustment using settings thresholds
        risk_cfg = getattr(self, "settings", {}).get("trading", {}).get("risk", {})
        vix_thresholds = risk_cfg.get("vix_thresholds", {})
        
        if risk_cfg.get("vix_risk_adjustment", True) and vix_level is not None:
            normal    = vix_thresholds.get("normal",    15)
            caution   = vix_thresholds.get("caution",   20)
            defensive = vix_thresholds.get("defensive", 25)
            pause_thr = vix_thresholds.get("pause",     30)
            
            if vix_level < normal:
                pass  # normal risk
            elif normal <= vix_level < caution:
                risk_pct *= 0.85
            elif caution <= vix_level < defensive:
                risk_pct *= 0.70
            elif defensive <= vix_level < pause_thr:
                risk_pct *= 0.50
            else:
                risk_pct *= 0.25

                
        spec = self._get_instrument_spec(symbol)
        if spec is None:
            return self._invalid(symbol, direction, entry_price, stop_loss, take_profit,
                                 account_equity, risk_pct, [f"Instrument specifications unavailable for {symbol}"])
        
        # Dynamic pip value untuk JPY pairs berdasarkan last known rate
        if symbol == 'USDJPY' and self._mt5 is None:
            # Coba ambil dari cache terakhir
            try:
                import asyncio, json
                # Gunakan class variable untuk cache sederhana
                cached_rate = getattr(PositionSizer, '_usdjpy_rate_cache', None)
                if cached_rate and cached_rate.get('rate', 0) > 0:
                    import dataclasses
                    spec = dataclasses.replace(spec, 
                        pip_value_usd=round(100000 * 0.01 / cached_rate['rate'], 4))
            except Exception:
                pass  # fallback to static
                
        rejections: list[str] = []

        # 1. Basic sanity checks
        if entry_price <= 0 or stop_loss <= 0:
            return self._invalid(symbol, direction, entry_price, stop_loss, take_profit,
                                 account_equity, risk_pct, ["entry_price or stop_loss is zero/negative"])

        if direction == "buy" and stop_loss >= entry_price:
            rejections.append("For BUY: stop_loss must be below entry_price")
        elif direction == "sell" and stop_loss <= entry_price:
            rejections.append("For SELL: stop_loss must be above entry_price")

        if take_profit is not None and take_profit > 0:
            if direction == "buy" and take_profit <= entry_price:
                rejections.append("For BUY: take_profit must be above entry_price")
            elif direction == "sell" and take_profit >= entry_price:
                rejections.append("For SELL: take_profit must be below entry_price")

        if not account_equity or account_equity <= 0:
            rejections.append("account_equity must be positive")

        # 2. Calculate SL distance using Decimal fixed-point precision
        d_entry = Decimal(str(entry_price))
        d_sl = Decimal(str(stop_loss))
        d_pip_size = Decimal(str(spec.pip_size))
        d_digits = Decimal(10) ** -spec.digits

        d_sl_distance_price = abs(d_entry - d_sl).quantize(d_digits, rounding=ROUND_HALF_UP)
        sl_distance_price = float(d_sl_distance_price)
        if sl_distance_price < spec.pip_size:
            rejections.append(f"SL distance ({sl_distance_price}) is smaller than 1 pip ({spec.pip_size})")

        d_sl_distance_pips = d_sl_distance_price / d_pip_size if d_pip_size > 0 else Decimal("0")
        sl_distance_pips = float(d_sl_distance_pips.quantize(d_digits, rounding=ROUND_HALF_UP))

        # Broker stops_level validation
        if spec.stops_level_pips > 0 and sl_distance_pips < spec.stops_level_pips:
            rejections.append(
                f"SL distance ({sl_distance_pips} pips) is smaller than broker minimum stops level ({spec.stops_level_pips} pips)"
            )

        # 3. Calculate risk amount
        d_equity = Decimal(str(account_equity))
        d_risk_pct = Decimal(str(risk_pct))
        d_risk_amount_usd = d_equity * (d_risk_pct / Decimal("100.0"))
        risk_amount_usd = float(d_risk_amount_usd)

        # 4. Calculate raw lot size
        # Formula: risk_amount / (sl_pips × pip_value_per_lot)
        d_pip_val = Decimal(str(spec.pip_value_per_lot))
        d_denom = Decimal(str(sl_distance_pips)) * d_pip_val
        if spec.pip_value_per_lot <= 0 or sl_distance_pips <= 0 or d_denom <= 0:
            rejections.append("Cannot calculate lot size: pip_value or SL distance is zero")
            raw_lots = 0.0
        else:
            d_raw_lots = d_risk_amount_usd / d_denom
            raw_lots = float(d_raw_lots)

        # 5. Round to lot step and clamp
        recommended_lots = self._round_lots(raw_lots, spec.lot_step)
        if recommended_lots < spec.min_lot:
            rejections.append(f"Calculated lot size ({recommended_lots}) is below broker minimum ({spec.min_lot})")
            
        max_risk_cap = float(self.settings.get("trading", {}).get("risk", {}).get("max_risk_amount_usd", 1000.0))
        actual_risk_usd = recommended_lots * sl_distance_pips * spec.pip_value_per_lot
        if actual_risk_usd > max_risk_cap:
            rejections.append(f"Actual risk (${actual_risk_usd:.2f}) exceeds configured risk limit of ${max_risk_cap:.2f}")
        recommended_lots = max(spec.min_lot, recommended_lots)
        
        # TAMBAHKAN: cap to configured max lot and spec max lot
        max_lot_cfg = self.settings.get("trading", {}).get("risk", {}).get("max_lot_per_symbol")
        if max_lot_cfg is None:
            max_lot_cfg = self.settings.get("trading", {}).get("risk", {}).get("max_lot_size")
        if max_lot_cfg is not None:
            recommended_lots = min(float(max_lot_cfg), recommended_lots)
        if spec.max_lot > 0:
            recommended_lots = min(spec.max_lot, recommended_lots)
            
        # TAMBAHKAN: sanity check — if lot size would create notional > 20% of equity, reduce
        if spec.contract_size > 0 and entry_price > 0:
            is_forex = len(symbol) == 6 and symbol[:3].isalpha() and symbol[3:].isalpha()
            if is_forex and symbol.startswith("USD"):
                notional = recommended_lots * spec.contract_size
            elif is_forex and not symbol.endswith("USD"):
                notional = recommended_lots * spec.contract_size * 1.5  # safe upper bound for cross pairs
            else:
                notional = recommended_lots * spec.contract_size * entry_price
                
            max_notional = account_equity * 20  # max 20x equity (leverage cap)
            if notional > max_notional:
                if is_forex and symbol.startswith("USD"):
                    capped_lots = max_notional / spec.contract_size
                elif is_forex and not symbol.endswith("USD"):
                    capped_lots = max_notional / (spec.contract_size * 1.5)
                else:
                    capped_lots = max_notional / (spec.contract_size * entry_price)
                
                capped_lots = self._round_lots(capped_lots, spec.lot_step)
                if capped_lots < spec.min_lot:
                    rejections.append(f"Notional cap reduced lot size below minimum ({spec.min_lot})")
                capped_lots = max(spec.min_lot, capped_lots)
                
                if capped_lots < recommended_lots:
                    logger.info(
                        f"[{symbol}] Lot size capped from {recommended_lots} to {capped_lots} "
                        f"(notional exposure limit: {max_notional:.0f} USD)"
                    )
                    recommended_lots = capped_lots
        


        # 6. R:R ratio check
        rr_ratio: Optional[float] = None
        if take_profit is not None:
            tp_distance = abs(take_profit - entry_price)
            rr_ratio = tp_distance / sl_distance_price if sl_distance_price > 0 else None
            if rr_ratio is not None and rr_ratio < self.min_rr:
                rejections.append(
                    f"R:R ratio {rr_ratio:.2f} is below minimum {self.min_rr:.1f}. "
                    f"Move TP or tighten SL."
                )

        is_valid = len(rejections) == 0
        if not is_valid:
            recommended_lots = 0.0

        result = SizingResult(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            account_equity=account_equity,
            risk_percent=risk_pct,
            risk_amount_usd=risk_amount_usd,
            sl_distance_price=sl_distance_price,
            sl_distance_pips=sl_distance_pips,
            pip_value_per_lot=spec.pip_value_per_lot,
            raw_lots=raw_lots,
            recommended_lots=recommended_lots,
            rr_ratio=rr_ratio,
            is_valid=is_valid,
            rejection_reasons=rejections,
            instrument_spec_source=getattr(spec, '_source', 'default'),
        )

        log_level = logging.INFO if is_valid else logging.WARNING
        logger.log(log_level, f"PositionSizing: {result.summary()}")
        return result

    # ------------------------------------------------------------------
    # Instrument spec resolution
    # ------------------------------------------------------------------

    async def _get_instrument_spec_dynamic(
        self, session, symbol: str, as_of: Optional[datetime] = None
    ) -> Optional[InstrumentSpec]:
        """Dapatkan spec dengan pip value USDJPY dihitung dari harga terkini."""
        # Try MT5 live data
        if self._mt5 is not None:
            try:
                info = await self._mt5.get_symbol_info(symbol)
                if info is not None:
                    digits = info.get('digits', 5)
                    point = info.get('point', 0.00001)
                    point_multiplier = 10 if digits in (5, 3) else 1
                    pip_size = point * point_multiplier
                    
                    stops_pts = info.get('stops_level', 0)
                    stops_pips = (stops_pts * point) / pip_size if stops_pts > 0 and pip_size > 0 else 0.0
                    
                    tick_value = info.get('tick_value', 1.0)
                    tick_size = info.get('tick_size', 0.00001) or 0.00001
                    pip_value_usd = tick_value * (1 / tick_size) * pip_size
                    
                    spec = InstrumentSpec(
                        symbol=symbol,
                        pip_size=pip_size,
                        pip_value_usd=pip_value_usd,
                        contract_size=info.get('contract_size') or info.get('trade_contract_size', 100000),
                        min_lot=info.get('volume_min', 0.01),
                        max_lot=info.get('volume_max', 100.0),
                        lot_step=info.get('volume_step', 0.01),
                        digits=digits,
                        stops_level_pips=stops_pips,
                    )
                    spec._source = "mt5_live"
                    return spec
            except Exception as e:
                logger.debug(f"MT5 symbol info unavailable for {symbol}: {e}")

        # Fallback
        if symbol in DEFAULT_INSTRUMENTS:
            import dataclasses
            spec = dataclasses.replace(DEFAULT_INSTRUMENTS[symbol])
            
            # Update USDJPY pip value berdasarkan harga terkini dari DB
            if symbol == "USDJPY":
                from database.models import PriceOHLCV
                from sqlalchemy import select
                sim_time = as_of or clock.now()
                stmt = (
                    select(PriceOHLCV)
                    .where(PriceOHLCV.symbol == "USDJPY")
                    .where(PriceOHLCV.timeframe == 'H4')
                )
                if sim_time is not None:
                    stmt = stmt.where(PriceOHLCV.timestamp <= sim_time)
                last_bar = (await session.execute(
                    stmt.order_by(PriceOHLCV.timestamp.desc()).limit(1)
                )).scalar_one_or_none()
                
                if last_bar and last_bar.close > 0:
                    dynamic_pip_value = (100_000 * 0.01) / last_bar.close
                    spec = dataclasses.replace(spec, pip_value_usd=round(dynamic_pip_value, 4))
            
            spec._source = "default"
            return spec

        # Unknown symbol
        logger.error(f"Unknown symbol {symbol} — no MT5 or default instrument specification available.")
        return None

    def _get_instrument_spec(self, symbol: str) -> Optional[InstrumentSpec]:
        """Dapatkan spesifikasi instrumen dari MT5 (live) atau gunakan default fallback."""
        # Try MT5 live data (sync call is OK here — sizing is called from sync context)
        if self._mt5 is not None:
            try:
                import MetaTrader5 as mt5
                mt5_symbol_info: Any = getattr(mt5, "symbol_info", None)
                info: Any = mt5_symbol_info(symbol) if callable(mt5_symbol_info) else None
                if info is not None:
                    digits = int(getattr(info, "digits", 5))
                    point = float(getattr(info, "point", 0.00001))
                    point_multiplier = 10 if digits in (5, 3) else 1
                    pip_size = point * point_multiplier
                    
                    # stops_level is usually in points
                    stops_pts = float(getattr(info, 'trade_stops_level', 0) or 0)
                    stops_pips = (stops_pts * point) / pip_size if stops_pts > 0 and pip_size > 0 else 0.0
                    
                    tick_size = float(getattr(info, 'trade_tick_size', 0.00001) or 0.00001)
                    tick_value = float(getattr(info, 'trade_tick_value', 1.0) or 1.0)
                    contract_size = float(getattr(info, 'trade_contract_size', 100_000) or 100_000)
                    min_lot = float(getattr(info, 'volume_min', 0.01) or 0.01)
                    max_lot = float(getattr(info, 'volume_max', 100.0) or 100.0)
                    lot_step = float(getattr(info, 'volume_step', 0.01) or 0.01)
                    
                    spec = InstrumentSpec(
                        symbol=symbol,
                        pip_size=pip_size,
                        pip_value_usd=tick_value * (1.0 / tick_size) * pip_size,
                        contract_size=contract_size,
                        min_lot=min_lot,
                        max_lot=max_lot,
                        lot_step=lot_step,
                        digits=digits,
                        stops_level_pips=stops_pips,
                        _source="mt5_live",
                    )
                    return spec
            except Exception as e:
                logger.debug(f"MT5 symbol info unavailable for {symbol}: {e}")

        # Fallback
        if symbol in DEFAULT_INSTRUMENTS:
            spec = DEFAULT_INSTRUMENTS[symbol]
            spec._source = "default"
            return spec

        # Unknown symbol — reject sizing safely
        logger.error(f"Unknown symbol {symbol} — no MT5 or default instrument specification available.")
        return None

    @staticmethod
    def _round_lots(raw: float, step: float) -> float:
        """Bulatkan ke bawah ke step lot terdekat (demi keamanan), dinamis desimal dengan Decimal fixed-point precision."""
        if raw is None or step is None or math.isnan(raw) or math.isinf(raw) or math.isnan(step) or math.isinf(step) or step <= 0 or raw <= 0:
            return 0.0
        
        # Determine number of decimals from step
        decimals = 2
        if step < 0.01:
            decimals = 3
        elif step >= 1.0:
            decimals = 0
            
        d_raw = Decimal(str(round(raw, 8)))
        d_step = Decimal(str(step))
        steps = (d_raw / d_step).quantize(Decimal("1"), rounding=ROUND_FLOOR)
        rounded = (steps * d_step).quantize(Decimal(10) ** -decimals)
        return float(rounded)

    @staticmethod
    def _invalid(
        symbol, direction, entry, sl, tp,
        equity, risk_pct, reasons
    ) -> "SizingResult":
        """Pintasan untuk langsung mengembalikan hasil invalid."""
        return SizingResult(
            symbol=symbol, direction=direction,
            entry_price=entry, stop_loss=sl, take_profit=tp,
            account_equity=equity, risk_percent=risk_pct,
            risk_amount_usd=0, sl_distance_price=0,
            sl_distance_pips=0, pip_value_per_lot=0,
            raw_lots=0, recommended_lots=0,
            rr_ratio=None, is_valid=False,
            rejection_reasons=reasons,
        )


async def calculate_lot_size(
    symbol: str,
    entry_price: float,
    stop_loss: float,
    risk_pct: float = 1.0,
    direction: Optional[str] = None,
    session: Optional[Any] = None,
    settings: Optional[dict] = None,
    mt5_client: Optional[Any] = None,
    account_equity: Optional[float] = None,
    **kwargs
) -> dict:
    """Helper fungsi publik untuk perhitungan lot size deterministik."""
    if direction is None:
        direction = "buy" if stop_loss < entry_price else "sell"

    if mt5_client is None and settings:
        try:
            from execution.mt5_client import get_mt5_client
            mt5_client = get_mt5_client(settings)
        except Exception:
            mt5_client = None

    equity = account_equity
    if equity is None or equity <= 0:
        if mt5_client is not None:
            try:
                info = await mt5_client.get_account_info()
                if info and info.get("equity", 0) > 0:
                    equity = float(info["equity"])
            except Exception as e:
                logger.debug(f"Could not retrieve MT5 equity for calculate_lot_size: {e}")

    if equity is None or equity <= 0:
        raw_bal = (settings or {}).get("paper_trading", {}).get("initial_balance") if isinstance(settings, dict) else None
        equity = float(raw_bal) if raw_bal is not None else 10000.0

    sizer = PositionSizer(settings=settings or {}, mt5_client=mt5_client)
    res = await sizer.calculate_with_session(
        session=session,
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        account_equity=equity,
        risk_percent_override=risk_pct,
        **kwargs
    )
    return {
        "symbol": res.symbol,
        "direction": res.direction,
        "recommended_lots": res.recommended_lots,
        "raw_lots": res.raw_lots,
        "risk_amount_usd": res.risk_amount_usd,
        "risk_percent": res.risk_percent,
        "sl_pips": res.sl_distance_pips,
        "pip_value": res.pip_value_per_lot,
        "is_valid": res.is_valid,
        "rejection_reasons": res.rejection_reasons,
        "summary": res.summary()
    }


def get_instrument_spec(symbol: str, mt5_client=None) -> InstrumentSpec:
    """
    Dapatkan spesifikasi instrumen trading (pip_size, pip_value_usd, contract_size, digits).
    Mendukung Forex, Gold/Logam (XAUUSD), Crypto (BTCUSD, ETHUSD), Energi (XTIUSD, XBRUSD), dan Indices.
    Menggunakan live MT5 jika tersedia, atau fallback tabel statis DEFAULT_INSTRUMENTS.
    """
    clean_sym = (symbol or "").upper().replace("/", "")
    if mt5_client is not None:
        try:
            sizer = PositionSizer(settings={}, mt5_client=mt5_client)
            spec = sizer._get_instrument_spec(clean_sym)
            if spec:
                return spec
        except Exception:
            pass

    import dataclasses
    if clean_sym in DEFAULT_INSTRUMENTS:
        return dataclasses.replace(DEFAULT_INSTRUMENTS[clean_sym])

    # Heuristik cerdas untuk instrumen dinamis di luar default map
    if "JPY" in clean_sym:
        return InstrumentSpec(symbol=clean_sym, pip_size=0.01, pip_value_usd=1000.0 / 150.0, contract_size=100_000, digits=3)
    elif "XAU" in clean_sym or "GOLD" in clean_sym:
        return InstrumentSpec(symbol=clean_sym, pip_size=0.01, pip_value_usd=1.0, contract_size=100, digits=2)
    elif "XAG" in clean_sym or "SILVER" in clean_sym:
        return InstrumentSpec(symbol=clean_sym, pip_size=0.001, pip_value_usd=5.0, contract_size=5000, digits=3)
    elif "BTC" in clean_sym or "ETH" in clean_sym or "CRYPTO" in clean_sym or "SOL" in clean_sym:
        return InstrumentSpec(symbol=clean_sym, pip_size=1.0, pip_value_usd=1.0, contract_size=1, min_lot=0.01, max_lot=10.0, digits=2)
    elif "OIL" in clean_sym or "XTI" in clean_sym or "XBR" in clean_sym or "CL" in clean_sym:
        return InstrumentSpec(symbol=clean_sym, pip_size=0.01, pip_value_usd=1.0, contract_size=100, digits=2)
    elif "US30" in clean_sym or "SPX" in clean_sym or "NAS" in clean_sym or "USTEC" in clean_sym:
        return InstrumentSpec(symbol=clean_sym, pip_size=1.0, pip_value_usd=1.0, contract_size=1, digits=2)
    elif len(clean_sym) == 6 and clean_sym.isalpha():
        return InstrumentSpec(symbol=clean_sym, pip_size=0.0001, pip_value_usd=10.0, contract_size=100_000, digits=5)

    return InstrumentSpec(symbol=clean_sym, pip_size=0.0001, pip_value_usd=10.0, contract_size=100_000, digits=5)


