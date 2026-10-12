"""Shim module: monika.application.analysis.debate.multi_persona_risk_llm."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.debate.multi_persona_risk_llm import *

_canonical = _importlib.import_module("monika.application.analysis.debate.multi_persona_risk_llm")
_sys.modules[__name__] = _canonical
