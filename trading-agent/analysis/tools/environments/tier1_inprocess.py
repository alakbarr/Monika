"""Shim module: monika.application.analysis.tools.environments.tier1_inprocess."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.environments.tier1_inprocess import *

_canonical = _importlib.import_module("monika.application.analysis.tools.environments.tier1_inprocess")
_sys.modules[__name__] = _canonical
