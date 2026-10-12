"""Shim module: monika.application.agent.turn_tool_round."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.turn_tool_round import *

_canonical = _importlib.import_module("monika.application.agent.turn_tool_round")
_sys.modules[__name__] = _canonical
