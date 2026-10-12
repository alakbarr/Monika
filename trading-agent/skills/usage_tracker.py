"""Shim module: monika.application.skills.usage_tracker."""

import sys as _sys
import importlib as _importlib

from monika.application.skills.usage_tracker import *

_canonical = _importlib.import_module("monika.application.skills.usage_tracker")
_sys.modules[__name__] = _canonical
