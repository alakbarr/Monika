"""Shim module: monika.application.skills.continuous_learning."""

import sys as _sys
import importlib as _importlib

from monika.application.skills.continuous_learning import *

_canonical = _importlib.import_module("monika.application.skills.continuous_learning")
_sys.modules[__name__] = _canonical
