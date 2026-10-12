"""Shim module: monika.application.analysis.tools.handlers.behavioral_alert_tool."""

import sys as _sys
import importlib as _importlib

from monika.application.analysis.tools.handlers.behavioral_alert_tool import *

_canonical = _importlib.import_module("monika.application.analysis.tools.handlers.behavioral_alert_tool")
_sys.modules[__name__] = _canonical
