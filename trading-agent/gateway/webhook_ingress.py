# ==============================================================================
# File: gateway/webhook_ingress.py
# ==============================================================================

"""
Secure Webhook Ingress & Omnichannel Event Receiver.
Features:
  1. HMAC-SHA256 signature verification (supports raw hex or 'sha256=<hex>' prefix).
  2. Secret rotation support (primary & secondary verification secrets).
  3. Replay attack protection with strict timestamp drift bounds (default: 300s).
  4. Nonce / idempotency cache to prevent duplicate request processing.
  5. Asynchronous event dispatcher for trade signals, risk alerts, and HITL approval responses.
"""

from __future__ import annotations

import asyncio
import collections
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("TradingAgent.Gateway.WebhookIngress")

DEFAULT_REPLAY_WINDOW_SECONDS = 300.0  # 5 minutes
MAX_NONCE_CACHE_SIZE = 10000


class WebhookIngressStatus(str, Enum):
    SUCCESS = "SUCCESS"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    EXPIRED_TIMESTAMP = "EXPIRED_TIMESTAMP"
    REPLAY_DETECTED = "REPLAY_DETECTED"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"
    HANDLER_ERROR = "HANDLER_ERROR"
    UNHANDLED_EVENT = "UNHANDLED_EVENT"


@dataclass
class WebhookIngressResult:
    status: WebhookIngressStatus
    event_type: Optional[str] = None
    event_id: Optional[str] = None
    message: str = ""
    data: Optional[Dict[str, Any]] = None

    @property
    def is_success(self) -> bool:
        return self.status == WebhookIngressStatus.SUCCESS


class WebhookSignatureVerifier:
    """
    Cryptographic HMAC-SHA256 signature verifier supporting secret rotation and replay bounds.
    """

    def __init__(
        self,
        primary_secret: str,
        secondary_secret: Optional[str] = None,
        max_drift_seconds: float = DEFAULT_REPLAY_WINDOW_SECONDS,
    ):
        self.primary_secret = primary_secret.encode("utf-8") if isinstance(primary_secret, str) else primary_secret
        self.secondary_secret = (
            secondary_secret.encode("utf-8")
            if (secondary_secret and isinstance(secondary_secret, str))
            else secondary_secret
        )
        self.max_drift_seconds = max_drift_seconds

    def compute_signature(self, payload: bytes, secret: Optional[bytes] = None) -> str:
        """Generates standard lowercase hex HMAC-SHA256 signature."""
        active_secret = secret or self.primary_secret
        return hmac.new(active_secret, payload, hashlib.sha256).hexdigest()

    def verify_signature(self, payload: bytes, signature_header: str) -> bool:
        """
        Constant-time verification of HMAC-SHA256 signature.
        Supports both raw hex and 'sha256=' prefixed strings.
        Tries primary secret first, then secondary secret if configured.
        """
        if not signature_header:
            return False

        sig = signature_header.strip()
        if sig.startswith("sha256="):
            sig = sig[len("sha256="):]

        expected_primary = self.compute_signature(payload, self.primary_secret)
        if hmac.compare_digest(expected_primary.lower(), sig.lower()):
            return True

        if self.secondary_secret:
            expected_secondary = self.compute_signature(payload, self.secondary_secret)
            if hmac.compare_digest(expected_secondary.lower(), sig.lower()):
                logger.info("[WebhookVerifier] Signature verified using secondary rotation secret.")
                return True

        return False

    def verify_timestamp(self, timestamp_str: str, now: Optional[float] = None) -> Tuple[bool, str]:
        """
        Validates timestamp against allowed drift window to prevent replay attacks.
        Supports UNIX epoch seconds, milliseconds, or ISO-8601 strings.
        """
        if not timestamp_str:
            return False, "Missing timestamp header."

        current_time = now if now is not None else time.time()
        try:
            # Try numeric timestamp first
            ts = float(timestamp_str)
            if ts > 1e11:  # Likely milliseconds
                ts = ts / 1000.0
        except ValueError:
            # Try ISO 8601 parsing
            from datetime import datetime, timezone
            try:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                ts = dt.timestamp()
            except Exception as exc:
                return False, f"Malformed timestamp format: {exc}"

        drift = abs(current_time - ts)
        if drift > self.max_drift_seconds:
            return False, f"Timestamp drift exceeds window: drift={drift:.1f}s > allowed={self.max_drift_seconds}s"

        return True, "Timestamp valid."


