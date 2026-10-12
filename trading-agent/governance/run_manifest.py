"""Shim module: monika.application.governance.run_manifest."""

import sys as _sys
import importlib as _importlib

from monika.application.governance.run_manifest import *

_canonical = _importlib.import_module("monika.application.governance.run_manifest")
_sys.modules[__name__] = _canonical
