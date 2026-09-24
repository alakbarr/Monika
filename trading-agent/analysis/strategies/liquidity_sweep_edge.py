from analysis.strategies.base_strategy import EdgeStrategy, EdgeSignal
from analysis.strategies.registry import StrategyRegistry
from analysis.calculators.liquidity_sweep_detector import detect_liquidity_sweep

@StrategyRegistry.register
class LiquiditySweepStructuralShift(EdgeStrategy):
    strategy_id = "liquidity_sweep"
    applicable_symbols = {'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD'}
    compatible_regimes = {'RANGE', 'VOLATILE_CHOP', 'WEAK_TREND', 'TREND'}
    factor_family = 'breakout'

    async def evaluate(self, session, symbol, settings) -> EdgeSignal:
        r = await detect_liquidity_sweep(session, symbol, settings)
        if not r.get('structure_confirmed'):
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale=str(r.get('reasons')))
        conf = 0.75 if r.get('volume_confirmed') else 0.45
        require_vol = self.cfg.get('require_volume_confirmation', False)
        if require_vol and not r.get('volume_confirmed'):
            return EdgeSignal(self.strategy_id, symbol, None, False, 0.0, rationale="volume not confirmed, hard-gated")
        direction = 'buy' if r['valid_for_direction'] == 'buy' else 'sell'
        stop_loss = None
        sweep_price = r.get('sweep_price')
        if sweep_price is not None:
            try:
                from analysis.calculators.intraday_level_optimizer import _get_atr
                atr = await _get_atr(session, symbol)
                buf = (atr * 0.10) if atr and atr > 0 else (abs(sweep_price) * 0.0005)
                if direction == 'buy':
                    stop_loss = round(sweep_price - buf, 5)
                else:
                    stop_loss = round(sweep_price + buf, 5)
            except Exception:
                stop_loss = None

        return EdgeSignal(self.strategy_id, symbol, direction, True, confidence=conf,
                           stop_loss=stop_loss,
                           ttl_minutes=45, factor_family='breakout',
                           rationale='; '.join(r['reasons']), tags=["liquidity_sweep", "reversal", "breakout"], meta=r)
