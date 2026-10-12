"""Shim module: monika.application.skills.loader."""

import sys as _sys
import importlib as _importlib

from monika.application.skills.loader import *
from monika.application.skills.loader import _SKILLS_DIR

_canonical = _importlib.import_module("monika.application.skills.loader")
_sys.modules[__name__] = _canonical
