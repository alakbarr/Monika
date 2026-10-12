"""Shim module: monika.application.analysis.tools.environments.base_environment."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.environments.base_environment import *

_canonical = _importlib.import_module("monika.application.analysis.tools.environments.base_environment")
_sys.modules[__name__] = _canonical
