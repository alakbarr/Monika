import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from database.db import init_db, get_db, get_session, close_db

class TestDB:

    @pytest.mark.asyncio
    @patch('database.db.engine')
    @patch('database.db.Base')
    async def test_init_db_success(self, mock_base, mock_engine):
        mock_conn = AsyncMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_conn
        mock_engine.begin.return_value = mock_ctx
        
        await init_db()
        
        mock_engine.begin.assert_called_once()
        mock_conn.run_sync.assert_awaited_once_with(mock_base.metadata.create_all)

    @pytest.mark.asyncio
    @patch('database.db.engine')
    async def test_init_db_error(self, mock_engine):
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.side_effect = Exception("DB Init Error")
        mock_engine.begin.return_value = mock_ctx
        
        with pytest.raises(Exception, match="DB Init Error"):
            await init_db()

    @pytest.mark.asyncio
    @patch('database.db.AsyncSessionLocal')
    async def test_get_db(self, mock_sessionmaker):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_sessionmaker.return_value = mock_ctx
        
        gen = get_db()
        session = await anext(gen)
        
        assert session is mock_session
        
        with pytest.raises(StopAsyncIteration):
            await anext(gen)

    @pytest.mark.asyncio
    @patch('database.db.AsyncSessionLocal')
    async def test_get_session_success(self, mock_sessionmaker):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_sessionmaker.return_value = mock_ctx
        
        async with get_session() as session:
            assert session is mock_session

    @pytest.mark.asyncio
    @patch('database.db.AsyncSessionLocal')
    async def test_get_session_error(self, mock_sessionmaker):
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_session
        mock_sessionmaker.return_value = mock_ctx
        
        with pytest.raises(Exception, match="Test Error"):
            async with get_session() as session:
                raise Exception("Test Error")
                
        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    @patch('database.db.engine')
    async def test_close_db(self, mock_engine):
        mock_engine.dispose = AsyncMock()
        
        await close_db()
        
        mock_engine.dispose.assert_awaited_once()
