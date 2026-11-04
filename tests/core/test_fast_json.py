"""
Tests for high-throughput serialization via fast_json (orjson / fallback).
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from monika.core.serialization.fast_json import (
    dumps,
    dumps_bytes,
    loads,
)


def test_fast_json_primitives() -> None:
    data = {"a": 1, "b": 2.5, "c": True, "d": None, "e": "hello"}
    serialized = dumps(data)
    assert isinstance(serialized, str)
    deserialized = loads(serialized)
    assert deserialized == data


def test_fast_json_bytes_output() -> None:
    data = {"key": "value", "list": [1, 2, 3]}
    b = dumps_bytes(data)
    assert isinstance(b, bytes)
    assert loads(b) == data


def test_fast_json_extended_types() -> None:
    class DummyObj:
        def to_dict(self):
            return {"name": "test"}

    uid = uuid4()
    now = datetime.now(timezone.utc)
    data = {
        "dec": Decimal("123.45"),
        "unique": {1, 2, 3},
        "id": uid,
        "ts": now,
        "obj": DummyObj(),
    }
    s = dumps(data)
    parsed = loads(s)

    # Strictly verify financial Decimal precision preservation as string
    assert parsed["dec"] == "123.45"
    assert sorted(parsed["unique"]) == [1, 2, 3]
    assert parsed["id"] == str(uid)
    assert parsed["obj"] == {"name": "test"}


def test_fast_json_sort_keys_and_indent() -> None:
    data = {"b": 2, "a": 1}
    s_sorted = dumps(data, sort_keys=True)
    assert s_sorted.startswith('{"a":1') or s_sorted.startswith('{"a": 1')

    s_indent = dumps(data, indent=2)
    assert "\n" in s_indent
