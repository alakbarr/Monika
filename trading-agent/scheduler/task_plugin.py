"""Shim module: monika.application.scheduler.task_plugin."""

import sys as _sys
import importlib as _importlib

from monika.application.scheduler.task_plugin import *

_canonical = _importlib.import_module("monika.application.scheduler.task_plugin")
_sys.modules[__name__] = _canonical
