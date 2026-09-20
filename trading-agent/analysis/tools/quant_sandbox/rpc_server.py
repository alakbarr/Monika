"""
Local Loopback Quant Sandbox RPC Server & Client.

Executes intensive quantitative data calculations (ticks, candles, statistical distributions,
Hurst exponents, correlations, volatility) via an isolated local loopback RPC interface.
Avoids dumping massive raw price arrays into the LLM context window.
"""

import asyncio
import json
import logging
import math
from typing import Dict, Any, Optional, List

from analysis.tools.kernel.persistent_kernel import PersistentCodeKernel

logger = logging.getLogger("TradingAgent.QuantSandboxRPC")


class QuantSandboxRpcServer:
    """
    Lightweight JSON-RPC loopback execution server for quantitative calculations.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8991):
        self.host = host
        self.port = port
        self.kernel = PersistentCodeKernel(session_id="quant_rpc")
        self._server: Optional[asyncio.Server] = None
        self._is_running = False

    async def handle_request(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches JSON-RPC 2.0 requests to internal calculation handlers."""
        req_id = request_data.get("id", 1)
        method = request_data.get("method", "")
        params = request_data.get("params", {})

        try:
            if method == "compute_stats":
                result = self._compute_stats(params)
            elif method == "compute_correlation":
                result = self._compute_correlation(params)
            elif method == "execute_code":
                result = self._execute_code(params)
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": result,
            }
        except Exception as exc:
            logger.error(f"[QuantRPC] Error executing {method}: {exc}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32000, "message": str(exc)},
            }

    def _compute_stats(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Computes statistical properties of a numeric series without returning full arrays."""
        series = params.get("series", [])
        if not series or len(series) < 2:
            return {"count": len(series), "error": "Insufficient data points"}

        n = len(series)
        mean = sum(series) / n
        variance = sum((x - mean) ** 2 for x in series) / (n - 1) if n > 1 else 0.0
        std = math.sqrt(variance)
        last_val = series[-1]
        z_score = (last_val - mean) / std if std > 0 else 0.0

        # Min / Max / Range
        min_v = min(series)
        max_v = max(series)

        # Approximate Hurst Exponent for mean-reversion vs trend persistence
        hurst = self._estimate_hurst(series)

        return {
            "count": n,
            "mean": round(mean, 5),
            "std": round(std, 5),
            "min": round(min_v, 5),
            "max": round(max_v, 5),
            "last": round(last_val, 5),
            "z_score": round(z_score, 3),
            "hurst_exponent": round(hurst, 3) if hurst is not None else None,
            "regime_bias": "trending" if hurst and hurst > 0.55 else ("mean_reverting" if hurst and hurst < 0.45 else "random_walk"),
        }

    def _compute_correlation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates Pearson correlation between two numeric series."""
        s_a = params.get("series_a", [])
        s_b = params.get("series_b", [])

        min_len = min(len(s_a), len(s_b))
        if min_len < 3:
            return {"error": "Insufficient data points for correlation"}

        x = s_a[-min_len:]
        y = s_b[-min_len:]

        n = min_len
        mean_x = sum(x) / n
        mean_y = sum(y) / n

        num = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        den_x = math.sqrt(sum((x[i] - mean_x) ** 2 for i in range(n)))
        den_y = math.sqrt(sum((y[i] - mean_y) ** 2 for i in range(n)))

        if den_x == 0 or den_y == 0:
            corr = 0.0
        else:
            corr = num / (den_x * den_y)

        return {
            "samples": n,
            "correlation": round(corr, 4),
            "strong_correlation": abs(corr) >= 0.70,
        }

    def _execute_code(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Runs custom Python calculation snippet in persistent kernel."""
        code = params.get("code", "")
        timeout = float(params.get("timeout_seconds", 10.0))
        output, success = self.kernel.execute(code, timeout_seconds=timeout)
        return {
            "output": output,
            "success": success,
        }

    def _estimate_hurst(self, series: List[float]) -> Optional[float]:
        """Simplified Rescaled Range (R/S) Hurst exponent approximation."""
        try:
            n = len(series)
            if n < 16:
                return None
            mean = sum(series) / n
            y = [x - mean for x in series]
            z = []
            running = 0.0
            for val in y:
                running += val
                z.append(running)
            r = max(z) - min(z)
            s = math.sqrt(sum((x - mean) ** 2 for x in series) / n)
            if s <= 0 or r <= 0:
                return 0.5
            rs = r / s
            hurst = math.log(rs) / math.log(n)
            return min(max(hurst, 0.0), 1.0)
        except Exception:
            return 0.5

    async def start(self) -> None:
        """Starts loopback TCP server."""
        async def _client_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
            try:
                line = await reader.readline()
                if not line:
                    return
                req = json.loads(line.decode("utf-8"))
                resp = await self.handle_request(req)
                writer.write((json.dumps(resp) + "\n").encode("utf-8"))
                await writer.drain()
            except Exception as e:
                logger.debug(f"[QuantRPC] Connection error: {e}")
            finally:
                writer.close()
                await writer.wait_closed()

        self._server = await asyncio.start_server(_client_handler, self.host, self.port)
        self._is_running = True
        logger.info(f"[QuantRPC] Quant Sandbox RPC Server listening on {self.host}:{self.port}")

    async def stop(self) -> None:
        """Stops loopback server."""
        self._is_running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("[QuantRPC] Quant Sandbox RPC Server stopped.")


class QuantSandboxClient:
    """
    Direct in-process or loopback client for executing quant computations.
    """

    def __init__(self, server: Optional[QuantSandboxRpcServer] = None):
        self._server = server or QuantSandboxRpcServer()

    async def compute_stats(self, series: List[float]) -> Dict[str, Any]:
        """Compute summary statistics for a price or tick series."""
        resp = await self._server.handle_request({
            "id": 1,
            "method": "compute_stats",
            "params": {"series": series},
        })
        return resp.get("result", {})

    async def compute_correlation(self, series_a: List[float], series_b: List[float]) -> Dict[str, Any]:
        """Compute correlation between two series."""
        resp = await self._server.handle_request({
            "id": 2,
            "method": "compute_correlation",
            "params": {"series_a": series_a, "series_b": series_b},
        })
        return resp.get("result", {})

    async def execute_code(self, code: str, timeout_seconds: float = 10.0) -> Dict[str, Any]:
        """Execute sandboxed quantitative analysis code."""
        resp = await self._server.handle_request({
            "id": 3,
            "method": "execute_code",
            "params": {"code": code, "timeout_seconds": timeout_seconds},
        })
        return resp.get("result", {})
