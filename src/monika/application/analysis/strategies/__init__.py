import logging

logger = logging.getLogger("TradingAgent.StrategiesInit")

try:
    import monika.application.analysis.strategies.gap_fade
except Exception as e:
    logger.debug(f"gap_fade not loaded: {e}")

try:
    import monika.application.analysis.strategies.tsm_momentum
except Exception as e:
    logger.debug(f"tsm_momentum not loaded: {e}")

try:
    import monika.application.analysis.strategies.liquidity_sweep_edge
except Exception as e:
    logger.debug(f"liquidity_sweep_edge not loaded: {e}")

try:
    import monika.application.analysis.strategies.xau_trend_engine
except Exception as e:
    logger.debug(f"xau_trend_engine not loaded: {e}")

try:
    import monika.application.analysis.strategies.btc_donchian_breakout
except Exception as e:
    logger.debug(f"btc_donchian_breakout not loaded: {e}")

try:
    import monika.application.analysis.strategies.xti_pairs_readiness
except Exception as e:
    logger.debug(f"xti_pairs_readiness not loaded: {e}")

try:
    import monika.application.analysis.strategies.tri_convergent_alpha
except Exception as e:
    logger.debug(f"tri_convergent_alpha not loaded: {e}")

try:
    import monika.application.analysis.strategies.smc_fvg
except Exception as e:
    logger.debug(f"smc_fvg not loaded: {e}")

try:
    import monika.application.analysis.strategies.bb_volume_profile
except Exception as e:
    logger.debug(f"bb_volume_profile not loaded: {e}")

try:
    import monika.application.analysis.strategies.asian_range_fade
except Exception as e:
    logger.debug(f"asian_range_fade not loaded: {e}")

try:
    import monika.application.analysis.strategies.smt_divergence
except Exception as e:
    logger.debug(f"smt_divergence not loaded: {e}")

try:
    import monika.application.analysis.strategies.tokyo_sweep
except Exception as e:
    logger.debug(f"tokyo_sweep not loaded: {e}")

try:
    import monika.application.analysis.strategies.vwap_reversion
except Exception as e:
    logger.debug(f"vwap_reversion not loaded: {e}")

try:
    import monika.application.analysis.strategies.bollinger_reversion
except Exception as e:
    logger.debug(f"bollinger_reversion not loaded: {e}")

try:
    import monika.application.analysis.strategies.usdjpy_atr_exhaustion
except Exception as e:
    logger.debug(f"usdjpy_atr_exhaustion not loaded: {e}")

try:
    import monika.application.analysis.strategies.xtiusd_atr_exhaustion
except Exception as e:
    logger.debug(f"xtiusd_atr_exhaustion not loaded: {e}")

try:
    import monika.application.analysis.strategies.xauusd_atr_exhaustion
except Exception as e:
    logger.debug(f"xauusd_atr_exhaustion not loaded: {e}")

try:
    import monika.application.analysis.strategies.btcusd_dynamic_donchian
except Exception as e:
    logger.debug(f"btcusd_dynamic_donchian not loaded: {e}")

try:
    import monika.application.analysis.strategies.gbpusd_trend_breakout
except Exception as e:
    logger.debug(f"gbpusd_trend_breakout not loaded: {e}")

try:
    import monika.application.analysis.strategies.london_trend_breakout
except Exception as e:
    logger.debug(f"london_trend_breakout not loaded: {e}")

try:
    import monika.application.analysis.strategies.london_gold_breakout
except Exception as e:
    logger.debug(f"london_gold_breakout not loaded: {e}")

try:
    import monika.application.analysis.strategies.crude_london_breakout
except Exception as e:
    logger.debug(f"crude_london_breakout not loaded: {e}")

try:
    import monika.application.analysis.strategies.btc_us_momentum
except Exception as e:
    logger.debug(f"btc_us_momentum not loaded: {e}")

try:
    import monika.application.analysis.strategies.tokyo_range_fade
except Exception as e:
    logger.debug(f"tokyo_range_fade not loaded: {e}")

try:
    from monika.application.analysis.strategies.registry import StrategyRegistry

    StrategyRegistry.log_summary()
except Exception as e:
    logger.debug(f"StrategyRegistry summary not logged: {e}")
