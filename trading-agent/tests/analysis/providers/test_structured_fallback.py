import pytest
from unittest.mock import AsyncMock, MagicMock
from analysis.providers.structured_fallback import (
    extract_and_parse_json,
    invoke_structured_or_freetext,
)


def test_extract_and_parse_json_markdown():
    text = "Here is the response:\n```json\n{\"sentiment\": \"bullish\", \"score\": 0.85}\n```\nHope that helps!"
    parsed = extract_and_parse_json(text)
    assert parsed == {"sentiment": "bullish", "score": 0.85}


def test_extract_and_parse_json_with_python_literals_and_trailing_commas():
    text = "Analysis output: {\"valid\": True, \"items\": [1, 2, None,],}"
    parsed = extract_and_parse_json(text)
    assert parsed == {"valid": True, "items": [1, 2, None]}


@pytest.mark.asyncio
async def test_invoke_structured_or_freetext_structured_success():
    client = MagicMock()
    client.classify_json = AsyncMock(return_value={"decision": "BUY", "confidence": 0.9})

    res = await invoke_structured_or_freetext(
        client, prompt="Analyze EURUSD", system_prompt="System instructions", schema={"type": "object"}
    )
    assert res == {"decision": "BUY", "confidence": 0.9}
    client.classify_json.assert_called_once()


@pytest.mark.asyncio
async def test_invoke_structured_or_freetext_fallback_to_freetext():
    client = MagicMock()
    client.classify_json = AsyncMock(side_effect=RuntimeError("Structured generation unsupported"))
    client.generate = AsyncMock(return_value="```json\n{\"decision\": \"SELL\", \"confidence\": 0.75}\n```")

    res = await invoke_structured_or_freetext(
        client, prompt="Analyze GBPUSD", system_prompt="System instructions", schema={"type": "object"}
    )
    assert res == {"decision": "SELL", "confidence": 0.75}
    client.generate.assert_called_once()
