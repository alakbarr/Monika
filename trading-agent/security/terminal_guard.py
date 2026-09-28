# ==============================================================================
# File: security/terminal_guard.py
# ==============================================================================

"""
Production Terminal & Host Execution Safety Guard.
Enforces hardline blocklists, quote-unwrapping evaluation, filesystem write roots,
and consecutive denial circuit breakers to protect host machines from malicious
or accidental destructive execution.
"""

import os
import re
import shlex
from pathlib import Path
from typing import List, Optional, Set, Tuple

from utils.security.nt_guard import is_dangerous_nt_namespace, SecurityViolationError

# Hardline command patterns that MUST NEVER execute under any mode or posture
HARDLINE_BLOCKLIST_PATTERNS = [
    # System destruction & formatting
    re.compile(r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f*|-f*r[a-zA-Z]*)\s+(?:/|/etc|/usr|/bin|/var|~|\$HOME|\*)(?:/|\*|\s|$|;)", re.IGNORECASE),
    re.compile(r"\b(del|erase|rd|rmdir)\s+.*(/s|/q).*(\\|C:\\|C:/)(?:\s|$|;)", re.IGNORECASE),
    re.compile(r"\b(mkfs|format)\b", re.IGNORECASE),
    re.compile(r"\bdd\s+.*of=(/dev/|\\\\.\b)", re.IGNORECASE),
    
    # Forkbomb & Process Sabotage
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:", re.IGNORECASE),
    re.compile(r"\bkill\s+-9\s+-1\b", re.IGNORECASE),
    re.compile(r"\b(shutdown|reboot|poweroff|halt)\b", re.IGNORECASE),
    re.compile(r"\b(Stop-Computer|Restart-Computer)\b", re.IGNORECASE),
    re.compile(r"\btaskkill\s+.*(/f|/im\s+python\.exe|/im\s+terminal64\.exe)\b", re.IGNORECASE),
    
    # Sudo stdin password injection
    re.compile(r"echo\s+.*\|\s*sudo\s+-S\b", re.IGNORECASE),
    
    # Direct access to shadow/credentials
    re.compile(r"\b(cat|type|more|less|head|tail)\s+.*(/etc/shadow|/etc/passwd|\.ssh/id_|\.env)\b", re.IGNORECASE),
    
    # Cloud Instance Metadata Service (IMDS) SSRF Protection
    re.compile(r"(?:169\.254\.169\.254|169\.254\.170\.2|metadata\.google\.internal|100\.100\.100\.200|fd00:ec2::254)", re.IGNORECASE),
    
    # Reverse shell & socket pipes
    re.compile(r"/dev/(?:tcp|udp)/\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", re.IGNORECASE),
    re.compile(r"\bnc(?:\.traditional)?\s+-[a-zA-Z]*e\b|\bncat\s+.*--exec\b", re.IGNORECASE),
    re.compile(r"\b(?:base64\s+-d|openssl\s+enc\s+-d)\s*\|\s*(?:bash|sh|zsh|powershell|pwsh)\b", re.IGNORECASE),
    re.compile(r"\b(?:Invoke-Expression|iex)\s*[\(\$].*(?:DownloadString|FromBase64String|webclient)", re.IGNORECASE),
]

# Sensitive file and directory names that agent is forbidden from writing or deleting
PROTECTED_TARGETS: Set[str] = {
    ".env",
    ".env.example",
    "id_rsa",
    "id_ed25519",
    ".git-credentials",
    ".netrc",
    ".pgpass",
    "authorized_keys",
    "known_hosts",
    "AIAgent_EA.mq5",  # Protected MQL5 EA source code
}

PROTECTED_DIRECTORIES: Set[str] = {
    ".ssh",
    ".aws",
    ".gnupg",
    ".kube",
    ".docker",
    "system32",
    "/etc",
    "/usr",
}


def deobfuscate_command(cmd_line: str) -> str:
    """
    De-obfuscates command line strings to defeat evasion techniques such as:
    - Intra-token quote concatenation (e.g. c'a't /e"t"c/p'a'sswd)
    - PowerShell backtick masking (e.g. c`a`t)
    - Hex escaped strings (e.g. \\x63\\x61\\x74)
    - Substring concatenation expressions
    """
    if not cmd_line:
        return ""

    result = cmd_line

    # 1. Remove PowerShell backtick evasion (e.g. `c`a`t -> cat)
    result = re.sub(r"`([a-zA-Z0-9_\-\.\/])", r"\1", result)

    # 2. De-obfuscate intra-token quotes (e.g. c'a't -> cat, /e"t"c -> /etc, r""m -> rm)
    result = re.sub(r"(?<=[a-zA-Z0-9_\-\.\/\$])['\"]+(?=[a-zA-Z0-9_\-\.\/\$])", "", result)
    result = re.sub(r"(^|\s)['\"]([a-zA-Z0-9_\-\.\/]+)['\"](?=\s|$)", lambda m: (m.group(1) or "") + m.group(2), result)

    # 3. Decode hex escape sequences (\x41 -> A)
    def _decode_hex(match: re.Match) -> str:
        try:
            return bytes.fromhex(match.group(1)).decode("latin1")
        except Exception:
            return match.group(0)

    result = re.sub(r"\\x([0-9a-fA-F]{2})", _decode_hex, result)

    # 4. Remove quote concatenations (e.g. 'c'+'a'+'t' -> cat)
    result = re.sub(r"['\"]\s*\+\s*['\"]", "", result)

    return result.strip()


