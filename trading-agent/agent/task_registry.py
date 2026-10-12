"""Shim module: monika.application.agent.task_registry."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.task_registry")
_sys.modules[__name__] = _canonical
