"""Shim module: monika.application.plugins.brokers.mt5_local.mt5_plugin."""

import sys as _sys
import importlib as _importlib

from monika.application.plugins.brokers.mt5_local.mt5_plugin import *

_canonical = _importlib.import_module("monika.application.plugins.brokers.mt5_local.mt5_plugin")
_sys.modules[__name__] = _canonical
