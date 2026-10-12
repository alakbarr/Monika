"""Shim module: monika.application.analysis.prefetch.news_digest."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.prefetch.news_digest import *

_canonical = _importlib.import_module("monika.application.analysis.prefetch.news_digest")
_sys.modules[__name__] = _canonical
