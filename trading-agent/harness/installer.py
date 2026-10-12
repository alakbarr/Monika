"""Shim module: monika.application.harness.installer."""

import sys as _sys
import importlib as _importlib

from monika.application.harness.installer import *

_canonical = _importlib.import_module("monika.application.harness.installer")
_sys.modules[__name__] = _canonical
