"""Shim module: monika.application.plugins.brokers.paper_trading.paper_plugin."""

import sys as _sys
import importlib as _importlib

from monika.application.plugins.brokers.paper_trading.paper_plugin import *

_canonical = _importlib.import_module("monika.application.plugins.brokers.paper_trading.paper_plugin")
_sys.modules[__name__] = _canonical
