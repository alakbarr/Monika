"""Shim module: monika.application.scheduler.order_reconciler."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.order_reconciler import *

_canonical = _importlib.import_module("monika.application.scheduler.order_reconciler")
_sys.modules[__name__] = _canonical
