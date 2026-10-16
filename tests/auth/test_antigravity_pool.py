# ==============================================================================
# File: tests/auth/test_antigravity_pool.py
# ==============================================================================

"""
Comprehensive tests for Antigravity Multi-Account OAuth Pool:
- Multi-account CRUD in oauth_store
- Tier-based routing (Paid for Argon/Pro, Free round-robin for Flash)
- Automatic rotation & cooldown tracking
- GeminiProvider tier integration
- CLI status and logout commands
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from monika.infrastructure.auth.antigravity_bridge import (
    get_antigravity_pool_summary,
    mark_antigravity_account_cooldown,
    resolve_antigravity_access_token,
)
from monika.infrastructure.auth.oauth_store import (
    clear_oauth_accounts,
    delete_oauth_account,
    get_oauth_accounts,
    save_oauth_account,
)
from monika.interfaces.cli.commands.auth_ctrl import logout_provider, show_auth_status


@pytest.fixture
def mock_vault():
    """Isolated in-memory vault for testing without touching OS keyring or disk."""
    store = {}
    with patch("monika.infrastructure.auth.oauth_store.vault") as v:
        v.get_secret.side_effect = lambda k, *args, **kwargs: store.get(k)
        v.set_secret.side_effect = lambda k, val, *args, **kwargs: store.update({k: val}) or True
        v.delete_secret.side_effect = lambda k, *args, **kwargs: bool(store.pop(k, None))
        yield store


@pytest.fixture(autouse=True)
def reset_antigravity_state():
    """Ensure in-memory cooldown dict is isolated and reset for each test."""
    from monika.infrastructure.auth.antigravity_bridge import _antigravity_account_cooldowns

    _antigravity_account_cooldowns.clear()
    yield
    _antigravity_account_cooldowns.clear()


def test_oauth_store_multi_account_crud(mock_vault):
    """Verify save, get, update, delete, and clear for multi-account pool."""
    paid_acc = {
        "email": "primary.paid@gmail.com",
        "access_token": "ya29.paid_tok_1",
        "refresh_token": "1//paid_ref",
        "expires_at": time.time() + 3600,
        "tier": "paid",
    }
    free_acc_1 = {
        "email": "free1@gmail.com",
        "access_token": "ya29.free_tok_1",
        "refresh_token": "1//free_ref_1",
        "expires_at": time.time() + 3600,
        "tier": "free",
    }
    free_acc_2 = {
        "email": "free2@gmail.com",
        "access_token": "ya29.free_tok_2",
        "refresh_token": "1//free_ref_2",
        "expires_at": time.time() + 3600,
        "tier": "free",
    }

    # 1. Save 3 accounts
    assert save_oauth_account("antigravity", paid_acc) is True
    assert save_oauth_account("antigravity", free_acc_1) is True
    assert save_oauth_account("antigravity", free_acc_2) is True

    # 2. Retrieve pool
    accounts = get_oauth_accounts("antigravity")
    assert len(accounts) == 3
    emails = [a["email"] for a in accounts]
    assert "primary.paid@gmail.com" in emails
    assert "free1@gmail.com" in emails
    assert "free2@gmail.com" in emails

    # 3. Update existing account
    updated_free_1 = dict(free_acc_1)
    updated_free_1["access_token"] = "ya29.free_tok_1_updated"
    assert save_oauth_account("antigravity", updated_free_1) is True

    accounts = get_oauth_accounts("antigravity")
    assert len(accounts) == 3
    f1 = next(a for a in accounts if a["email"] == "free1@gmail.com")
    assert f1["access_token"] == "ya29.free_tok_1_updated"

    # 4. Delete one account
    assert delete_oauth_account("antigravity", "free1@gmail.com") is True
    accounts = get_oauth_accounts("antigravity")
    assert len(accounts) == 2
    assert "free1@gmail.com" not in [a["email"] for a in accounts]

    # 5. Clear all accounts
    assert clear_oauth_accounts("antigravity") is True
    assert len(get_oauth_accounts("antigravity")) == 0


def test_antigravity_pool_tier_routing_and_round_robin(mock_vault):
    """Verify tier routing: Paid for Argon/Pro, and round-robin across Free accounts for Flash."""
    paid_acc = {
        "email": "paid@gmail.com",
        "access_token": "ya29.paid_tok",
        "refresh_token": "1//paid_ref",
        "expires_at": time.time() + 3600,
        "tier": "paid",
    }
    free_acc_1 = {
        "email": "free1@gmail.com",
        "access_token": "ya29.free_tok_1",
        "refresh_token": "1//free_ref_1",
        "expires_at": time.time() + 3600,
        "tier": "free",
    }
    free_acc_2 = {
        "email": "free2@gmail.com",
        "access_token": "ya29.free_tok_2",
        "refresh_token": "1//free_ref_2",
        "expires_at": time.time() + 3600,
        "tier": "free",
    }
    save_oauth_account("antigravity", paid_acc)
    save_oauth_account("antigravity", free_acc_1)
    save_oauth_account("antigravity", free_acc_2)

    # Argon / Pro -> Paid token
    assert resolve_antigravity_access_token(tier="paid") == "ya29.paid_tok"
    assert resolve_antigravity_access_token(model="gemini-4-argon") == "ya29.paid_tok"
    assert resolve_antigravity_access_token(model="gemini-pro") == "ya29.paid_tok"

    # Flash -> Round-robin across free accounts
    tok_a = resolve_antigravity_access_token(model="gemini-3.8-flash")
    tok_b = resolve_antigravity_access_token(model="gemini-3.8-flash")
    tok_c = resolve_antigravity_access_token(model="gemini-3.8-flash")

    # Tokens must rotate between the two free accounts
    assert tok_a in ("ya29.free_tok_1", "ya29.free_tok_2")
    assert tok_b in ("ya29.free_tok_1", "ya29.free_tok_2")
    assert tok_a != tok_b
    assert tok_c == tok_a


def test_antigravity_pool_cooldown_and_fallback(mock_vault):
    """Verify that cooled-down accounts are skipped and pool falls back safely."""
    paid_acc = {
        "email": "paid@gmail.com",
        "access_token": "ya29.paid_tok",
        "expires_at": time.time() + 3600,
        "tier": "paid",
    }
    free_acc_1 = {
        "email": "free1@gmail.com",
        "access_token": "ya29.free_tok_1",
        "expires_at": time.time() + 3600,
        "tier": "free",
    }
    free_acc_2 = {
        "email": "free2@gmail.com",
        "access_token": "ya29.free_tok_2",
        "expires_at": time.time() + 3600,
        "tier": "free",
    }
    save_oauth_account("antigravity", paid_acc)
    save_oauth_account("antigravity", free_acc_1)
    save_oauth_account("antigravity", free_acc_2)

    # Put free1 in cooldown
    mark_antigravity_account_cooldown("free1@gmail.com", duration_seconds=60.0)

    # Free requests must now only return free2
    for _ in range(3):
        assert resolve_antigravity_access_token(tier="free") == "ya29.free_tok_2"

    # Put free2 in cooldown as well
    mark_antigravity_account_cooldown("free2@gmail.com", duration_seconds=60.0)

    # When all free accounts are cooled down, Flash should fall back to paid account
    assert resolve_antigravity_access_token(tier="free") == "ya29.paid_tok"

    # Put paid in cooldown too
    mark_antigravity_account_cooldown("paid@gmail.com", duration_seconds=60.0)

    # Now all accounts in pool are in cooldown -> returns None
    assert resolve_antigravity_access_token(tier="free") is None
    assert resolve_antigravity_access_token(tier="paid") is None


def test_antigravity_pool_summary(mock_vault):
    """Verify pool summary counts and cooldown status."""
    paid_acc = {
        "email": "paid@gmail.com",
        "access_token": "ya29.paid",
        "tier": "paid",
        "expires_at": time.time() + 3600,
    }
    free_acc = {
        "email": "free@gmail.com",
        "access_token": "ya29.free",
        "tier": "free",
        "expires_at": time.time() + 3600,
    }
    save_oauth_account("antigravity", paid_acc)
    save_oauth_account("antigravity", free_acc)

    summary = get_antigravity_pool_summary()
    assert summary["total_accounts"] == 2
    assert summary["paid_accounts"] == 1
    assert summary["free_accounts"] == 1
    assert summary["cooldown_accounts"] == 0
    assert summary["active_accounts"] == 2

    # Put free in cooldown
    mark_antigravity_account_cooldown("free@gmail.com", 120.0)
    summary_after = get_antigravity_pool_summary()
    assert summary_after["cooldown_accounts"] == 1
    assert summary_after["active_accounts"] == 1


def test_gemini_provider_tier_routing():
    """Verify GeminiProvider calls resolve_antigravity_access_token with appropriate tier."""
    from monika.infrastructure.providers.gemini_provider import GeminiProvider

    provider_argon = GeminiProvider(model="gemini-4-argon", api_key="")

    with patch("monika.infrastructure.auth.antigravity_bridge.resolve_antigravity_access_token") as mock_resolve:
        mock_resolve.return_value = "ya29.resolved_paid_tok"
        key = provider_argon._get_api_key()
        mock_resolve.assert_called_with(tier="paid", model="gemini-4-argon")
        assert key == "ya29.resolved_paid_tok"

    provider_flash = GeminiProvider(model="gemini-3.8-flash", api_key="")
    provider_flash.free_api_keys = []
    with patch("monika.infrastructure.auth.antigravity_bridge.resolve_antigravity_access_token") as mock_resolve:
        mock_resolve.return_value = "ya29.resolved_free_tok"
        key = provider_flash._get_api_key()
        mock_resolve.assert_called_with(tier="free", model="gemini-3.8-flash")
        assert key == "ya29.resolved_free_tok"


def test_gemini_provider_oauth_cooldown():
    """Verify that a 429 response on an OAuth Bearer token triggers account cooldown."""
    from monika.infrastructure.providers.gemini_provider import GeminiProvider

    provider = GeminiProvider(model="gemini-2.5-flash", api_key="AIzaSyDummyKey")

    with patch("monika.infrastructure.auth.antigravity_bridge.mark_antigravity_account_cooldown") as mock_mark_cooldown:
        provider._handle_rate_limit_error("ya29.rate_limited_token", Exception("HTTP 429: Resource has been exhausted"))
        mock_mark_cooldown.assert_called_once()
        args, _ = mock_mark_cooldown.call_args
        assert args[0] == "ya29.rate_limited_token"


def test_cli_show_auth_status_with_pool(mock_vault, capsys):
    """Verify CLI show_auth_status renders when multi-account pool exists."""
    paid_acc = {
        "email": "boss@gmail.com",
        "access_token": "ya29.boss",
        "tier": "paid",
        "expires_at": time.time() + 3600,
    }
    free_acc = {
        "email": "worker@gmail.com",
        "access_token": "ya29.worker",
        "tier": "free",
        "expires_at": time.time() + 3600,
    }
    save_oauth_account("antigravity", paid_acc)
    save_oauth_account("antigravity", free_acc)

    code = show_auth_status()
    assert code == 0


def test_cli_logout_single_account_and_all(mock_vault):
    """Verify CLI logout allows removing a specific email or all accounts."""
    paid_acc = {
        "email": "paid@gmail.com",
        "access_token": "ya29.paid",
        "tier": "paid",
        "expires_at": time.time() + 3600,
    }
    free_acc = {
        "email": "free@gmail.com",
        "access_token": "ya29.free",
        "tier": "free",
        "expires_at": time.time() + 3600,
    }
    save_oauth_account("antigravity", paid_acc)
    save_oauth_account("antigravity", free_acc)

    # 1. Logout single email
    res = logout_provider("antigravity", email="free@gmail.com")
    assert res == 0
    accounts = get_oauth_accounts("antigravity")
    assert len(accounts) == 1
    assert accounts[0]["email"] == "paid@gmail.com"

    # 2. Logout all accounts
    res_all = logout_provider("antigravity", all_accounts=True)
    assert res_all == 0
    assert len(get_oauth_accounts("antigravity")) == 0
