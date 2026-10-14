# ==============================================================================
# File: domain/ports/__init__.py
# ==============================================================================

"""
Monika Domain Ports & Interfaces.

Provides pure abstract domain protocols for persistence, Unit of Work, and
external boundaries, upholding the Dependency Inversion Principle.
"""

from monika.domain.ports.execution import BrokerPort, ExecutionPort
from monika.domain.ports.llm import LlmPort, ModelProviderPort
from monika.domain.ports.market_data import MarketDataPort
from monika.domain.ports.notifier import NotifierPort
from monika.domain.ports.repository import (
    ActivityLogRepositoryPort,
    AnalysisRepositoryPort,
    PositionRepositoryPort,
    RiskRepositoryPort,
    SystemConfigRepositoryPort,
    TradeProposalRepositoryPort,
)
from monika.domain.ports.unit_of_work import UnitOfWorkPort

__all__ = [
    "PositionRepositoryPort",
    "TradeProposalRepositoryPort",
    "ActivityLogRepositoryPort",
    "SystemConfigRepositoryPort",
    "RiskRepositoryPort",
    "AnalysisRepositoryPort",
    "UnitOfWorkPort",
    "BrokerPort",
    "ExecutionPort",
    "MarketDataPort",
    "NotifierPort",
    "LlmPort",
    "ModelProviderPort",
]
