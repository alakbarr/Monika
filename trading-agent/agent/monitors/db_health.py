"""Shim module: monika.application.agent.monitors.db_health."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.monitors.db_health import *

_canonical = _importlib.import_module("monika.application.agent.monitors.db_health")
_sys.modules[__name__] = _canonical