def unwrap_command_quotes(cmd_line: str) -> str:
    """
    Unwrap nested quotes and execution wrappers (e.g. sh -c '...', bash -c '...', powershell -Command '...')
    to analyze the payload string inside.
    """
    cleaned = cmd_line.strip()
    # Check for execution wrappers like: bash -c "...", sh -c "...", powershell -Command "..."
    wrapper_match = re.search(
        r"(?:bash|sh|zsh|cmd|powershell|pwsh)(?:\.exe)?\s+(?:-c|-Command|/c)\s+['\"](.*)['\"]",
        cleaned,
        re.IGNORECASE,
    )
    if wrapper_match:
        return wrapper_match.group(1).strip()
    return cleaned


def is_hardline_blocked_command(cmd_line: str) -> Tuple[bool, str]:
    """
    Evaluate command line string against hardline blocklist.
    Checks raw command, unwrapped command, and de-obfuscated representations.
    Returns (is_blocked: bool, reason: str).
    """
    if not cmd_line or not cmd_line.strip():
        return False, ""

    unwrapped = unwrap_command_quotes(cmd_line)
    deobfuscated = deobfuscate_command(cmd_line)
    deobfuscated_unwrapped = deobfuscate_command(unwrapped)

    candidates = [cmd_line, unwrapped, deobfuscated, deobfuscated_unwrapped]

    for pattern in HARDLINE_BLOCKLIST_PATTERNS:
        for candidate in candidates:
            if pattern.search(candidate):
                return True, f"Command matched prohibited security signature: '{pattern.pattern}'."

    return False, ""


def assert_safe_write_path(target_path: str, safe_root: Optional[str] = None) -> str:
    """
    Ensure the target write path is inside MONIKA_WRITE_SAFE_ROOT and does not target
    protected credentials or system files.
    """
    if is_dangerous_nt_namespace(target_path):
        raise SecurityViolationError(f"Rejected NT-namespace path: {target_path}")

    # Resolve safe root from argument or environment variable
    root_env = safe_root or os.environ.get("MONIKA_WRITE_SAFE_ROOT")
    if not root_env:
        # Default safe root is the repository root
        root_path = Path(__file__).resolve().parent.parent.parent
        allow_temp = True
    else:
        root_path = Path(root_env).resolve()
        allow_temp = False

    target = Path(target_path).resolve()
    import tempfile
    temp_dir = Path(tempfile.gettempdir()).resolve()

    # 1. Check if inside safe root or temp dir
    is_safe = False
    try:
        target.relative_to(root_path)
        is_safe = True
    except ValueError:
        pass

    if not is_safe and allow_temp:
        try:
            target.relative_to(temp_dir)
            is_safe = True
        except ValueError:
            pass

    if not is_safe:
        raise SecurityViolationError(
            f"Path traversal blocked: '{target_path}' is outside designated safe root '{root_path}'."
        )

    # 2. Check protected file names
    base_name = target.name.lower()
    if base_name in {p.lower() for p in PROTECTED_TARGETS}:
        raise SecurityViolationError(f"Access denied: Target '{target.name}' is a protected system asset.")

    # 3. Check protected directories in path parts
    for part in target.parts:
        if part.lower() in {d.lower() for d in PROTECTED_DIRECTORIES}:
            raise SecurityViolationError(f"Access denied: Target resides in protected directory '{part}'.")

    return str(target)


class DenialCircuitBreaker:
    """
    Tracks consecutive security and execution rejections.
    Trips hard-stop after threshold consecutive rejections to prevent prompt injection loops.
    """

    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self._consecutive_denials: int = 0
        self._is_tripped: bool = False
        self._trip_reason: str = ""

    @property
    def is_tripped(self) -> bool:
        return self._is_tripped

    @property
    def trip_reason(self) -> str:
        return self._trip_reason

    def record_success(self) -> None:
        """Reset tally on successful allowed execution."""
        if not self._is_tripped:
            self._consecutive_denials = 0

    def record_denial(self, reason: str) -> bool:
        """
        Record a rejection. If count reaches threshold, trips circuit breaker.
        Returns True if tripped.
        """
        self._consecutive_denials += 1
        if self._consecutive_denials >= self.threshold:
            self._is_tripped = True
            self._trip_reason = f"Security Circuit Breaker Tripped: {self._consecutive_denials} consecutive violations. Last: {reason}"
            return True
        return False

    def reset(self) -> None:
        """Manual operator reset."""
        self._consecutive_denials = 0
        self._is_tripped = False
        self._trip_reason = ""


class CommandSecurityViolationError(SecurityViolationError):
    """Raised when command execution violates terminal security policy."""
    pass


def validate_command(cmd_line: str) -> None:
    """Validate command line string against hardline blocklist. Raises if blocked."""
    blocked, reason = is_hardline_blocked_command(cmd_line)
    if blocked:
        raise CommandSecurityViolationError(reason)
