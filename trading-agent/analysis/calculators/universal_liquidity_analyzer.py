"""Shim module: monika.application.analysis.calculators.universal_liquidity_analyzer."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.universal_liquidity_analyzer import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.universal_liquidity_analyzer")
_sys.modules[__name__] = _canonical
