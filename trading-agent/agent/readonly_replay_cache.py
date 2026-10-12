"""Shim module: monika.application.agent.readonly_replay_cache."""
import sys as _sys
import importlib as _importlib

_canonical = _importlib.import_module("monika.application.agent.readonly_replay_cache")
_sys.modules[__name__] = _canonical
