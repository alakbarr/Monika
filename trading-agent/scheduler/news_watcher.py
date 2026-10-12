"""Shim module: monika.application.scheduler.news_watcher."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.news_watcher import *

_canonical = _importlib.import_module("monika.application.scheduler.news_watcher")
_sys.modules[__name__] = _canonical
