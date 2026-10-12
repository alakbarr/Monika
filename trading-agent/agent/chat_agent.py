"""Shim module: monika.application.agent.chat_agent."""
import sys as _sys
import importlib as _importlib

from monika.application.agent.chat_agent import *

_canonical = _importlib.import_module("monika.application.agent.chat_agent")
_sys.modules[__name__] = _canonical
