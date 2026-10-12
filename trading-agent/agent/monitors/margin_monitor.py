"""Shim module: monika.application.agent.monitors.margin_monitor."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.monitors.margin_monitor import *

_canonical = _importlib.import_module("monika.application.agent.monitors.margin_monitor")
_sys.modules[__name__] = _canonical
