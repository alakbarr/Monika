"""
Unit tests for Monika Core Exception Taxonomy.
"""

from monika.core.exceptions import (
    AuthenticationError,
    BrokerConnectionError,
    CircuitBreakerOpenError,
    ConfigurationError,
    DataIngestionError,
    ExecutionError,
    KillSwitchActiveError,
    ModelInferenceError,
    MonikaError,
    RiskViolationError,
)


def test_monika_error_str_and_dict():
    err = MonikaError("Base error", code="ERR_BASE", details={"retry": False})
    assert str(err) == "[ERR_BASE] Base error | Details: {'retry': False}"

    d = err.to_dict()
    assert d["error"] == "MonikaError"
    assert d["code"] == "ERR_BASE"
    assert d["message"] == "Base error"
    assert d["details"] == {"retry": False}


def test_exception_inheritance_hierarchy():
    # Risk hierarchy
    risk_err = RiskViolationError("Risk breached", details={"drawdown": 0.06})
    assert isinstance(risk_err, MonikaError)

    kill_err = KillSwitchActiveError("Kill switch triggered")
    assert isinstance(kill_err, RiskViolationError)
    assert isinstance(kill_err, MonikaError)

    # Execution hierarchy
    exec_err = ExecutionError("Order failed")
    assert isinstance(exec_err, MonikaError)

    broker_err = BrokerConnectionError("MT5 disconnected")
    assert isinstance(broker_err, ExecutionError)
    assert isinstance(broker_err, MonikaError)

    # Operational errors
    assert isinstance(ConfigurationError("Invalid yaml"), MonikaError)
    assert isinstance(DataIngestionError("Scraper failed"), MonikaError)
    assert isinstance(ModelInferenceError("Groq 503"), MonikaError)
    assert isinstance(AuthenticationError("Invalid token"), MonikaError)
    assert isinstance(CircuitBreakerOpenError("Tripped"), MonikaError)
