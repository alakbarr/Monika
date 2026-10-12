"""Shim module: monika.application.skills.skill_manager."""

import sys as _sys
import importlib as _importlib

from monika.application.skills.skill_manager import *

_canonical = _importlib.import_module("monika.application.skills.skill_manager")
_sys.modules[__name__] = _canonical
