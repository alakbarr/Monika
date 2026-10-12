"""Shim module: monika.application.agent.monitors.startup_watchdog."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.monitors.startup_watchdog")
_sys.modules[__name__] = _canonical
