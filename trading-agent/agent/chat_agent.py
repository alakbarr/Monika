"""Shim module: monika.application.agent.chat_agent."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.chat_agent")
_sys.modules[__name__] = _canonical
