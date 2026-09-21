import pytest
from analysis.providers.provider_failover_classifier import classify_error, FailoverReason


def test_classify_waf_and_cloudflare_blocked():
    err1 = Exception("403 Forbidden: Request blocked by Cloudflare WAF cf-ray 83921abc")
    reason1, detail1 = classify_error(err1)
    assert reason1 == FailoverReason.UPSTREAM_BLOCKED
    assert "WAF" in detail1 or "Cloudflare" in detail1
    assert reason1.can_failover(is_hot_path=True)


def test_classify_role_alternation_error():
    err = Exception("Invalid parameter: role alternation violation - consecutive user messages")
    reason, detail = classify_error(err)
    assert reason == FailoverReason.ROLE_ALTERNATION
    assert "consecutive" in detail


def test_classify_thinking_signature_error():
    err = Exception("Validation failed: missing or invalid thinking signature from model")
    reason, detail = classify_error(err)
    assert reason == FailoverReason.THINKING_SIGNATURE
    assert reason.can_failover(is_hot_path=True)


def test_classify_model_entitlement_error():
    err = Exception("AccessDeniedException: Account is not entitled to access model claude-3-opus")
    reason, detail = classify_error(err)
    assert reason == FailoverReason.MODEL_ENTITLEMENT
    assert reason.can_failover(is_hot_path=True)


def test_classify_image_multimodal_errors():
    err_large = Exception("BadRequestError: image too large, maximum image size is 5MB")
    reason_large, _ = classify_error(err_large)
    assert reason_large == FailoverReason.IMAGE_TOO_LARGE
    assert reason_large.should_compress is True

    err_corrupt = Exception("UnprocessableEntity: cannot decode image or unsupported image format")
    reason_corrupt, _ = classify_error(err_corrupt)
    assert reason_corrupt == FailoverReason.IMAGE_CORRUPT
    assert reason_corrupt.should_compress is False


def test_classify_completion_ceiling_exceeded():
    from analysis.providers.provider_failover_classifier import extract_completion_ceiling

    err = Exception("BadRequestError: max_tokens is too large: 32000 > 8192")
    reason, detail = classify_error(err)
    assert reason == FailoverReason.COMPLETION_CEILING_EXCEEDED
    assert reason.is_completion_ceiling is True
    assert reason.should_failover is False
    assert reason.max_retries == 1

    ceiling = extract_completion_ceiling(err)
    assert ceiling == 8192

    err2 = Exception("400 Invalid parameter: max_completion_tokens must be less than or equal to 4096")
    reason2, _ = classify_error(err2)
    assert reason2 == FailoverReason.COMPLETION_CEILING_EXCEEDED
    assert extract_completion_ceiling(err2) == 4096


def test_classify_hard_quota_exhausted():
    err = Exception("RateLimitError: 429 You exceeded your current quota, please check your plan and billing details")
    reason, detail = classify_error(err)
    assert reason == FailoverReason.HARD_QUOTA_EXHAUSTED
    assert reason.is_hard_quota_exhausted is True
    assert reason.should_failover is True
    assert reason.max_retries == 0


def test_classify_transient_rate_limit():
    err = Exception("429 Rate limit exceeded: requests per minute (RPM) limit reached for default tier")
    reason, detail = classify_error(err)
    assert reason == FailoverReason.TRANSIENT_RATE_LIMIT
    assert reason.should_failover is False
    assert reason.max_retries == 3


def test_resolve_effective_context_window_cascade():
    from analysis.providers.capabilities import resolve_effective_context_window

    # Tier 1: Proxy limit overrides everything
    assert resolve_effective_context_window("gemini-2.5-pro", proxy_limit=16384) == 16384

    # Tier 2: Settings overrides catalog/heuristics
    settings = {
        "llm": {
            "models": {
                "custom-trader-v1": {"context_window": 45000}
            },
            "providers": {
                "groq": {"context_window": 65536}
            }
        }
    }
    assert resolve_effective_context_window("custom-trader-v1", settings=settings) == 45000
    assert resolve_effective_context_window("unknown-groq-model", provider_name="groq", settings=settings) == 65536

    # Tier 3: ModelCapabilities table lookup
    assert resolve_effective_context_window("gemini-2.5-pro") == 1048576
    assert resolve_effective_context_window("claude-3-5-sonnet") == 200000

    # Tier 4: Provider heuristics
    assert resolve_effective_context_window("unregistered-groq-model", provider_name="groq") == 32768
    assert resolve_effective_context_window("unregistered-gemini-model", provider_name="gemini") == 1048576

    # Tier 5: Safe lower bound default
    assert resolve_effective_context_window("completely-unknown-model", provider_name="unknown") >= 32768


def test_extract_retry_after_headers_and_strings():
    from analysis.providers.base_provider import extract_retry_after

    # 1. Standard Retry-After header
    assert extract_retry_after({"headers": {"retry-after": "12.5"}}) == 12.5
    assert extract_retry_after({"headers": {"Retry-After": "45"}}) == 45.0

    # 2. Millisecond header
    assert extract_retry_after({"headers": {"retry-after-ms": "2500"}}) == 2.5

    # 3. String patterns in error message
    err_sec = Exception("Rate limit reached. Please retry after 18.0s.")
    assert extract_retry_after(err_sec) == 18.0

    err_ms = Exception("Too Many Requests: retry in 500ms")
    assert extract_retry_after(err_ms) == 0.5

    # 4. None / no match
    assert extract_retry_after(Exception("Generic server error 500")) is None


def test_endpoint_blackhole_lifecycle():
    from analysis.providers.llm_factory import EndpointBlackhole
    import time

    EndpointBlackhole.reset()
    assert not EndpointBlackhole.is_blackholed("ollama-local")

    # Blackhole for 1 second
    EndpointBlackhole.blackhole_endpoint("ollama-local", ttl_seconds=1.0)
    assert EndpointBlackhole.is_blackholed("ollama-local")

    # Sleep past TTL
    time.sleep(1.05)
    assert not EndpointBlackhole.is_blackholed("ollama-local")


