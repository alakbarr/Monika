"""
High-throughput JSON serialization utilities powered by orjson with standard library fallback.
"""

from __future__ import annotations

from decimal import Decimal
import json
from typing import Any, Callable, Optional, Union
from uuid import UUID

try:
    import orjson
except ImportError:
    orjson = None


def default_serializer(obj: Any) -> Any:
    """Default serializer for types not natively handled by orjson."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return obj.to_dict()
    if hasattr(obj, "dict") and callable(obj.dict):
        return obj.dict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Type {type(obj)} not serializable")


def dumps_bytes(
    obj: Any,
    *,
    default: Optional[Callable[[Any], Any]] = default_serializer,
    option: Optional[int] = None,
    sort_keys: bool = False,
    indent: Optional[int] = None,
) -> bytes:
    """
    Serialize an object to JSON bytes.
    Zero-copy UTF-8 output powered by orjson.
    """
    if orjson is not None:
        opt = option
        if opt is None:
            opt = orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY | orjson.OPT_UTC_Z
        if sort_keys:
            opt |= orjson.OPT_SORT_KEYS
        if indent == 2:
            opt |= orjson.OPT_INDENT_2
        try:
            return orjson.dumps(obj, default=default, option=opt)
        except Exception:
            # Fall back to stdlib json if edge case unsupported by orjson occurs
            pass

    return json.dumps(obj, default=default, sort_keys=sort_keys, indent=indent).encode("utf-8")


def dumps(
    obj: Any,
    *,
    default: Optional[Callable[[Any], Any]] = default_serializer,
    option: Optional[int] = None,
    sort_keys: bool = False,
    indent: Optional[int] = None,
) -> str:
    """
    Serialize an object to JSON str.
    Decodes fast from orjson UTF-8 bytes.
    """
    return dumps_bytes(obj, default=default, option=option, sort_keys=sort_keys, indent=indent).decode("utf-8")


def loads(s: Union[str, bytes, bytearray]) -> Any:
    """
    Deserialize JSON from str or bytes into Python objects.
    """
    if orjson is not None:
        try:
            return orjson.loads(s)
        except Exception:
            pass
    if isinstance(s, (bytes, bytearray)):
        return json.loads(s.decode("utf-8"))
    return json.loads(s)
