"""Shim module: monika.application.scheduler.post_release_analyzer."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.post_release_analyzer import *

_canonical = _importlib.import_module("monika.application.scheduler.post_release_analyzer")
_sys.modules[__name__] = _canonical