WebhookHandler = Callable[[Dict[str, Any], Dict[str, str]], Awaitable[Any]]


class WebhookIngressRouter:
    """
    High-reliability webhook ingress processor with idempotency cache and async dispatch.
    """

    def __init__(
        self,
        verifier: Optional[WebhookSignatureVerifier] = None,
        enforce_signature: bool = True,
        enforce_timestamp: bool = True,
    ):
        self.verifier = verifier
        self.enforce_signature = enforce_signature
        self.enforce_timestamp = enforce_timestamp
        self._handlers: Dict[str, List[WebhookHandler]] = collections.defaultdict(list)
        self._seen_nonces: collections.OrderedDict[str, float] = collections.OrderedDict()
        self._lock = asyncio.Lock()

    def register_handler(self, event_type: str, handler: WebhookHandler) -> None:
        """Registers an asynchronous event handler for a given event type."""
        self._handlers[event_type].append(handler)
        logger.debug(f"[WebhookIngress] Registered handler for event '{event_type}'.")

    async def _check_and_record_nonce(self, nonce: str, now: float) -> bool:
        """Returns True if nonce is fresh and recorded; False if duplicate (replay)."""
        async with self._lock:
            # Prune nonces older than 2x replay window
            cutoff = now - (DEFAULT_REPLAY_WINDOW_SECONDS * 2)
            while self._seen_nonces:
                oldest_k, oldest_ts = next(iter(self._seen_nonces.items()))
                if oldest_ts < cutoff or len(self._seen_nonces) > MAX_NONCE_CACHE_SIZE:
                    self._seen_nonces.pop(oldest_k, None)
                else:
                    break

            if nonce in self._seen_nonces:
                return False

            self._seen_nonces[nonce] = now
            return True

    async def process_event(
        self,
        raw_body: bytes,
        headers: Dict[str, str],
        now: Optional[float] = None,
    ) -> WebhookIngressResult:
        """
        Processes an incoming webhook HTTP request:
        1. Checks signature (X-Signature / X-Hub-Signature-256)
        2. Validates timestamp (X-Timestamp)
        3. Prevents replay via Nonce (X-Nonce / X-Delivery-Id or SHA256 of payload+ts)
        4. Parses JSON payload
        5. Dispatches to registered handlers
        """
        current_time = now if now is not None else time.time()
        # Normalize header keys to lowercase
        norm_headers = {k.lower(): v for k, v in headers.items()}

        # 1. Signature Verification
        if self.enforce_signature:
            if not self.verifier:
                return WebhookIngressResult(
                    status=WebhookIngressStatus.INVALID_SIGNATURE,
                    message="Signature enforcement enabled but no verifier configured.",
                )
            sig_header = (
                norm_headers.get("x-signature")
                or norm_headers.get("x-hub-signature-256")
                or norm_headers.get("x-signature-256")
                or ""
            )
            if not self.verifier.verify_signature(raw_body, sig_header):
                logger.warning("[WebhookIngress] Webhook rejected: invalid cryptographic signature.")
                return WebhookIngressResult(
                    status=WebhookIngressStatus.INVALID_SIGNATURE,
                    message="Cryptographic signature verification failed.",
                )

        # 2. Timestamp Verification
        if self.enforce_timestamp and self.verifier:
            ts_header = norm_headers.get("x-timestamp") or norm_headers.get("x-request-timestamp") or ""
            valid_ts, ts_msg = self.verifier.verify_timestamp(ts_header, now=current_time)
            if not valid_ts:
                logger.warning(f"[WebhookIngress] Webhook rejected: {ts_msg}")
                return WebhookIngressResult(
                    status=WebhookIngressStatus.EXPIRED_TIMESTAMP,
                    message=ts_msg,
                )

        # 3. Replay Protection / Nonce Check
        nonce = (
            norm_headers.get("x-nonce")
            or norm_headers.get("x-delivery-id")
            or norm_headers.get("x-request-id")
            or hashlib.sha256(raw_body + str(round(current_time, 1)).encode()).hexdigest()
        )
        is_fresh = await self._check_and_record_nonce(nonce, current_time)
        if not is_fresh:
            logger.warning(f"[WebhookIngress] Webhook rejected: replay attack detected for nonce '{nonce}'.")
            return WebhookIngressResult(
                status=WebhookIngressStatus.REPLAY_DETECTED,
                message=f"Duplicate request / replay detected (nonce={nonce}).",
            )

        # 4. JSON Payload Parsing
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except Exception as exc:
            return WebhookIngressResult(
                status=WebhookIngressStatus.INVALID_PAYLOAD,
                message=f"Payload is not valid JSON: {exc}",
            )

        event_type = payload.get("event_type") or payload.get("type") or norm_headers.get("x-event-type") or "generic"
        event_id = payload.get("event_id") or payload.get("id") or nonce

        # 5. Dispatching to Handlers
        handlers = self._handlers.get(event_type, [])
        handlers_generic = self._handlers.get("*", [])
        all_handlers = handlers + handlers_generic

        if not all_handlers:
            logger.info(f"[WebhookIngress] Unhandled event received: '{event_type}' (id={event_id}).")
            return WebhookIngressResult(
                status=WebhookIngressStatus.UNHANDLED_EVENT,
                event_type=event_type,
                event_id=event_id,
                message=f"No handlers registered for event '{event_type}'.",
                data=payload,
            )

        # Dispatch async
        results = []
        for handler in all_handlers:
            try:
                res = await handler(payload, norm_headers)
                results.append(res)
            except Exception as exc:
                logger.error(f"[WebhookIngress] Error executing handler for event '{event_type}': {exc}", exc_info=True)
                return WebhookIngressResult(
                    status=WebhookIngressStatus.HANDLER_ERROR,
                    event_type=event_type,
                    event_id=event_id,
                    message=f"Handler execution error: {exc}",
                    data=payload,
                )

        logger.info(f"[WebhookIngress] Event '{event_type}' (id={event_id}) dispatched successfully to {len(all_handlers)} handlers.")
        return WebhookIngressResult(
            status=WebhookIngressStatus.SUCCESS,
            event_type=event_type,
            event_id=event_id,
            message=f"Processed successfully by {len(all_handlers)} handlers.",
            data={"handler_results": results, "payload": payload},
        )


