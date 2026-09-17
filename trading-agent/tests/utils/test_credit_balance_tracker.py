"""
Unit tests for CreditBalanceTracker.
Tests live credit fetching for OpenRouter & DeepSeek, daily quota calculation, and monthly expenses.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from utils.api.credit_balance_tracker import CreditBalanceTracker


@pytest.mark.asyncio
async def test_fetch_openrouter_credits_success():
    """Memverifikasi parsing response /api/v1/credits dan /api/v1/key OpenRouter."""
    mock_credits_resp = AsyncMock()
    mock_credits_resp.status = 200
    mock_credits_resp.json.return_value = {
        "data": {
            "total_credits": 50.0,
            "total_usage": 15.5
        }
    }

    mock_key_resp = AsyncMock()
    mock_key_resp.status = 200
    mock_key_resp.json.return_value = {
        "data": {
            "limit": 100.0,
            "usage": 15.5,
            "is_free_tier": False,
            "rate_limit": {"requests": 50, "interval": "10s"}
        }
    }

    class MockSessionContext:
        async def __aenter__(self):
            session = MagicMock()
            session.get = MagicMock(side_effect=[
                AsyncContextManager(mock_credits_resp),  # paid key /credits
                AsyncContextManager(mock_key_resp),      # free key 1 /key
                AsyncContextManager(mock_key_resp),      # free key 2 /key
            ])
            return session

        async def __aexit__(self, *args):
            pass

    class AsyncContextManager:
        def __init__(self, response):
            self.response = response
        async def __aenter__(self):
            return self.response
        async def __aexit__(self, *args):
            pass

    with patch('aiohttp.ClientSession', return_value=MockSessionContext()), \
         patch.dict('os.environ', {'OPENROUTER_PAID_API_KEY': 'sk-or-paid', 'OPENROUTER_API_KEYS': 'sk-or-free-1,sk-or-free-2'}):
        res = await CreditBalanceTracker.fetch_openrouter_credits()
        assert res["status"] == "ok"
        assert res["total_credits_usd"] == 50.0
        assert res["total_usage_usd"] == 15.5
        assert res["remaining_usd"] == 34.5
        assert res["paid_key"]["status"] == "ok"
        assert res["paid_key"]["remaining_usd"] == 34.5
        assert res["free_keys"]["configured_count"] == 2
        assert res["free_keys"]["active_count"] == 2


@pytest.mark.asyncio
async def test_fetch_deepseek_balance_success():
    """Memverifikasi parsing response /user/balance DeepSeek."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json.return_value = {
        "is_available": True,
        "balance_infos": [
            {
                "currency": "USD",
                "total_balance": "10.00",
                "granted_balance": "2.00",
                "topped_up_balance": "8.00"
            }
        ]
    }

    class MockSessionContext:
        async def __aenter__(self):
            session = MagicMock()
            session.get = MagicMock(return_value=AsyncContextManager(mock_resp))
            return session
        async def __aexit__(self, *args):
            pass

    class AsyncContextManager:
        def __init__(self, response):
            self.response = response
        async def __aenter__(self):
            return self.response
        async def __aexit__(self, *args):
            pass

    with patch('aiohttp.ClientSession', return_value=MockSessionContext()):
        res = await CreditBalanceTracker.fetch_deepseek_balance(api_key="sk-ds-test-key")
        assert res["status"] == "ok"
        assert res["is_available"] is True
        assert res["total_balance_usd"] == 10.0
        assert res["topped_up_balance_usd"] == 8.0
        assert res["granted_balance_usd"] == 2.0


@pytest.mark.asyncio
async def test_unconfigured_keys():
    """Memverifikasi penanganan API key yang kosong / unconfigured."""
    with patch.dict('os.environ', {'OPENROUTER_PAID_API_KEY': '', 'OPENROUTER_API_KEY': '', 'OPENROUTER_API_KEYS': '', 'DEEPSEEK_API_KEY': ''}, clear=True):
        or_res = await CreditBalanceTracker.fetch_openrouter_credits()
        assert or_res["status"] == "unconfigured"

        ds_res = await CreditBalanceTracker.fetch_deepseek_balance()
        assert ds_res["status"] == "unconfigured"


@pytest.mark.asyncio
async def test_daily_quota_and_monthly_expense_summary():
    """Memverifikasi kalkulasi kuota harian dan pengeluaran bulan berjalan dari DB."""
    mock_session = AsyncMock()
    
    # Mock daily quota query
    mock_quota_row1 = MagicMock(provider="gemini", model_name="gemini-3.7-flash", call_count=4, sum_tokens=25000)
    mock_quota_row2 = MagicMock(provider="gemini", model_name="gemini-3.5-flash-lite", call_count=80, sum_tokens=120000)
    mock_exec_result_quota = MagicMock()
    mock_exec_result_quota.all.return_value = [mock_quota_row1, mock_quota_row2]
    mock_session.execute = AsyncMock(return_value=mock_exec_result_quota)

    quotas = await CreditBalanceTracker.get_daily_quota_summary(session=mock_session)
    assert "gemini-3.7-flash" in quotas
    assert quotas["gemini-3.7-flash"]["used_calls"] == 4
    assert quotas["gemini-3.7-flash"]["remaining_calls"] == 16  # 20 - 4
    assert quotas["gemini-3.5-flash-lite"]["used_calls"] == 80
    assert quotas["gemini-3.5-flash-lite"]["remaining_calls"] == 420  # 500 - 80

    # Mock monthly expense query
    mock_exp_row1 = MagicMock(provider="anthropic", total_calls=150, total_tokens=500000, cached_tokens=50000, total_cost=3.25)
    mock_exp_row2 = MagicMock(provider="openai", total_calls=40, total_tokens=100000, cached_tokens=10000, total_cost=0.50)
    mock_exec_result_exp = MagicMock()
    mock_exec_result_exp.all.return_value = [mock_exp_row1, mock_exp_row2]
    mock_session.execute = AsyncMock(return_value=mock_exec_result_exp)

    expenses = await CreditBalanceTracker.get_monthly_expense_summary(session=mock_session)
    assert expenses["total_month_usd"] == 3.75
    assert expenses["total_month_calls"] == 190
    assert "anthropic" in expenses["by_provider"]
    assert expenses["by_provider"]["anthropic"]["cost_usd"] == 3.25
