# ==============================================================================
# File: domain/ports/__init__.py
# ==============================================================================

"""
Monika Domain Ports & Interfaces.

Provides pure abstract domain protocols for persistence, Unit of Work, and
external boundaries, upholding the Dependency Inversion Principle.
"""

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
]
