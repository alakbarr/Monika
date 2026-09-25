# ==============================================================================
# File: utils/http_retry.py
# ==============================================================================

"""HTTP Request Wrapper dengan fitur retry otomatis dan exponential backoff."""
import asyncio
import logging
import os
import ssl
from typing import Optional, Callable, Any
import aiohttp

try:
    import certifi
    _DEFAULT_SSL_CONTEXT: Optional[ssl.SSLContext] = ssl.create_default_context(cafile=certifi.where())
    if "SSL_CERT_FILE" not in os.environ:
        os.environ["SSL_CERT_FILE"] = certifi.where()
except Exception:
    _DEFAULT_SSL_CONTEXT = ssl.create_default_context()

import time
import re
import json
import random
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

logger = logging.getLogger("TradingAgent.HTTPRetry")

def format_api_error_summary(status: int, body: str = "", url: str = "") -> str:
    """
    Extracts a clean, single-line error summary from API error response body.
    Eliminates messy multiline raw JSON dumps in logs and telemetry.
    """
    if not body:
        return f"HTTP {status}"
    
    # Try parsing JSON error from Gemini, OpenAI, Anthropic, OpenRouter, etc.
    try:
        data = json.loads(body) if isinstance(body, str) else body
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict):
                msg = err.get("message") or err.get("detail") or ""
                err_status = err.get("status") or err.get("type") or ""
                if err_status and msg:
                    return f"HTTP {status} ({err_status}): {msg.strip()}"
                elif msg:
                    return f"HTTP {status}: {msg.strip()}"
            elif isinstance(err, str):
                return f"HTTP {status}: {err.strip()}"
            
            if "detail" in data:
                return f"HTTP {status}: {str(data['detail']).strip()}"
            if "message" in data:
                return f"HTTP {status}: {str(data['message']).strip()}"
    except Exception:
        pass
    
    # Clean HTML or raw text to single line
    clean_body = re.sub(r"<[^>]+>", " ", str(body))
    clean_body = " ".join(clean_body.split())
    if len(clean_body) > 200:
        clean_body = clean_body[:200] + "..."
    return f"HTTP {status}: {clean_body}" if clean_body else f"HTTP {status}"


class APIStatusError(Exception):
    """Clean structured API status exception with formatted summary."""
    def __init__(self, status: int, message: str = "", body: str = "", retry_after: Optional[float] = None, url: str = "", status_name: str = ""):
        self.status = status
        self.status_code = status
        self.error_message = message
        self.body = body
        self.retry_after = retry_after
        self.url = url
        self.status_name = status_name
        
        summary = message or format_api_error_summary(status, body, url)
        super().__init__(summary)


class RateLimitError(APIStatusError):
    """Raised on rate limits (HTTP 429 / RESOURCE_EXHAUSTED)."""
    def __init__(self, message: str, body: str = "", retry_after: Optional[float] = None, status: int = 429):
        clean_msg = message
        if body and ("HTTP 429" in message or not message):
            clean_msg = format_api_error_summary(status, body)
        super().__init__(status=status, message=clean_msg, body=body, retry_after=retry_after)

_CIRCUIT_BREAKER: dict[str, float] = {}

def _jittered_delay(base_delay: float, attempt: int, max_delay: float = 60.0) -> float:
    """Exponential backoff with jitter (delay * (1 - random * 0.25))."""
    delay = min(base_delay * (2 ** attempt), max_delay)
    if delay <= 0:
        return 0.0
    return delay * (1.0 - random.random() * 0.25)

def _jitter_retry_after(retry_after: float) -> float:
    """Apply 10% jitter to Retry-After header value to prevent thundering herd."""
    if retry_after <= 0:
        return 0.0
    return retry_after * (1.0 - random.random() * 0.1)

def _sanitize_url(url: str) -> str:
    """Mask sensitive query parameter values in URL before logging."""
    try:
        parsed = urlparse(url)
        if not parsed.query:
            return url
        params = parse_qsl(parsed.query, keep_blank_values=True)
        masked_params = []
        for k, v in params:
            if any(s in k.lower() for s in ('key', 'token', 'secret', 'password', 'auth')):
                masked_params.append((k, '***'))
            else:
                masked_params.append((k, v))
        return urlunparse(parsed._replace(query=urlencode(masked_params)))
    except Exception:
        return url

