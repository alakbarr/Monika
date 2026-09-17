import logging

logger = logging.getLogger("TradingAgent.StrategiesInit")

try:
    import analysis.strategies.gap_fade
except Exception as e:
    logger.debug(f"gap_fade not loaded: {e}")

try:
    import analysis.strategies.tsm_momentum
except Exception as e:
    logger.debug(f"tsm_momentum not loaded: {e}")

try:
    import analysis.strategies.liquidity_sweep_edge
except Exception as e:
    logger.debug(f"liquidity_sweep_edge not loaded: {e}")

try:
    import analysis.strategies.xau_trend_engine
except Exception as e:
    logger.debug(f"xau_trend_engine not loaded: {e}")

try:
    import analysis.strategies.btc_donchian_breakout
except Exception as e:
    logger.debug(f"btc_donchian_breakout not loaded: {e}")

try:
    import analysis.strategies.xti_pairs_readiness
except Exception as e:
    logger.debug(f"xti_pairs_readiness not loaded: {e}")

try:
    from analysis.strategies.registry import StrategyRegistry
    StrategyRegistry.log_summary()
except Exception as e:
    logger.debug(f"StrategyRegistry summary not logged: {e}")

