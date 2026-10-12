"""Shim module: monika.application.plugins.scrapers.example_scraper.example_scraper."""

import sys as _sys
import importlib as _importlib

from monika.application.plugins.scrapers.example_scraper.example_scraper import *

_canonical = _importlib.import_module("monika.application.plugins.scrapers.example_scraper.example_scraper")
_sys.modules[__name__] = _canonical
