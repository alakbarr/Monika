"""Shim module: monika.application.agent.thinking_timeout_guidance."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.thinking_timeout_guidance import *

_canonical = _importlib.import_module("monika.application.agent.thinking_timeout_guidance")
_sys.modules[__name__] = _canonical
