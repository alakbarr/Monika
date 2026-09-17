# ==============================================================================
# File: utils/infra/log_redactor.py
# ==============================================================================

"""
Log Redaction Utility (H7).
Strips API keys, tokens, passwords, and sensitive URLs from log strings.
"""

import re
import logging
from typing import List, Tuple, Any

# Pre-compiled redaction patterns
REDACTION_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Anthropic API Key
    (re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}"), "[REDACTED_ANTHROPIC_KEY]"),
    # OpenAI API Key
    (re.compile(r"sk-[a-zA-Z0-9_\-]{24,}"), "[REDACTED_OPENAI_KEY]"),
    # Google AI / Gemini API Key
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "[REDACTED_GEMINI_KEY]"),
    # Telegram Bot Token (standalone or in https://api.telegram.org/bot<token> URLs)
    (re.compile(r"(?:(?<=bot)|\b)[0-9]{8,10}:[a-zA-Z0-9_\-]{35}\b"), "[REDACTED_TELEGRAM_TOKEN]"),
    # Authorization: Bearer
    (re.compile(r"(?i)\bBearer\s+[a-zA-Z0-9_\-\.]{20,}\b"), "Bearer [REDACTED_BEARER_TOKEN]"),
    # Database URI password: postgresql://user:password@host
    (re.compile(r"(://[^:\s]+):([^@\s]+)@"), r"\1:[REDACTED_PASSWORD]@"),
    # Generic credential assignment in text/JSON
    (
        re.compile(
            r"""(?i)(["']?(?:password|passwd|secret|api_key|token|access_token|client_secret)["']?\s*[:=]\s*["'])([^"'\r\n]+)(["'])"""
        ),
        r"\1[REDACTED]\3",
    ),
]


def redact_sensitive_text(text: str) -> str:
    """Sanitize string by masking known secret patterns."""
    if not isinstance(text, str):
        return text
    sanitized = text
    for pattern, replacement in REDACTION_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


class RedactingFormatter(logging.Formatter):
    """Logging formatter that redacts sensitive credentials from rendered records."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        return redact_sensitive_text(original)
