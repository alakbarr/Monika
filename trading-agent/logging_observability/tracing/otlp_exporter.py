"""
OTLP Span Exporter — optional integration with OpenTelemetry Collector.
Enable via settings.yaml: observability.otlp.enabled: true

Exports spans in OTLP/HTTP JSON format to any OTel-compatible backend
(Grafana Tempo, Jaeger, Datadog, SigNoz, Honeycomb).

ponytail: No-op when disabled. Single class, no heavy framework dependencies.
"""
import logging
import json
import time
import threading
from collections import deque
from typing import Optional, List, Dict, Any

logger = logging.getLogger("TradingAgent.OTLPExporter")


class OTLPSpanExporter:
    """Batched OTLP/HTTP span exporter. Flushes every N spans or T seconds."""

    def __init__(
        self,
        endpoint: str = "http://localhost:4318/v1/traces",
        batch_size: int = 50,
        flush_interval_s: float = 10.0,
        enabled: bool = False,
    ):
        self._endpoint = endpoint
        self._batch_size = batch_size
        self._flush_interval = flush_interval_s
        self._enabled = enabled
        self._buffer: deque = deque(maxlen=5000)
        self._flush_thread: Optional[threading.Thread] = None

        if self._enabled:
            self._start_flush_thread()
            logger.info(f"[OTLPExporter] Enabled, exporting to {endpoint}")
        else:
            logger.debug("[OTLPExporter] Disabled (observability.otlp.enabled = false)")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def export_span(self, span_dict: Dict[str, Any]):
        """Queue a span for export. No-op if disabled."""
        if not self._enabled:
            return
        self._buffer.append(self._to_otlp_span(span_dict))
        if len(self._buffer) >= self._batch_size:
            self._flush()

    def _to_otlp_span(self, span: Dict[str, Any]) -> Dict[str, Any]:
        """Convert internal TraceRecord dict to OTLP span format."""
        attrs = []
        for k, v in span.get("attributes", {}).items():
            if isinstance(v, bool):
                val_dict = {"boolValue": v}
            elif isinstance(v, int):
                val_dict = {"intValue": str(v)}
            elif isinstance(v, float):
                val_dict = {"doubleValue": v}
            else:
                val_dict = {"stringValue": str(v)}
            attrs.append({"key": str(k), "value": val_dict})

        return {
            "traceId": span.get("trace_id", ""),
            "spanId": span.get("span_id", ""),
            "parentSpanId": span.get("parent_span_id") or "",
            "name": span.get("name", ""),
            "kind": 1,  # SPAN_KIND_INTERNAL
            "startTimeUnixNano": self._iso_to_nano(span.get("start_time", "")),
            "endTimeUnixNano": self._iso_to_nano(span.get("end_time", "")),
            "attributes": attrs,
            "status": {
                "code": 2 if span.get("status") == "ERROR" else 1,
                "message": span.get("error") or "",
            },
        }

    def _flush(self):
        if not self._buffer:
            return
        batch = [self._buffer.popleft() for _ in range(min(len(self._buffer), self._batch_size))]
        try:
            import urllib.request
            payload = {
                "resourceSpans": [{
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": "tradeagent"}},
                        ]
                    },
                    "scopeSpans": [{"spans": batch}],
                }]
            }
            req = urllib.request.Request(
                self._endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                if resp.status not in (200, 202):
                    logger.warning(f"[OTLPExporter] Export returned status {resp.status}")
        except Exception as e:
            logger.debug(f"[OTLPExporter] Export error (non-fatal): {e}")

    def _start_flush_thread(self):
        def _loop():
            while self._enabled:
                time.sleep(self._flush_interval)
                self._flush()

        self._flush_thread = threading.Thread(target=_loop, daemon=True, name="otlp-flush")
        self._flush_thread.start()

    @staticmethod
    def _iso_to_nano(iso_str: str) -> int:
        if not iso_str:
            return 0
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1_000_000_000)
        except Exception:
            return 0


# Global singleton exporter (disabled by default)
global_otlp_exporter = OTLPSpanExporter(enabled=False)
