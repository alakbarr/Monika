"""
High-throughput serialization package.
"""

from monika.core.serialization.fast_json import (
    default_serializer,
    dumps,
    dumps_bytes,
    loads,
)

__all__ = [
    "default_serializer",
    "dumps",
    "dumps_bytes",
    "loads",
]
