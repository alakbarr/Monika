"""Shim module: monika.application.skills.skills_hub."""

import sys as _sys
import importlib as _importlib

from monika.application.skills.skills_hub import *

_canonical = _importlib.import_module("monika.application.skills.skills_hub")
_sys.modules[__name__] = _canonical