async def fetch_with_retry(
    url: str,
    method: str = "GET",
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
    json: Optional[dict] = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: int = 30,
    raise_on_429: bool = False,
    use_circuit_breaker: bool = True,
    return_error_info: bool = False,
    response_type: str = "json",
    timeout_seconds: Optional[int] = None,
    ssl: Any = None,
    **kwargs,
) -> Any:
    """
    Eksekusi HTTP request dengan retry otomatis & exponential backoff.
    Jika return_error_info=True, return dict {_error: True, _status: int, _body: str} saat gagal.
    Returns: JSON dict, text string, atau None jika gagal.
    """
    effective_timeout = timeout_seconds if timeout_seconds is not None else (kwargs.get("timeout_sec") or timeout)
    timeout_obj = aiohttp.ClientTimeout(total=effective_timeout)
    effective_ssl = ssl if ssl is not None else kwargs.get("ssl", _DEFAULT_SSL_CONTEXT)
    domain = url.split('/')[2] if '//' in url else url
    safe_url = _sanitize_url(url)
    if use_circuit_breaker and domain in _CIRCUIT_BREAKER and time.time() < _CIRCUIT_BREAKER[domain]:
        logger.warning(f"Circuit breaker OPEN for {domain}, skipping {safe_url}")
        if return_error_info:
            return {"_error": True, "_status": 503, "_body": "Circuit breaker OPEN", "_url": safe_url}
        return None
    
    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession(timeout=timeout_obj) as http:
                async with http.request(method, url, params=params, headers=headers, json=json, ssl=effective_ssl) as resp:
                    raw_ra = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
                    parsed_retry_after: Optional[float] = None
                    if raw_ra:
                        try:
                            parsed_retry_after = float(raw_ra)
                        except (ValueError, TypeError):
                            parsed_retry_after = None

                    if resp.status == 429:  # Rate limited
                        body = await resp.text()
                        if raise_on_429:
                            if use_circuit_breaker:
                                _CIRCUIT_BREAKER[domain] = time.time() + 60.0
                            raise RateLimitError(
                                f"HTTP 429 Too Many Requests on {safe_url}",
                                body=body,
                                retry_after=parsed_retry_after,
                                status=429
                            )
                        wait = (_jitter_retry_after(parsed_retry_after) + 1.0) if parsed_retry_after is not None else (_jittered_delay(base_delay, attempt) + 5)
                        logger.warning(f"Rate limited on {safe_url}, waiting {wait:.1f}s")
                        await asyncio.sleep(wait)
                        continue
                    
                    if resp.status in (500, 502, 503, 504):  # Server errors
                        wait = (_jitter_retry_after(parsed_retry_after) + 1.0) if parsed_retry_after is not None else _jittered_delay(base_delay, attempt)
                        logger.warning(f"Server error {resp.status} on {safe_url}, retry in {wait:.1f}s")
                        await asyncio.sleep(wait)
                        continue
                    
                    if resp.status != 200:
                        body = await resp.text()
                        err_summary = format_api_error_summary(resp.status, body, safe_url)
                        logger.error(f"{err_summary} [url: {safe_url}]")
                        if return_error_info:
                            return {"_error": True, "_status": resp.status, "_body": body, "_url": safe_url}
                        return None
                    
                    if response_type == "text":
                        return await resp.text()
                    try:
                        return await resp.json()
                    except Exception:
                        return await resp.text()
                    
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            wait = _jittered_delay(base_delay, attempt)
            err_msg = str(e) if str(e).strip() else type(e).__name__
            err_msg = re.sub(r'(key|token|secret|password|auth)=([^\s&]+)', r'\1=***', err_msg, flags=re.IGNORECASE)
            err_msg = re.sub(r'sk-[a-zA-Z0-9_\-]+', 'sk-***', err_msg)
            logger.warning(f"Request failed (attempt {attempt+1}/{max_retries}): {err_msg}, retry in {wait:.1f}s")
            await asyncio.sleep(wait)
            
    logger.error(f"Failed to fetch {safe_url} after {max_retries} attempts")
    if use_circuit_breaker:
        _CIRCUIT_BREAKER[domain] = time.time() + 60.0
    if return_error_info:
        return {"_error": True, "_status": 0, "_body": "All retries exhausted", "_url": safe_url}
    return None
