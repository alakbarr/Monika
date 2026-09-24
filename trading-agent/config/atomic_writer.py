"""
Atomic YAML configuration writer with comment preservation, fsync, and automatic backups.
"""

import os
import re
import shutil
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

logger = logging.getLogger("TradingAgent.Config.AtomicWriter")

# Regexes to detect scalar strings that PyYAML / YAML 1.1 coerces into int/bool if unquoted:
# - Sexagesimal time strings: "15:00", "07:00", "20:00:00"
RE_SEXAGESIMAL = re.compile(r"^\d{1,2}:[0-5]\d(:[0-5]\d)?$")
# - Numeric strings with leading zeroes: "088691", "099741"
RE_LEADING_ZERO = re.compile(r"^0\d+$")
# - YAML 1.1 boolean/null keywords: "yes", "no", "y", "n", "on", "off", "true", "false", "null"
RE_YAML_SPECIAL = re.compile(r"^(y|n|yes|no|on|off|true|false|null)$", re.IGNORECASE)

try:
    from ruamel.yaml.scalarstring import SingleQuotedScalarString

    def _single_quote_representer(dumper, data):
        return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style="'")

    yaml.add_representer(SingleQuotedScalarString, _single_quote_representer)
    yaml.add_representer(SingleQuotedScalarString, _single_quote_representer, Dumper=yaml.SafeDumper)
except ImportError:
    pass


