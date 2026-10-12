"""Shim module: monika.application.analysis.tools.environments.tier3_docker."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.environments.tier3_docker import *

_canonical = _importlib.import_module("monika.application.analysis.tools.environments.tier3_docker")
_sys.modules[__name__] = _canonical
