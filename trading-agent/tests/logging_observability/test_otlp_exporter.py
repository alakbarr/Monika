import pytest
from logging_observability.tracing.otlp_exporter import OTLPSpanExporter


def test_otlp_exporter_disabled_by_default():
    exporter = OTLPSpanExporter(enabled=False)
    assert exporter.is_enabled is False
    # Calling export_span on disabled exporter is a safe no-op
    exporter.export_span({"name": "test_span"})
    assert len(exporter._buffer) == 0


def test_otlp_span_format_conversion():
    exporter = OTLPSpanExporter(enabled=False)
    span_dict = {
        "trace_id": "abcdef1234567890abcdef1234567890",
        "span_id": "1234567890abcdef",
        "parent_span_id": "fedcba0987654321",
        "name": "llm.claude-3-7-sonnet",
        "kind": "llm",
        "start_time": "2026-09-15T05:00:00Z",
        "end_time": "2026-09-15T05:00:02Z",
        "duration_ms": 2000.0,
        "status": "OK",
        "attributes": {
            "llm.provider": "openrouter",
            "input_tokens": 1500,
            "cost_usd": 0.0045,
            "streaming": True,
        },
    }

    otlp_span = exporter._to_otlp_span(span_dict)

    assert otlp_span["traceId"] == "abcdef1234567890abcdef1234567890"
    assert otlp_span["spanId"] == "1234567890abcdef"
    assert otlp_span["parentSpanId"] == "fedcba0987654321"
    assert otlp_span["name"] == "llm.claude-3-7-sonnet"
    assert otlp_span["kind"] == 1
    assert otlp_span["status"]["code"] == 1

    attr_map = {a["key"]: a["value"] for a in otlp_span["attributes"]}
    assert attr_map["llm.provider"] == {"stringValue": "openrouter"}
    assert attr_map["input_tokens"] == {"intValue": "1500"}
    assert attr_map["cost_usd"] == {"doubleValue": 0.0045}
    assert attr_map["streaming"] == {"boolValue": True}
