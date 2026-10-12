"""Shim module: monika.application.agent.monitors.db_health."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.monitors.db_health")
_sys.modules[__name__] = _canonical
