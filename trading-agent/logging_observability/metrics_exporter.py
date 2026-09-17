# ==============================================================================
# File: logging_observability/metrics_exporter.py
# ==============================================================================

"""
Prometheus / OpenMetrics Exporter untuk AI Trading Agent.
Menyediakan metrik operasional, latensi analisis, biaya LLM, status MT5, dan metrik risiko.
"""

import time
import threading
from typing import Dict, List, Any, Optional

class MetricsCollector:
    """Singleton thread-safe in-memory metric collector yang menghasilkan format Prometheus."""
    _instance: Optional["MetricsCollector"] = None
    _lock = threading.RLock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MetricsCollector, cls).__new__(cls)
                cls._instance._init_metrics()
            return cls._instance

    def _init_metrics(self):
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._labeled_counters: Dict[str, Dict[str, float]] = {}
        self._labeled_gauges: Dict[str, Dict[str, float]] = {}
        self._histograms: Dict[str, List[float]] = {}
        
        # Inisialisasi default baseline
        self.set_gauge("agent_uptime_seconds", 0.0)
        self.set_gauge("open_positions_count", 0.0)
        self.set_gauge("floating_pnl_usd", 0.0)
        self.set_gauge("account_equity_usd", 10000.0)
        self.set_gauge("vix_current_level", 15.0)
        self.set_gauge("mt5_primary_connected", 1.0)
        self.set_gauge("mt5_secondary_connected", 0.0)
        self.set_gauge("active_gateway_is_primary", 1.0)

    def inc_counter(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None):
        with self._lock:
            if labels:
                label_key = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
                if name not in self._labeled_counters:
                    self._labeled_counters[name] = {}
                self._labeled_counters[name][label_key] = self._labeled_counters[name].get(label_key, 0.0) + value
            else:
                self._counters[name] = self._counters.get(name, 0.0) + value

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        with self._lock:
            if labels:
                label_key = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
                if name not in self._labeled_gauges:
                    self._labeled_gauges[name] = {}
                self._labeled_gauges[name][label_key] = float(value)
            else:
                self._gauges[name] = float(value)

    def record_histogram(self, name: str, value: float):
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = []
            self._histograms[name].append(float(value))
            # Simpan 500 nilai terakhir
            if len(self._histograms[name]) > 500:
                self._histograms[name] = self._histograms[name][-500:]

    def generate_prometheus_metrics(self) -> str:
        """Menghasilkan representasi string teks Prometheus/OpenMetrics standar."""
        lines = []
        with self._lock:
            # Gauges
            for name, val in sorted(self._gauges.items()):
                metric_name = f"trading_agent_{name}"
                lines.append(f"# HELP {metric_name} Gauge metric for {name}")
                lines.append(f"# TYPE {metric_name} gauge")
                lines.append(f"{metric_name} {val}")

            # Labeled Gauges
            for name, label_dict in sorted(self._labeled_gauges.items()):
                metric_name = f"trading_agent_{name}"
                lines.append(f"# HELP {metric_name} Labeled gauge metric for {name}")
                lines.append(f"# TYPE {metric_name} gauge")
                for label_str, val in sorted(label_dict.items()):
                    lines.append(f"{metric_name}{{{label_str}}} {val}")

            # Counters
            for name, val in sorted(self._counters.items()):
                metric_name = f"trading_agent_{name}"
                lines.append(f"# HELP {metric_name} Counter metric for {name}")
                lines.append(f"# TYPE {metric_name} counter")
                lines.append(f"{metric_name} {val}")

            # Labeled Counters
            for name, label_dict in sorted(self._labeled_counters.items()):
                metric_name = f"trading_agent_{name}"
                lines.append(f"# HELP {metric_name} Labeled counter metric for {name}")
                lines.append(f"# TYPE {metric_name} counter")
                for label_str, val in sorted(label_dict.items()):
                    lines.append(f"{metric_name}{{{label_str}}} {val}")

            # Histograms (Count, Sum)
            for name, values in sorted(self._histograms.items()):
                if not values:
                    continue
                count = len(values)
                val_sum = sum(values)
                metric_name = f"trading_agent_{name}"
                lines.append(f"# HELP {metric_name} Summary metric for {name}")
                lines.append(f"# TYPE {metric_name} summary")
                lines.append(f"{metric_name}_count {count}")
                lines.append(f"{metric_name}_sum {val_sum:.4f}")

        return "\n".join(lines) + "\n"

# Global helper instance
metrics = MetricsCollector()
