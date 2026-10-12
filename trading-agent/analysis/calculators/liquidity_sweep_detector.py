"""Shim module: monika.application.analysis.calculators.liquidity_sweep_detector."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.calculators.liquidity_sweep_detector import *

_canonical = _importlib.import_module("monika.application.analysis.calculators.liquidity_sweep_detector")
_sys.modules[__name__] = _canonical
