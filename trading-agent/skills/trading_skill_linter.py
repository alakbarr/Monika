"""Shim module: monika.application.skills.trading_skill_linter."""

import sys as _sys
import importlib as _importlib

from monika.application.skills.trading_skill_linter import *

_canonical = _importlib.import_module("monika.application.skills.trading_skill_linter")
_sys.modules[__name__] = _canonical
