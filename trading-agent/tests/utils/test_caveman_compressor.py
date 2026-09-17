import pytest
from utils.llm.caveman_compressor import compress_tool_payload

def test_compress_tool_payload():
    # Test float rounding
    assert compress_tool_payload(1.123456789) == 1.12346
    assert compress_tool_payload(1.00000) == 1
    
    # Test dictionary compression (removing None, empty strings, empty lists, empty dicts)
    input_dict = {
        "valid": "data",
        "null_val": None,
        "empty_str": "",
        "empty_list": [],
        "empty_dict": {},
        "nested": {
            "keep": 100,
            "remove": None
        }
    }
    expected_dict = {
        "valid": "data",
        "nested": {
            "keep": 100
        }
    }
    assert compress_tool_payload(input_dict) == expected_dict

    # Test list compression
    input_list = [
        {"a": 1, "b": None},
        None,
        "",
        [],
        {"c": 2}
    ]
    expected_list = [
        {"a": 1},
        {"c": 2}
    ]
    assert compress_tool_payload(input_list) == expected_list

    # Test extreme float near 0
    assert compress_tool_payload(1e-10) == 0.0

    # Test recursive empty resolution (dict becomes empty after children are removed)
    recursive_empty = {
        "a": {
            "b": {
                "c": None
            }
        },
        "d": 1
    }
    expected_recursive = {
        "d": 1
    }
    assert compress_tool_payload(recursive_empty) == expected_recursive
