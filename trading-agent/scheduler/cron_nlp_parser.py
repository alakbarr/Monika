"""Shim module: monika.application.scheduler.cron_nlp_parser."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.cron_nlp_parser import *

_canonical = _importlib.import_module("monika.application.scheduler.cron_nlp_parser")
_sys.modules[__name__] = _canonical
