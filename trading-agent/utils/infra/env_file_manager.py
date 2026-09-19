"""
Atomic .env file manager.
Safely reads and updates key-value pairs in environment configuration files
while preserving existing comments, whitespace, and ordering without corrupting formatting.
"""

import os
import re
import tempfile
import logging
from typing import Dict, Optional, List

logger = logging.getLogger("TradingAgent.Utils.EnvFileManager")


class EnvFileManager:
    """Atomic updater and validator for environment configuration files."""

    @staticmethod
    def get_default_env_path() -> str:
        """Returns the canonical root .env file path."""
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_dir, ".env")

    @classmethod
    def update_env_values(cls, updates: Dict[str, str], env_path: Optional[str] = None) -> bool:
        """
        Atomically updates or inserts key-value pairs into the target .env file.
        Preserves existing comments, blank lines, and line ordering.
        """
        target_path = env_path or cls.get_default_env_path()
        target_dir = os.path.dirname(os.path.abspath(target_path))
        os.makedirs(target_dir, exist_ok=True)

        lines: List[str] = []
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except Exception as e:
                logger.error(f"Failed to read existing env file {target_path}: {e}")
                return False

        remaining_updates = dict(updates)
        new_lines: List[str] = []
        key_pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=")

        for line in lines:
            match = key_pattern.match(line.strip())
            if match:
                key = match.group(1)
                if key in remaining_updates:
                    val = remaining_updates.pop(key)
                    # Quote value if it contains spaces or special characters
                    if any(c in val for c in (' ', '#', '"', "'", '\n')):
                        escaped_val = val.replace('"', '\\"')
                        new_lines.append(f'{key}="{escaped_val}"\n')
                    else:
                        new_lines.append(f"{key}={val}\n")
                    continue
            new_lines.append(line if line.endswith("\n") else f"{line}\n")

        # Append remaining keys at the end
        if remaining_updates:
            if new_lines and not new_lines[-1].strip() == "":
                new_lines.append("\n")
            new_lines.append("# Added by Setup Wizard\n")
            for key, val in remaining_updates.items():
                if any(c in val for c in (' ', '#', '"', "'", '\n')):
                    escaped_val = val.replace('"', '\\"')
                    new_lines.append(f'{key}="{escaped_val}"\n')
                else:
                    new_lines.append(f"{key}={val}\n")

        # Write to temporary file in same directory for atomic replace
        try:
            fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".env_tmp_", text=True)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            os.replace(tmp_path, target_path)
            logger.info(f"Successfully updated {len(updates)} key(s) in {target_path}")
            return True
        except Exception as e:
            logger.error(f"Atomic update failed for {target_path}: {e}")
            if 'tmp_path' in locals() and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            return False

    @classmethod
    def is_configured(cls, env_path: Optional[str] = None) -> bool:
        """
        Checks if essential runtime credentials are present.
        If env_path is explicitly passed, inspects that file.
        Otherwise checks os.environ and falls back to default .env path.
        """
        if env_path is None:
            # First check active process os.environ
            has_mt5 = bool(os.environ.get("MT5_ACCOUNT"))
            has_db = bool(os.environ.get("DATABASE_URL"))
            has_llm = any(bool(os.environ.get(k)) for k in [
                "GEMINI_API_KEY", "GEMINI_API_KEYS", "ANTHROPIC_API_KEY",
                "OPENAI_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY"
            ])
            if has_mt5 and has_db and has_llm:
                return True

        target_path = env_path or cls.get_default_env_path()
        if not os.path.exists(target_path):
            return False

        found_keys = set()
        try:
            key_pattern = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$")
            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = key_pattern.match(line.strip())
                    if m:
                        val = m.group(2).strip().strip('"').strip("'")
                        if val:
                            found_keys.add(m.group(1))
        except Exception:
            return False

        file_has_mt5 = "MT5_ACCOUNT" in found_keys
        file_has_db = "DATABASE_URL" in found_keys
        file_has_llm = any(k in found_keys for k in [
            "GEMINI_API_KEY", "GEMINI_API_KEYS", "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY", "GROQ_API_KEY", "DEEPSEEK_API_KEY"
        ])
        return file_has_mt5 and file_has_db and file_has_llm
