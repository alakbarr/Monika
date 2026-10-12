"""Shim module: monika.application.execution.broker_registry."""

import sys as _sys
import importlib as _importlib

from monika.application.execution.broker_registry import *

_canonical = _importlib.import_module("monika.application.execution.broker_registry")
_sys.modules[__name__] = _canonical
