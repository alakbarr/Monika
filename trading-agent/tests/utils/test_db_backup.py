# ==============================================================================
# File: tests/utils/test_db_backup.py
# ==============================================================================

import pytest
from unittest.mock import patch, AsyncMock
from pathlib import Path
from utils.infra.db_backup import create_backup


@pytest.mark.asyncio
async def test_create_backup_disabled():
    """Verify create_backup skips execution if disabled in settings."""
    settings = {"database": {"backup": {"enabled": False}}}
    result = await create_backup(settings)
    assert result.get("skipped") is True
    assert result.get("reason") == "backup_disabled"


@pytest.mark.asyncio
async def test_create_backup_missing_db_url(monkeypatch):
    """Verify error returned when DATABASE_URL is missing."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = {"database": {"backup": {"enabled": True}}}
    result = await create_backup(settings)
    assert "error" in result
    assert "DATABASE_URL not set" in result["error"]


@pytest.mark.asyncio
async def test_create_backup_success_with_safe_subprocess(monkeypatch, tmp_path):
    """Verify create_backup calls safe_subprocess_run and writes compressed sql.gz."""
    backup_dir = tmp_path / "backups"
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/tradingdb")
    settings = {
        "database": {
            "backup": {
                "enabled": True,
                "backup_dir": str(backup_dir),
                "keep_last_n": 3,
            }
        }
    }

    mock_sql_output = "CREATE TABLE test (id int);"
    with patch(
        "utils.infra.platform_compat.safe_subprocess_run",
        new_callable=AsyncMock,
        return_value=(0, mock_sql_output, ""),
    ) as mock_run:
        result = await create_backup(settings)

        assert result.get("success") is True
        assert "backup_file" in result
        mock_run.assert_awaited_once()

        # Verify created backup file exists and can be decompressed
        created_file = Path(result["backup_file"])
        assert created_file.exists()

        import gzip
        with gzip.open(created_file, "rt", encoding="utf-8") as f:
            decompressed = f.read()
        assert decompressed == mock_sql_output


@pytest.mark.asyncio
async def test_create_backup_subprocess_failure(monkeypatch, tmp_path):
    """Verify create_backup handles non-zero exit code from safe_subprocess_run."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/tradingdb")
    settings = {
        "database": {
            "backup": {
                "enabled": True,
                "backup_dir": str(tmp_path / "backups"),
            }
        }
    }
    with patch(
        "utils.infra.platform_compat.safe_subprocess_run",
        new_callable=AsyncMock,
        return_value=(1, "", "Connection refused"),
    ):
        result = await create_backup(settings)
        assert "error" in result
        assert "pg_dump failed" in result["error"]


@pytest.mark.asyncio
async def test_create_backup_timeout(monkeypatch, tmp_path):
    """Verify create_backup handles timeout in safe_subprocess_run."""
    import asyncio
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/tradingdb")
    settings = {
        "database": {
            "backup": {
                "enabled": True,
                "backup_dir": str(tmp_path / "backups"),
            }
        }
    }
    with patch(
        "utils.infra.platform_compat.safe_subprocess_run",
        new_callable=AsyncMock,
        side_effect=asyncio.TimeoutError("Timed out"),
    ):
        result = await create_backup(settings)
        assert "error" in result
        assert "timed out" in result["error"].lower()

