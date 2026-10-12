"""Shim module: monika.application.agent.empty_response_guard."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.empty_response_guard import *

_canonical = _importlib.import_module("monika.application.agent.empty_response_guard")
_sys.modules[__name__] = _canonical
