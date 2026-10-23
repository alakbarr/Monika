"""
Monika Database Repositories.

Provides domain-focused repository abstractions separating data access from UI and service layers.
"""

from monika.infrastructure.database.repositories.activity_log_repository import ActivityLogRepository
from monika.infrastructure.database.repositories.asset_analysis_repository import SqlAlchemyAssetAnalysisRepository
from monika.infrastructure.database.repositories.market_data_repository import SqlAlchemyMarketDataRepository
from monika.infrastructure.database.repositories.paper_trade_repository import SqlAlchemyPaperTradeRepository
from monika.infrastructure.database.repositories.position_repository import PositionRepository
from monika.infrastructure.database.repositories.risk_repository import SqlAlchemyRiskRepository
from monika.infrastructure.database.repositories.system_config_repository import SystemConfigRepository
from monika.infrastructure.database.repositories.trade_proposal_repository import TradeProposalRepository
from monika.infrastructure.database.repositories.unit_of_work import SqlAlchemyUnitOfWork

__all__ = [
    "PositionRepository",
    "ActivityLogRepository",
    "SystemConfigRepository",
    "TradeProposalRepository",
    "SqlAlchemyRiskRepository",
    "SqlAlchemyAssetAnalysisRepository",
    "SqlAlchemyPaperTradeRepository",
    "SqlAlchemyMarketDataRepository",
    "SqlAlchemyUnitOfWork",
]