def normalize_tradingview_payload(raw_data: Union[dict, str, bytes]) -> dict:
    """
    Normalizes a TradingView Pine Script webhook alert payload into Monika's standard trade_signal structure.
    
    Handles:
      - Raw JSON string, bytes, or parsed dict
      - Key-value plain text alert payloads (e.g., 'ticker=EURUSD\\naction=buy')
      - Prefix stripping for exchange symbols (e.g., 'OANDA:EURUSD', 'FX:EURUSD' -> 'EURUSD')
      - Direction mapping ('buy', 'long', 'entry_long' -> 'BUY'; 'sell', 'short', 'entry_short' -> 'SELL')
      - Numeric extraction for price, volume/contracts, SL, and TP
    """
    data: dict[str, Any] = {}
    if isinstance(raw_data, bytes):
        raw_str = raw_data.decode("utf-8", errors="replace").strip()
    elif isinstance(raw_data, str):
        raw_str = raw_data.strip()
    elif isinstance(raw_data, dict):
        raw_str = ""
        data = dict(raw_data)
    else:
        raw_str = str(raw_data)

    if raw_str:
        try:
            parsed = json.loads(raw_str)
            if isinstance(parsed, dict):
                data = parsed
            else:
                data = {"message": str(parsed)}
        except Exception:
            # Fallback: parse lines formatted as key=value or key: value
            data = {}
            for line in raw_str.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip().lower()] = v.strip()
                elif ":" in line:
                    k, v = line.split(":", 1)
                    data[k.strip().lower()] = v.strip()
                else:
                    data.setdefault("comment_lines", []).append(line)
            if "comment_lines" in data:
                data["comment"] = " ".join(data.pop("comment_lines"))

    # Helper to retrieve case-insensitive keys
    def _get_val(*keys: str, default: Any = None) -> Any:
        for k in keys:
            for dk, dv in data.items():
                if dk.lower() == k.lower() and dv is not None:
                    return dv
        return default

    # 1. Symbol extraction & normalization
    raw_symbol = str(_get_val("ticker", "symbol", "pair", "instrument", default="EURUSD")).strip()
    if ":" in raw_symbol:
        # Strip exchange prefix: 'OANDA:EURUSD' -> 'EURUSD'
        raw_symbol = raw_symbol.split(":", 1)[1]
    symbol = raw_symbol.upper()

    # 2. Direction normalization
    raw_dir = str(_get_val("action", "order", "side", "signal", "direction", default="BUY")).strip().lower()
    if any(b in raw_dir for b in ["buy", "long"]):
        direction = "BUY"
    elif any(s in raw_dir for s in ["sell", "short"]):
        direction = "SELL"
    else:
        direction = "BUY"

    # 3. Volume normalization
    raw_vol = _get_val("volume", "contracts", "lots", "qty", "amount", "order_contracts", default=0.01)
    try:
        volume = float(raw_vol)
        if volume <= 0:
            volume = 0.01
    except (ValueError, TypeError):
        volume = 0.01

    # 4. Price normalization
    raw_price = _get_val("price", "entry_price", "close", default=None)
    price = None
    if raw_price is not None:
        try:
            price = float(raw_price)
        except (ValueError, TypeError):
            price = None

    # 5. Stop Loss & Take Profit
    raw_sl = _get_val("sl", "stop_loss", "stop", default=None)
    sl = None
    if raw_sl is not None:
        try:
            sl = float(raw_sl)
        except (ValueError, TypeError):
            sl = None

    raw_tp = _get_val("tp", "take_profit", "target", default=None)
    tp = None
    if raw_tp is not None:
        try:
            tp = float(raw_tp)
        except (ValueError, TypeError):
            tp = None

    # 6. Metadata
    strategy = str(_get_val("strategy", "strat", default="TradingView Alert")).strip()
    comment = str(_get_val("comment", "message", "msg", default=f"TV:{strategy}")).strip()
    passphrase = str(_get_val("passphrase", "secret", "token", "key", default="")).strip()

    now = time.time()
    event_id = f"tv_{symbol.lower()}_{int(now)}"

    return {
        "event_type": "trade_signal",
        "event_id": event_id,
        "source": "tradingview",
        "symbol": symbol,
        "direction": direction,
        "volume": volume,
        "price": price,
        "sl": sl,
        "tp": tp,
        "strategy": strategy,
        "comment": comment,
        "passphrase": passphrase,
        "timestamp": now,
        "raw_payload": data,
    }


_default_webhook_router: Optional[WebhookIngressRouter] = None


def get_webhook_router() -> WebhookIngressRouter:
    """Singleton getter for the global WebhookIngressRouter."""
    global _default_webhook_router
    if _default_webhook_router is None:
        _default_webhook_router = WebhookIngressRouter(enforce_signature=False, enforce_timestamp=False)
    return _default_webhook_router
