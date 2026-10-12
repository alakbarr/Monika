"""Shim module: monika.application.plugins.indicators.custom_indicator.custom_indicator."""

import sys as _sys
import importlib as _importlib

from monika.application.plugins.indicators.custom_indicator.custom_indicator import *

_canonical = _importlib.import_module("monika.application.plugins.indicators.custom_indicator.custom_indicator")
_sys.modules[__name__] = _canonical
