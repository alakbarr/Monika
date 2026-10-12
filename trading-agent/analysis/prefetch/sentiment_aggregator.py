"""Shim module: monika.application.analysis.prefetch.sentiment_aggregator."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.prefetch.sentiment_aggregator import *

_canonical = _importlib.import_module("monika.application.analysis.prefetch.sentiment_aggregator")
_sys.modules[__name__] = _canonical