class AtomicConfigWriter:
    """Safely updates or writes YAML configuration files atomically without destroying comments."""

    DEFAULT_MAX_BACKUPS = 10

    @classmethod
    def _sanitize_scalars(cls, data: Any) -> Any:
        """
        Wraps scalar strings vulnerable to YAML 1.1 sexagesimal/octal coercion
        (such as '15:00' or '088691') into SingleQuotedScalarString.
        """
        try:
            from ruamel.yaml.scalarstring import SingleQuotedScalarString
        except ImportError:
            return data

        if isinstance(data, str):
            if RE_SEXAGESIMAL.match(data) or RE_LEADING_ZERO.match(data) or RE_YAML_SPECIAL.match(data):
                return SingleQuotedScalarString(data)
            return data
        elif isinstance(data, dict):
            return {k: cls._sanitize_scalars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls._sanitize_scalars(item) for item in data]
        return data

    @classmethod
    def _sync_dict_to_ruamel(cls, dest: Any, src: Dict[str, Any]) -> None:
        """Recursively synchronizes a dictionary into a ruamel.yaml CommentedMap while preserving comments."""
        if not hasattr(dest, "items"):
            return
        for k, v in src.items():
            if k in dest and isinstance(dest[k], dict) and isinstance(v, dict):
                cls._sync_dict_to_ruamel(dest[k], v)
            else:
                dest[k] = v
        for k in list(dest.keys()):
            if k not in src:
                del dest[k]

    @classmethod
    def backup(cls, path: Union[str, Path], max_backups: int = DEFAULT_MAX_BACKUPS) -> Optional[Path]:
        """Creates a timestamped backup of the target config file in a 'backups' subdirectory."""
        target = Path(path).resolve()
        if not target.exists():
            return None

        backup_dir = target.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{target.stem}_{timestamp}{target.suffix}"

        try:
            shutil.copy2(str(target), str(backup_path))
            logger.debug(f"Created config backup at {backup_path}")

            # Prune older backups beyond max_backups
            pattern = f"{target.stem}_*{target.suffix}"
            existing_backups = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
            if len(existing_backups) > max_backups:
                for old in existing_backups[:-max_backups]:
                    try:
                        old.unlink(missing_ok=True)
                    except OSError:
                        pass
            return backup_path
        except Exception as e:
            logger.warning(f"Failed to create config backup for {target}: {e}")
            return None

    @classmethod
    def write(
        cls,
        path: Union[str, Path],
        data: Dict[str, Any],
        *,
        create_backup: bool = True,
    ) -> Path:
        """
        Atomically writes full data dict to YAML path using temporary file and atomic replace.
        Prefers ruamel.yaml for comment preservation; falls back to standard pyyaml.
        If target file exists, synchronizes on existing round-trip AST to preserve comments.
        """
        target = Path(path).resolve()
        config_dir = target.parent
        config_dir.mkdir(parents=True, exist_ok=True)

        if create_backup and target.exists():
            cls.backup(target)

        # Try ruamel.yaml first
        ruamel_success = False
        temp_name = None
        try:
            from ruamel.yaml import YAML
            ryaml = YAML()
            ryaml.preserve_quotes = True

            sanitized_data = cls._sanitize_scalars(data)
            dump_data = sanitized_data

            if target.exists():
                try:
                    with open(target, "r", encoding="utf-8") as f:
                        doc = ryaml.load(f)
                    if isinstance(doc, dict):
                        cls._sync_dict_to_ruamel(doc, sanitized_data)
                        dump_data = doc
                except Exception as read_err:
                    logger.debug(f"Failed loading existing AST for comment preservation ({read_err})")

            with tempfile.NamedTemporaryFile("w", dir=str(config_dir), delete=False, encoding="utf-8") as tf:
                temp_name = tf.name
                ryaml.dump(dump_data, tf)
                tf.flush()
                os.fsync(tf.fileno())

            os.replace(temp_name, str(target))
            ruamel_success = True
        except Exception as r_err:
            logger.debug(f"ruamel.yaml atomic write failed ({r_err}), falling back to yaml.dump")
            if temp_name and os.path.exists(temp_name):
                try:
                    os.remove(temp_name)
                except OSError:
                    pass

        if not ruamel_success:
            fallback_temp = None
            try:
                with tempfile.NamedTemporaryFile("w", dir=str(config_dir), delete=False, encoding="utf-8") as tf:
                    fallback_temp = tf.name
                    yaml.dump(data, tf, default_flow_style=False, sort_keys=False, allow_unicode=True)
                    tf.flush()
                    os.fsync(tf.fileno())
                os.replace(fallback_temp, str(target))
            finally:
                if fallback_temp and os.path.exists(fallback_temp):
                    try:
                        os.remove(fallback_temp)
                    except OSError:
                        pass

        logger.info(f"Atomically wrote config to {target}")
        return target

    @classmethod
    def update_in_place(
        cls,
        path: Union[str, Path],
        update_dict: Dict[str, Any],
        *,
        create_backup: bool = True,
    ) -> Path:
        """
        Selectively merges update_dict into an existing YAML file while strictly preserving
        comments, formatting, and quotes via ruamel.yaml round-trip AST editing.
        """
        target = Path(path).resolve()
        config_dir = target.parent
        config_dir.mkdir(parents=True, exist_ok=True)

        if create_backup and target.exists():
            cls.backup(target)

        from ruamel.yaml import YAML
        ryaml = YAML()
        ryaml.preserve_quotes = True

        if target.exists():
            with open(target, "r", encoding="utf-8") as f:
                doc = ryaml.load(f) or {}
        else:
            doc = {}

        sanitized_update = cls._sanitize_scalars(update_dict)

        def _recursive_merge(dest: Any, src: Dict[str, Any]):
            for k, v in src.items():
                if isinstance(v, dict) and isinstance(dest.get(k), dict):
                    _recursive_merge(dest[k], v)
                else:
                    dest[k] = v

        _recursive_merge(doc, sanitized_update)

        temp_name = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=str(config_dir), delete=False, encoding="utf-8") as tf:
                temp_name = tf.name
                ryaml.dump(doc, tf)
                tf.flush()
                os.fsync(tf.fileno())
            os.replace(temp_name, str(target))
        finally:
            if temp_name and os.path.exists(temp_name):
                try:
                    os.remove(temp_name)
                except OSError:
                    pass

        logger.info(f"Atomically updated config in {target} (comments preserved)")
        return target
