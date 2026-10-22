# ==============================================================================
# File: database/models.py
# ==============================================================================

"""
Model Database untuk AI Trading Agent.
Semua tabel dari spesifikasi dan ekstensi institusional.
Menggunakan SQLAlchemy 2.0 DeclarativeBase dengan pola async.
Backward-compatible facade delegating to `monika.infrastructure.database.domain_models`.
"""

import sys
import types
from typing import Any

from monika.domain.entities.order_status import (
    VALID_ORDER_TRANSITIONS,
    InvalidOrderStateTransitionError,
    OrderStatus,
)
from monika.infrastructure.database.domain_models import (
    ActivityLog,
    AgentSession,
    AgentSessionMessage,
    AssetAnalysis,
    BacktestRun,
    BacktestTrade,
    Base,
    BondYieldData,
    CandidateLesson,
    CentralBankDocument,
    CentralBankRateExpectation,
    ConfluenceFactorOutcome,
    ContextSpillBlob,
    COTReport,
    CronJob,
    CycleEvent,
    CyclePerformance,
    DebateTranscript,
    DecisionMemory,
    DecisionReflection,
    DeliveryRecord,
    DXYData,
    EconomicCalendar,
    EconomicReportDecomposition,
    EquityDrawdownSnapshot,
    FedWatchProbability,
    FundamentalBrief,
    FVGZone,
    InterestRate,
    JobDelivery,
    LiquidityZone,
    MacroLiquidityCreditMetric,
    MarketChronicle,
    MT5Signal,
    NewsClassificationOutcome,
    NewsDigest,
    NewsDigestSlice,
    NewsItem,
    Order,
    OrderBlock,
    OrderEvent,
    OrderLog,
    OutboxDelivery,
    PaperTradeRecord,
    PatternScreeningCache,
    PlaybookRuleAttribution,
    Position,
    PrescreenLog,
    PriceOHLCV,
    PriceOHLCVRejected,
    RepairLedger,
    RiskState,
    ScheduledJob,
    SessionToolRecord,
    SRZone,
    StructureBreak,
    SwingPoint,
    SystemConfig,
    SystemPrompt,
    TechnicalIndicator,
    TelegramConversation,
    TelegramTopicBinding,
    TimesFMForecast,
    TokenUsageLog,
    Trade,
    TradeOutcome,
    TradePlan,
    TradePlanLeg,
    TradeTrigger,
    TradingEvent,
    TradingStateLog,
    TreasuryYield,
    TSVECTOR,
    TSVECTOR_TYPE,
    UserJournalEntry,
    UserMarketIntel,
    UserPreference,
    VIXData,
    _utcnow,
)
import monika.infrastructure.database.domain_models as _dm_pkg
import monika.infrastructure.database.domain_models.analysis as _analysis_mod
import monika.infrastructure.database.domain_models.base as _base_mod
import monika.infrastructure.database.domain_models.market as _market_mod
import monika.infrastructure.database.domain_models.memory as _memory_mod
import monika.infrastructure.database.domain_models.news as _news_mod
import monika.infrastructure.database.domain_models.system as _system_mod
import monika.infrastructure.database.domain_models.trading as _trading_mod

__all__ = [
    # Base
    "Base",
    "_utcnow",
    "TSVECTOR",
    "TSVECTOR_TYPE",
    # News
    "NewsItem",
    "NewsDigest",
    "NewsDigestSlice",
    "EconomicCalendar",
    "NewsClassificationOutcome",
    # Market
    "TreasuryYield",
    "InterestRate",
    "FedWatchProbability",
    "CentralBankRateExpectation",
    "COTReport",
    "VIXData",
    "DXYData",
    "BondYieldData",
    "EconomicReportDecomposition",
    "CentralBankDocument",
    "MacroLiquidityCreditMetric",
    "PriceOHLCV",
    "PriceOHLCVRejected",
    "TechnicalIndicator",
    "SwingPoint",
    "SRZone",
    "LiquidityZone",
    "FVGZone",
    "OrderBlock",
    "StructureBreak",
    "PatternScreeningCache",
    # Analysis
    "FundamentalBrief",
    "AssetAnalysis",
    "PrescreenLog",
    "CyclePerformance",
    "ConfluenceFactorOutcome",
    "PlaybookRuleAttribution",
    "TimesFMForecast",
    "DebateTranscript",
    # Trading
    "Trade",
    "TradeTrigger",
    "MT5Signal",
    "Order",
    "OrderEvent",
    "Position",
    "TradeOutcome",
    "PaperTradeRecord",
    "EquityDrawdownSnapshot",
    "TradePlan",
    "TradePlanLeg",
    "OrderLog",
    "TradingStateLog",
    "BacktestRun",
    "BacktestTrade",
    "OrderStatus",
    "VALID_ORDER_TRANSITIONS",
    "InvalidOrderStateTransitionError",
    # Memory
    "MarketChronicle",
    "DecisionReflection",
    "DecisionMemory",
    "CandidateLesson",
    "ContextSpillBlob",
    "UserMarketIntel",
    "CycleEvent",
    # System
    "RiskState",
    "TelegramConversation",
    "TelegramTopicBinding",
    "ActivityLog",
    "TradingEvent",
    "TokenUsageLog",
    "SystemConfig",
    "SystemPrompt",
    "AgentSession",
    "AgentSessionMessage",
    "UserPreference",
    "UserJournalEntry",
    "CronJob",
    "OutboxDelivery",
    "DeliveryRecord",
    "SessionToolRecord",
    "RepairLedger",
    "ScheduledJob",
    "JobDelivery",
]


class _ModelsFacadeModule(types.ModuleType):
    """Module proxy forwarding attribute mutations to submodules for transparent monkeypatching."""

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        for submodule in (
            _dm_pkg,
            _base_mod,
            _market_mod,
            _trading_mod,
            _analysis_mod,
            _news_mod,
            _memory_mod,
            _system_mod,
        ):
            if hasattr(submodule, name):
                setattr(submodule, name, value)


_current_mod = sys.modules[__name__]
_proxy_mod = _ModelsFacadeModule(__name__, __doc__)
_proxy_mod.__dict__.update(_current_mod.__dict__)
sys.modules[__name__] = _proxy_mod

try:
    from monika.domain.models_resolver import register_model, register_model_provider

    register_model_provider(lambda name: globals().get(name))
    for _name in __all__:
        if _name in globals():
            register_model(_name, globals()[_name])
except Exception:
    pass
