"""Shim module: monika.application.analysis.prefetch.news_digest."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.prefetch.news_digest import *
from monika.application.analysis.prefetch.news_digest import _jaccard_title_similarity

_canonical = _importlib.import_module("monika.application.analysis.prefetch.news_digest")
_sys.modules[__name__] = _canonical
