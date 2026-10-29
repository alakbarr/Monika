import pytest
from monika.core.config.settings import load_settings
from monika.infrastructure.providers.llm_factory import LLMFactory


EXPECTED_MODELS_ORDER = [
    "gemini-3.7-flash",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "glm-5.2:free",
    "minimax-m3:free",
    "qwen3.8-27b",
    "gemini-3.5-flash-lite",
    "qwen3.6-27b",
    "gemini-3.1-flash-lite",
]


def test_settings_task_roles_hierarchy_and_thinking_high():
    """Verify all task roles in settings.yaml have the exact 8-tier hierarchy and thinking: high."""
    settings = load_settings()
    llm_cfg = settings.get("llm", {})
    task_roles = llm_cfg.get("task_roles", {})
    catalog = llm_cfg.get("model_catalog", {})

    assert len(task_roles) >= 25, f"Expected >= 25 task roles, got {len(task_roles)}"

    # 1. Verify every model in expected list is registered in model_catalog
    for model_name in EXPECTED_MODELS_ORDER:
        assert model_name in catalog, f"Model '{model_name}' missing from llm.model_catalog"

    # 2. Verify each task role
    factory = LLMFactory(settings)
    for role_name, role_cfg in task_roles.items():
        primary_model = role_cfg.get("primary")
        assert primary_model in catalog, f"Role '{role_name}' primary '{primary_model}' missing from catalog"

        for i in range(1, 15):
            slot_key = f"fallback_{i}"
            if slot_key in role_cfg:
                fb_model = role_cfg[slot_key]
                assert fb_model in catalog, f"Role '{role_name}' {slot_key} '{fb_model}' missing from catalog"

        # 3. Verify thinking level resolves to a valid value
        thinking_gemini = factory._resolve_thinking_level(primary_model, role_cfg, "gemini", "primary")
        assert thinking_gemini in ("high", "medium", "low", "none", "minimal", "xhigh", "max"), (
            f"Role '{role_name}' gemini thinking is '{thinking_gemini}'"
        )

        # 4. Verify provider resolution
        assert factory._resolve_provider("gemini-3.7-flash") in ("gemini", "openrouter")
        assert factory._resolve_provider("glm-5.2:free") == "openrouter"
        assert factory._resolve_provider("minimax-m3:free") == "openrouter"
        assert factory._resolve_provider("qwen3.8-27b") == "groq"
        assert factory._resolve_provider("qwen3.6-27b") == "groq"
        assert factory._resolve_provider("gemini-3.1-flash-lite") == "gemini"


def test_groq_aliases_include_qwen():
    """Verify Groq provider aliases include qwen3.8-27b and qwen3.6-27b."""
    from monika.infrastructure.providers.groq_provider import GROQ_MODEL_ALIASES

    assert "qwen3.8-27b" in GROQ_MODEL_ALIASES
    assert "qwen3.6-27b" in GROQ_MODEL_ALIASES
    assert GROQ_MODEL_ALIASES["qwen3.6-27b"] == "qwen/qwen3.8-27b"


@pytest.mark.asyncio
async def test_fallback_client_wrapper_per_model_timeout():
    """Verify FallbackClientWrapper moves to next fallback model when primary times out."""
    import asyncio
    from unittest.mock import AsyncMock, patch, MagicMock
    from monika.infrastructure.providers.llm_factory import LLMFactory, FallbackClientWrapper

    settings = {
        "llm": {
            "model_catalog": {"model_hang": {"provider": "gemini"}, "model_fast": {"provider": "openrouter"}},
            "task_roles": {"test_role": {"primary": "model_hang", "fallback_1": "model_fast"}},
        }
    }

    factory = LLMFactory(settings)
    wrapper = FallbackClientWrapper(
        factory=factory,
        primary="model_hang",
        fallbacks=["model_fast"],
        role_config={"primary": "model_hang", "fallback_1": "model_fast"},
        task_role="test_role",
    )

    # Mock client 1 that hangs forever
    client_hang = MagicMock()

    async def _hang(*args, **kwargs):
        await asyncio.sleep(10.0)
        return {"success": True, "final_text": "hang"}

    client_hang.run_agent = AsyncMock(side_effect=_hang)

    # Mock client 2 that succeeds immediately
    client_fast = MagicMock()
    client_fast.run_agent = AsyncMock(return_value={"success": True, "final_text": "fast_success"})

    def mock_create_instance(model, role_cfg, slot_name=None):
        if model == "model_hang":
            return client_hang
        return client_fast

    with patch.object(factory, "_create_client_instance", side_effect=mock_create_instance):
        # Pass small _per_model_timeout for test speed
        result = await wrapper.run_agent(
            session=MagicMock(), system_prompt="sys", user_message="user", tools=[], _per_model_timeout=0.1
        )
        assert result["success"] is True
        assert result["final_text"] == "fast_success"
        assert wrapper.model == "model_fast"


