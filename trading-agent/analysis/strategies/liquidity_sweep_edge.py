"""Shim module: monika.application.analysis.strategies.liquidity_sweep_edge."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.strategies.liquidity_sweep_edge import *

_canonical = _importlib.import_module("monika.application.analysis.strategies.liquidity_sweep_edge")
_sys.modules[__name__] = _canonical
