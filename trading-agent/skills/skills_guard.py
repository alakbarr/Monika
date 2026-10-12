"""Shim module: monika.application.skills.skills_guard."""

import sys as _sys
import importlib as _importlib

from monika.application.skills.skills_guard import *

_canonical = _importlib.import_module("monika.application.skills.skills_guard")
_sys.modules[__name__] = _canonical
