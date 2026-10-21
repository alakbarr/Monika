"""Unit tests for Gemini schema serialization and Protobuf enum stringification."""

from monika.infrastructure.providers.gemini_provider import _sanitize_schema_for_gemini
from monika.infrastructure.providers.schema_normalizer import ToolSchemaNormalizer


def test_sanitize_schema_for_gemini_converts_integer_enum_to_string():
    schema = {
        "type": "object",
        "properties": {
            "target_phase": {
                "type": "integer",
                "enum": [1, 2, 3],
                "description": "Analysis phase indicator",
            },
            "status": {
                "type": "string",
                "enum": ["active", "pending"],
            },
        },
        "required": ["target_phase"],
    }

    sanitized = _sanitize_schema_for_gemini(schema)
    phase_prop = sanitized["properties"]["target_phase"]

    # Enum items MUST be strings for Gemini Protobuf
    assert phase_prop["enum"] == ["1", "2", "3"]
    assert phase_prop["type"] == "STRING"

    status_prop = sanitized["properties"]["status"]
    assert status_prop["enum"] == ["active", "pending"]
    assert status_prop["type"] == "STRING"


def test_tool_schema_normalizer_to_gemini_handles_nested_enums():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "transition_analysis_phase",
                "description": "Transition pipeline phase",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phase": {
                            "type": "integer",
                            "enum": [1, 2, 3],
                        }
                    },
                    "required": ["phase"],
                },
            },
        }
    ]

    gemini_tools = ToolSchemaNormalizer.to_gemini(tools)
    assert len(gemini_tools) == 1
    decls = gemini_tools[0]["functionDeclarations"]
    assert len(decls) == 1
    params = decls[0]["parameters"]
    phase_spec = params["properties"]["phase"]
    assert phase_spec["enum"] == ["1", "2", "3"]
    assert phase_spec["type"] == "STRING"
