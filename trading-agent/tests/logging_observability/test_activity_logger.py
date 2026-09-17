import pytest
import logging
import os
from unittest.mock import AsyncMock, patch, MagicMock
from logging_observability.activity_logger import setup_logging, ActivityLogger, get_activity_logger, CATEGORIES

class TestActivityLogger:

    def test_setup_logging(self, tmpdir):
        log_dir = str(tmpdir.mkdir("logs"))
        logger = setup_logging(log_dir=log_dir, level=logging.DEBUG)
        
        assert logger.name == "TradingAgent"
        assert logger.level == logging.DEBUG
        assert len(logger.handlers) >= 3 # file, error_file, console
        
        # Test calling again returns same logger
        logger2 = setup_logging(log_dir=log_dir)
        assert logger2 is logger
        
        # Clean up handlers so it doesn't affect other tests
        logger.handlers.clear()

    def test_get_activity_logger(self):
        logger1 = get_activity_logger()
        logger2 = get_activity_logger()
        assert isinstance(logger1, ActivityLogger)
        assert logger1 is logger2

    @pytest.mark.asyncio
    @patch("database.db.get_session")
    async def test_log_success(self, mock_get_session):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        
        # Set up async context manager mock
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        
        def assign_id(entry):
            entry.id = 123
        
        mock_session.add.side_effect = assign_id
        
        logger = ActivityLogger()
        res = await logger.log("trading", "test message", related_id=1)
        
        assert res == 123
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("database.db.get_session")
    async def test_log_invalid_category(self, mock_get_session):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        
        logger = ActivityLogger()
        await logger.log("invalid_cat", "test message")
        
        # Should fallback to 'system'
        added_entry = mock_session.add.call_args[0][0]
        assert added_entry.category == "system"

    @pytest.mark.asyncio
    @patch("database.db.get_session")
    async def test_log_exception(self, mock_get_session):
        # Simulate DB exception
        mock_get_session.side_effect = Exception("DB Error")
        
        logger = ActivityLogger()
        res = await logger.log("trading", "test message")
        
        # Should catch exception and return None without crashing
        assert res is None

    @pytest.mark.asyncio
    async def test_category_shortcuts(self):
        logger = ActivityLogger()
        with patch.object(logger, "log", new_callable=AsyncMock) as mock_log:
            await logger.trading("test")
            mock_log.assert_called_with("trading", "test", None, "system", session=None)
            
            await logger.analysis("test")
            mock_log.assert_called_with("analysis", "test", None, "ai_agent", session=None)
            
            await logger.risk("test")
            mock_log.assert_called_with("risk", "test", None, "risk_gate", session=None)
            
            await logger.system("test")
            mock_log.assert_called_with("system", "test", None, "system", session=None)
            
            await logger.scraping("test")
            mock_log.assert_called_with("scraping", "test", None, "scraper", session=None)
            
            await logger.telegram("test")
            mock_log.assert_called_with("telegram", "test", None, "telegram", session=None)

    @pytest.mark.asyncio
    @patch("database.db.get_session")
    async def test_bulk(self, mock_get_session):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_get_session.return_value = mock_ctx
        
        logger = ActivityLogger()
        entries = [
            {"category": "trading", "description": "msg1"},
            {"category": "invalid", "description": "msg2"},
        ]
        
        res = await logger.bulk(entries)
        
        assert res == 2
        assert mock_session.add.call_count == 2
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bulk_empty(self):
        logger = ActivityLogger()
        res = await logger.bulk([])
        assert res == 0

    def test_third_party_logger_formatting_and_redaction(self, tmpdir):
        log_dir = str(tmpdir.mkdir("logs"))
        setup_logging(log_dir=log_dir, level=logging.INFO)

        httpx_logger = logging.getLogger("httpx")
        secret_token = "7871591922:AAENRd20agWx3AZqMVnvokzGgCDoZ192sVY"
        httpx_logger.info(f"HTTP Request: POST https://api.telegram.org/bot{secret_token}/getUpdates \"HTTP/1.1 200 OK\"")

        agent_log_path = os.path.join(log_dir, "agent.log")
        assert os.path.exists(agent_log_path)
        with open(agent_log_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert secret_token not in content
        assert "[REDACTED_TELEGRAM_TOKEN]" in content
        assert " | INFO     | httpx | HTTP Request: POST https://api.telegram.org/bot[REDACTED_TELEGRAM_TOKEN]/getUpdates" in content

        # Cleanup
        logging.getLogger("TradingAgent").handlers.clear()
        logging.getLogger().handlers.clear()

