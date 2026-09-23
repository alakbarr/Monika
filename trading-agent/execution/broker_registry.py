# ==============================================================================
# File: execution/broker_registry.py
# ==============================================================================

"""
Broker Adapter & Plugin Registry.
Provides centralized registration, lifecycle management, and active broker resolution
for live MT5, simulation, remote gateways, and custom BrokerPlugin implementations.
"""

import logging
from typing import Dict, Any, Optional, List, Type, Union

logger = logging.getLogger("TradingAgent.BrokerRegistry")


class BrokerAdapterRegistry:
    """
    Central registry for broker execution adapters and pluggable broker implementations.
    """
    _adapters: Dict[str, Any] = {}
    _adapter_factories: Dict[str, Any] = {}
    _active_name: str = "mt5_live"

    @classmethod
    def register(cls, name: str, adapter_or_factory: Any) -> None:
        """Register a broker adapter instance or factory callable."""
        key = name.lower().strip()
        if callable(adapter_or_factory) and not hasattr(adapter_or_factory, "submit_order"):
            cls._adapter_factories[key] = adapter_or_factory
        else:
            cls._adapters[key] = adapter_or_factory
        logger.info(f"[BrokerAdapterRegistry] Registered adapter: {key}")

    @classmethod
    def get(cls, name: str, **kwargs) -> Optional[Any]:
        """Resolve a registered broker adapter, instantiating via factory if necessary."""
        key = name.lower().strip()
        if key in cls._adapters:
            return cls._adapters[key]
        if key in cls._adapter_factories:
            factory = cls._adapter_factories[key]
            instance = factory(**kwargs) if kwargs else factory()
            cls._adapters[key] = instance
            return instance
        return None

    @classmethod
    def set_active(cls, name: str) -> None:
        """Set the active broker adapter key."""
        key = name.lower().strip()
        cls._active_name = key
        logger.info(f"[BrokerAdapterRegistry] Active broker adapter set to: {key}")

    @classmethod
    def get_active(cls, **kwargs) -> Optional[Any]:
        """Retrieve the currently active broker adapter."""
        adapter = cls.get(cls._active_name, **kwargs)
        if adapter is None:
            # Fallback to simulated if active is not found
            logger.warning(
                f"[BrokerAdapterRegistry] Active broker '{cls._active_name}' not resolved; falling back to simulated"
            )
            return cls.get("simulated", **kwargs)
        return adapter

    @classmethod
    def list_registered(cls) -> List[str]:
        """List all registered adapter identifiers."""
        keys = set(cls._adapters.keys()) | set(cls._adapter_factories.keys())
        return sorted(list(keys))

    @classmethod
    def reset(cls) -> None:
        """Reset internal registries (primarily for testing)."""
        cls._adapters.clear()
        cls._adapter_factories.clear()
        cls._active_name = "mt5_live"


# Register standard built-in factories lazily
def _register_builtins():
    def _create_mt5(**kwargs):
        from execution.broker_adapter import MT5LiveAdapter
        return MT5LiveAdapter(**kwargs)

    def _create_simulated(**kwargs):
        from execution.broker_adapter import SimulatedBrokerAdapter
        return SimulatedBrokerAdapter(**kwargs)

    def _create_remote(**kwargs):
        from execution.broker_adapter import MT5RemoteGatewayAdapter
        return MT5RemoteGatewayAdapter(**kwargs)

    BrokerAdapterRegistry.register("mt5_live", _create_mt5)
    BrokerAdapterRegistry.register("mt5", _create_mt5)
    BrokerAdapterRegistry.register("simulated", _create_simulated)
    BrokerAdapterRegistry.register("paper", _create_simulated)
    BrokerAdapterRegistry.register("remote_gateway", _create_remote)

_register_builtins()
