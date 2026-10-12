"""Shim module: monika.application.scheduler.scraper_runner."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.scraper_runner import *

_canonical = _importlib.import_module("monika.application.scheduler.scraper_runner")
_sys.modules[__name__] = _canonical
