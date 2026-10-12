"""Shim module: monika.application.analysis.schemas.pydantic_schemas."""
import sys as _sys
import importlib as _importlib

from monika.application.analysis.schemas.pydantic_schemas import *

_canonical = _importlib.import_module("monika.application.analysis.schemas.pydantic_schemas")
_sys.modules[__name__] = _canonical
