"""Shim module: monika.application.scheduler.adhoc_proxy."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.adhoc_proxy import *

_canonical = _importlib.import_module("monika.application.scheduler.adhoc_proxy")
_sys.modules[__name__] = _canonical
