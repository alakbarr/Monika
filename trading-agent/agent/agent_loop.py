"""Shim module: monika.application.agent.agent_loop."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.agent_loop import *

_canonical = _importlib.import_module("monika.application.agent.agent_loop")
_sys.modules[__name__] = _canonical
