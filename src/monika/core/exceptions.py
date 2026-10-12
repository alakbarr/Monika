"""
Core exception taxonomy for Monika quantitative trading platform.
Provides a unified, structured hierarchy for domain, infrastructure, and application errors.
"""

from typing import Any, Dict, Optional


class MonikaError(Exception):
    """Base exception for all domain and operational errors in Monika."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"[{self.code}] {self.message} | Details: {self.details}"
        return f"[{self.code}] {self.message}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to structured dict for API responses and telemetry logs."""
        return {
            "error": self.__class__.__name__,
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ConfigurationError(MonikaError):
    """Raised when configuration validation, parsing, or hot-reload fails."""
    pass


class RiskViolationError(MonikaError):
    """Raised when a proposed order or system state violates deterministic risk bounds."""
    pass


class KillSwitchActiveError(RiskViolationError):
    """Raised when an operation is blocked due to active emergency kill switch."""
    pass


class ExecutionError(MonikaError):
    """Raised when order submission, modification, or cancellation fails."""
    pass


class BrokerConnectionError(ExecutionError):
    """Raised when connection to broker socket (e.g. MT5, FIX) drops or fails."""
    pass


class DataIngestionError(MonikaError):
    """Raised when market data scrapers, feeds, or normalizers encounter fatal errors."""
    pass


class ModelInferenceError(MonikaError):
    """Raised when LLM providers, embedding models, or local time-series models fail."""
    pass


class AuthenticationError(MonikaError):
    """Raised when RBAC, API keys, or JWT tokens are invalid or expired."""
    pass


class CircuitBreakerOpenError(MonikaError):
    """Raised when a circuit breaker trips open to prevent cascading failures."""
    pass
