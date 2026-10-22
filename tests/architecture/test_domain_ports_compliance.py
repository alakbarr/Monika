"""
Architecture tests validating domain port protocols and concrete adapter compliance (DIP).
Verifies that concrete adapters in infrastructure fulfill their canonical domain protocols,
and that domain port modules remain strictly pure with zero external dependencies.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from monika.domain.ports import (
    ActivityLogRepositoryPort,
    BrokerPort,
    EventPublisherPort,
    ExecutionPort,
    LlmPort,
    MarketDataPort,
    ModelProviderPort,
    NotifierPort,
    PositionRepositoryPort,
    SystemConfigRepositoryPort,
    TradeProposalRepositoryPort,
    UnitOfWorkPort,
)
from monika.infrastructure.brokers.broker_adapter import (
    BrokerAdapter,
    MT5LiveAdapter,
    SimulatedBrokerAdapter,
)
from monika.infrastructure.database.repositories import (
    ActivityLogRepository,
    PositionRepository,
    SqlAlchemyUnitOfWork,
    SystemConfigRepository,
    TradeProposalRepository,
)
from monika.infrastructure.database.event_store import TradingEventStore
from monika.infrastructure.notifications.telegram_notifier import AgentNotifier
from monika.infrastructure.providers.base_provider import BaseLLMClient


def test_broker_ports_compliance():
    """Verify broker adapters satisfy BrokerPort and ExecutionPort protocols."""
    assert issubclass(BrokerAdapter, BrokerPort)
    assert issubclass(BrokerAdapter, ExecutionPort)
    assert issubclass(SimulatedBrokerAdapter, BrokerPort)
    assert issubclass(MT5LiveAdapter, BrokerPort)

    sim = SimulatedBrokerAdapter()
    assert isinstance(sim, BrokerPort)
    assert isinstance(sim, ExecutionPort)


def test_market_data_port_compliance():
    """Verify broker adapters satisfy MarketDataPort protocol."""
    assert issubclass(BrokerAdapter, MarketDataPort)
    assert issubclass(SimulatedBrokerAdapter, MarketDataPort)
    assert issubclass(MT5LiveAdapter, MarketDataPort)

    sim = SimulatedBrokerAdapter()
    assert isinstance(sim, MarketDataPort)


def test_notifier_port_compliance():
    """Verify AgentNotifier satisfies NotifierPort protocol."""
    assert issubclass(AgentNotifier, NotifierPort)

    notifier = AgentNotifier()
    assert isinstance(notifier, NotifierPort)


def test_event_publisher_port_compliance():
    """Verify TradingEventStore satisfies EventPublisherPort protocol."""
    assert issubclass(TradingEventStore, EventPublisherPort)


def test_llm_port_compliance():
    """Verify BaseLLMClient satisfies LlmPort and ModelProviderPort protocols."""
    assert issubclass(BaseLLMClient, LlmPort)
    assert issubclass(BaseLLMClient, ModelProviderPort)


def test_persistence_ports_compliance():
    """Verify persistence repositories and unit of work satisfy domain protocols."""
    from unittest.mock import MagicMock

    uow = SqlAlchemyUnitOfWork(MagicMock())
    assert isinstance(uow, UnitOfWorkPort)

    assert issubclass(PositionRepository, PositionRepositoryPort)
    assert issubclass(TradeProposalRepository, TradeProposalRepositoryPort)
    assert issubclass(ActivityLogRepository, ActivityLogRepositoryPort)
    assert issubclass(SystemConfigRepository, SystemConfigRepositoryPort)


def test_domain_ports_purity():
    """Verify that domain/ports modules do not import forbidden outer layers or frameworks."""
    ports_dir = Path("src/monika/domain/ports")
    assert ports_dir.exists() and ports_dir.is_dir()

    forbidden_roots = {
        "monika.application",
        "monika.infrastructure",
        "monika.interfaces",
        "sqlalchemy",
        "fastapi",
        "telegram",
        "MetaTrader5",
        "aiohttp",
        "requests",
    }

    for py_file in ports_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            imported_names: list[str] = []
            if isinstance(node, ast.Import):
                imported_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_names.append(node.module)

            for mod_name in imported_names:
                for forbidden in forbidden_roots:
                    assert not (mod_name == forbidden or mod_name.startswith(f"{forbidden}.")), (
                        f"Port module {py_file.name} violates domain purity by importing '{mod_name}'"
                    )