def test_catalog_provider_routing_groq_qwen():
    """Qwen bare names resolve via catalog to groq, never ollama (Round 5 H-4)."""
    settings = load_settings()
    factory = LLMFactory(settings)
    assert factory._resolve_provider("qwen3.8-27b") == "groq"
    assert factory._resolve_provider("qwen3.6-27b") == "groq"


def test_unknown_name_never_routes_to_ollama():
    """Name-guess heuristic must not send unknown bare names to ollama (no tool calling)."""
    settings = load_settings()
    factory = LLMFactory(settings)
    assert factory._resolve_provider("totally-unknown-model") != "ollama"


def test_startup_check_fails_on_ollama_tool_role():
    """_check_model_roles must fail fast when a tool-bearing role resolves to ollama."""
    from monika.application.agent.startup_checks import StartupChecker

    settings = load_settings()
    checker = StartupChecker(settings)
    checker.settings["llm"]["task_roles"]["stage1_fundamental"] = {
        "primary": "llama3-local",
        "thinking": {"anthropic": "none", "gemini": "none"},
    }
    ok, _warnings = checker._check_model_roles()
    assert ok is False


def test_startup_check_task_roles_complete_and_legacy_backfill():
    """All code task_roles must exist in loaded settings and backfill legacy configs missing macro_chronicle_curator."""
    from copy import deepcopy
    from monika.application.agent.startup_checks import StartupChecker

    settings = load_settings()
    assert "macro_chronicle_curator" in settings.get("llm", {}).get("task_roles", {})
    checker = StartupChecker(settings)
    ok, _warnings = checker._check_task_roles()
    assert ok is True

    legacy_raw = deepcopy(settings)
    legacy_raw["llm"]["task_roles"].pop("macro_chronicle_curator", None)
    reloaded = load_settings(legacy_raw)
    assert "macro_chronicle_curator" in reloaded["llm"]["task_roles"]


def test_future_proof_resolve_stale_timeout_floor():
    """Verify timeout floor is dynamic, capability-based, and model-agnostic."""
    from monika.infrastructure.providers.capabilities import resolve_stale_timeout_floor

    # 1. Any future unknown model name with high thinking level gets 600s
    assert resolve_stale_timeout_floor("future-provider/hyper-model-9", thinking_level="high") == 600.0
    assert resolve_stale_timeout_floor("unknown-vendor/model-x", thinking_level="max") == 600.0
    assert resolve_stale_timeout_floor("unknown-vendor/model-x", thinking_level="medium") == 360.0

    # 2. Large thinking budget (>= 8192) dynamically triggers 600s
    assert resolve_stale_timeout_floor("unseen-model", thinking_budget=16384) == 600.0

    # 3. Generic reasoning keywords across any provider get >= 360s
    assert resolve_stale_timeout_floor("custom/qwen-3-deep-reasoning") == 360.0
    assert resolve_stale_timeout_floor("local/llama-4-reasoner") == 360.0

    # 4. Standard non-thinking model defaults to standard timeout
    assert resolve_stale_timeout_floor("gemini-3.5-flash-lite", default_timeout=45.0) == 45.0


@pytest.mark.asyncio
async def test_future_model_run_agent_reasoning_timeout_protection():
    """Verify ANY model with thinking: high is floored to >=300s without hardcoded names."""
    import asyncio
    from unittest.mock import AsyncMock, patch, MagicMock
    from monika.infrastructure.providers.llm_factory import LLMFactory, FallbackClientWrapper

    settings = {
        "llm": {
            "model_catalog": {"future-frontier-v2": {"provider": "openrouter"}},
            "task_roles": {
                "stage1_fundamental": {
                    "primary": "future-frontier-v2",
                    "thinking": "high",
                    "per_model_timeout_seconds": 120.0,
                    "max_tool_turns": 4,
                }
            },
        }
    }

    factory = LLMFactory(settings)
    wrapper = FallbackClientWrapper(
        factory=factory,
        primary="future-frontier-v2",
        fallbacks=[],
        role_config=settings["llm"]["task_roles"]["stage1_fundamental"],
        task_role="stage1_fundamental",
    )

    client_future = MagicMock()
    client_future.thinking_level = "high"

    async def _mock_run_agent(*args, **kwargs):
        return {"success": True, "final_text": "future_synthesis"}

    client_future.run_agent = AsyncMock(side_effect=_mock_run_agent)

    with patch.object(factory, "_create_client_instance", return_value=client_future):
        with patch("asyncio.wait_for", wraps=asyncio.wait_for) as mock_wait_for:
            result = await wrapper.run_agent(
                session=MagicMock(),
                system_prompt="sys",
                user_message="user",
                tools=[],
            )
            assert result["success"] is True
            assert mock_wait_for.called
            _, call_kwargs = mock_wait_for.call_args
            actual_timeout = call_kwargs.get("timeout")
            assert actual_timeout >= 300.0, f"Expected timeout >= 300.0s, got {actual_timeout}s"
