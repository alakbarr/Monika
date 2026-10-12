import pytest
from unittest.mock import AsyncMock, patch
from utils.llm.embedding import generate_gemini_embedding

@pytest.mark.asyncio
async def test_generate_gemini_embedding_empty():
    assert await generate_gemini_embedding("") is None
    assert await generate_gemini_embedding("   ") is None

@pytest.mark.asyncio
@patch("utils.llm.embedding.fetch_with_retry")
async def test_generate_gemini_embedding_success(mock_fetch):
    mock_fetch.return_value = {
        "embedding": {
            "values": [0.1, 0.2, -0.3, 0.4]
        }
    }
    vec = await generate_gemini_embedding(
        "EURUSD bullish breakout above 1.0850",
        api_key="mock_test_key"
    )
    assert vec is not None
    assert len(vec) == 4
    assert vec[0] == 0.1
    assert vec[2] == -0.3
    mock_fetch.assert_called_once()

@pytest.mark.asyncio
@patch("utils.llm.embedding.fetch_with_retry")
async def test_generate_gemini_embedding_api_error(mock_fetch):
    mock_fetch.return_value = {
        "error": {
            "code": 400,
            "message": "Invalid request"
        }
    }
    vec = await generate_gemini_embedding(
        "test query",
        api_key="mock_test_key"
    )
    assert vec is None

@pytest.mark.asyncio
@patch("utils.llm.embedding.fetch_with_retry")
async def test_generate_gemini_embedding_default_model_and_dimensions(mock_fetch):
    mock_fetch.return_value = {"embedding": {"values": [0.1] * 768}}
    vec = await generate_gemini_embedding("test prompt", api_key="test_key")
    assert vec is not None
    assert len(vec) == 768
    call_args = mock_fetch.call_args[1]
    assert "gemini-embedding-2" in call_args["url"]
    assert call_args["json"]["outputDimensionality"] == 768

@pytest.mark.asyncio
@patch("utils.llm.embedding.fetch_with_retry")
async def test_generate_gemini_embedding_legacy_migration(mock_fetch):
    mock_fetch.return_value = {"embedding": {"values": [0.5] * 768}}
    vec = await generate_gemini_embedding(
        "test prompt",
        model="text-embedding-004",
        api_key="test_key"
    )
    assert vec is not None
    call_args = mock_fetch.call_args[1]
    # text-embedding-004 must be migrated to gemini-embedding-2 to prevent HTTP 404
    assert "gemini-embedding-2" in call_args["url"]
    assert "text-embedding-004" not in call_args["url"]

@pytest.mark.asyncio
@patch("utils.llm.embedding.fetch_with_retry")
async def test_generate_gemini_embedding_preview_alias_migration(mock_fetch):
    mock_fetch.return_value = {"embedding": {"values": [0.3] * 768}}
    vec = await generate_gemini_embedding(
        "test prompt",
        model="gemini-embedding-2-preview",
        api_key="test_key"
    )
    assert vec is not None
    call_args = mock_fetch.call_args[1]
    assert "gemini-embedding-2" in call_args["url"]
    assert "gemini-embedding-2-preview" not in call_args["url"]
