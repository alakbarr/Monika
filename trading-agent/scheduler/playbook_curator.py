"""Shim module: monika.application.scheduler.playbook_curator."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.playbook_curator import *

_canonical = _importlib.import_module("monika.application.scheduler.playbook_curator")
_sys.modules[__name__] = _canonical
