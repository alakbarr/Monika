from tests.conftest import create_mock_async_session
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from monika.infrastructure.providers.llm_factory import (
    LLMFactory,
    FallbackClientWrapper,
    get_client_for_task,
    create_client,
)


@pytest.fixture
def mock_settings():
    return {
        "llm": {
            "providers": {"anthropic": {"enabled": True}, "gemini": {"enabled": True}},
            "model_catalog": {
                "claude-sonnet-5": {"provider": "anthropic"},
                "gemini-3.5-flash-lite": {"provider": "gemini"},
            },
            "task_roles": {
                "test_task": {
                    "primary": "claude-sonnet-5",
                    "fallback_1": "gemini-3.5-flash-lite",
                    "max_tokens": 100,
                    "max_tool_turns": 2,
                }
            },
        }
    }


def test_resolve_provider(mock_settings):
    factory = LLMFactory(mock_settings)
    assert factory._resolve_provider("claude-sonnet-5") == "anthropic"
    assert factory._resolve_provider("gemini-3.5-flash-lite") == "gemini"
    assert factory._resolve_provider("gpt-4") == "openai"  # Guess


@patch("monika.infrastructure.providers.anthropic_provider.AnthropicProvider")
def test_create_client_instance_anthropic(mock_anthropic, mock_settings):
    factory = LLMFactory(mock_settings)
    client = factory._create_client_instance("claude-sonnet-5", {"max_tokens": 50})
    assert client is not None
    mock_anthropic.assert_called_once()


@patch("monika.infrastructure.providers.gemini_provider.GeminiProvider")
def test_create_client_instance_gemini(mock_gemini, mock_settings):
    factory = LLMFactory(mock_settings)
    client = factory._create_client_instance("gemini-3.5-flash-lite", {"max_tokens": 50})
    assert client is not None
    mock_gemini.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_wrapper_success(mock_settings):
    factory = LLMFactory(mock_settings)

    # Mock the client instance creation to return our mock clients
    mock_claude = AsyncMock()
    mock_claude.generate.return_value = "Claude success"

    with patch.object(factory, "_create_client_instance", return_value=mock_claude):
        wrapper = FallbackClientWrapper(
            factory, "claude-sonnet-5", ["gemini-3.5-flash-lite"], mock_settings["llm"]["task_roles"]["test_task"]
        )
        result = await wrapper.generate("test")

        assert result == "Claude success"
        mock_claude.generate.assert_called_once_with("test", system="", temperature=None)
        assert wrapper.model == "claude-sonnet-5"


@pytest.mark.asyncio
async def test_fallback_wrapper_fallback(mock_settings):
    factory = LLMFactory(mock_settings)

    mock_claude = AsyncMock()
    mock_claude.generate.side_effect = Exception("Claude failed")

    mock_gemini = AsyncMock()
    mock_gemini.generate.return_value = "Gemini success"

    def side_effect(model_name, role_config, **kwargs):
        if model_name == "claude-sonnet-5":
            return mock_claude
        return mock_gemini

    with patch.object(factory, "_create_client_instance", side_effect=side_effect):
        wrapper = FallbackClientWrapper(
            factory, "claude-sonnet-5", ["gemini-3.5-flash-lite"], mock_settings["llm"]["task_roles"]["test_task"]
        )
        result = await wrapper.generate("test")

        assert result == "Gemini success"
        mock_claude.generate.assert_called_once()
        mock_gemini.generate.assert_called_once()
        assert wrapper.model == "gemini-3.5-flash-lite"


@pytest.mark.asyncio
async def test_fallback_wrapper_generate_content(mock_settings):
    factory = LLMFactory(mock_settings)
    mock_claude = AsyncMock()
    mock_claude.generate_content.return_value = '{"decision": "buy"}'

    with patch.object(factory, "_create_client_instance", return_value=mock_claude):
        wrapper = FallbackClientWrapper(
            factory, "claude-sonnet-5", ["gemini-3.5-flash-lite"], mock_settings["llm"]["task_roles"]["test_task"]
        )
        result = await wrapper.generate_content(system_prompt="sys", user_message="msg")
        assert result == '{"decision": "buy"}'
        mock_claude.generate_content.assert_called_once_with(
            system_prompt="sys", user_message="msg", response_schema=None, temperature=None
        )


def test_flatten_system_prompt():
    from monika.infrastructure.providers.base_provider import _flatten_system_prompt

    assert _flatten_system_prompt(None) == ""
    assert _flatten_system_prompt("simple string") == "simple string"
    assert _flatten_system_prompt(("part 1", "part 2")) == "part 1\n\npart 2"
    assert _flatten_system_prompt(["part A", "", "part B"]) == "part A\n\npart B"


@pytest.mark.asyncio
async def test_fallback_wrapper_deepcopy_isolation(mock_settings):
    factory = LLMFactory(mock_settings)

    # Primary client modifies arguments in-place and fails
    async def failing_primary(session, system_prompt, messages, tools, **kwargs):
        messages.append({"role": "assistant", "content": "corrupted tool_use block"})
        return {"success": False, "error": "Primary model failed"}

    mock_primary = AsyncMock()
    mock_primary.run_agent_from_messages.side_effect = failing_primary

    # Fallback client should receive pristine original messages
    received_messages_in_fallback = []

    async def succeeding_fallback(session, system_prompt, messages, tools, **kwargs):
        received_messages_in_fallback.extend(messages)
        return {"success": True, "final_text": "Fallback succeeded"}

    mock_fallback = AsyncMock()
    mock_fallback.run_agent_from_messages.side_effect = succeeding_fallback

    def side_effect(model_name, role_config, **kwargs):
        if model_name == "claude-sonnet-5":
            return mock_primary
        return mock_fallback

    with patch.object(factory, "_create_client_instance", side_effect=side_effect):
        wrapper = FallbackClientWrapper(
            factory, "claude-sonnet-5", ["gemini-3.5-flash-lite"], mock_settings["llm"]["task_roles"]["test_task"]
        )
        original_messages = [{"role": "user", "content": "analyze"}]
        result = await wrapper.run_agent_from_messages(
            session=None, system_prompt="sys", messages=original_messages, tools=[]
        )
        assert result["success"] is True
        # Fallback received copy without the corrupted assistant block
        assert len(received_messages_in_fallback) == 1
        assert received_messages_in_fallback[0]["content"] == "analyze"
        assert len(original_messages) == 1


def test_safe_clone_unpicklable_and_nested():
    from monika.infrastructure.providers.llm_factory import _safe_clone

    class FakeAsyncSession:
        pass

    class FakeEngine:
        pass

    session = FakeAsyncSession()
    engine = FakeEngine()

    data = {
        "messages": [{"role": "user", "content": "hello"}],
        "params": {"session": session, "engine": engine, "count": 10},
        "flags": {"a", "b"},
        "tuple_val": (1, 2, [3, 4]),
    }

    cloned = _safe_clone(data)
    assert cloned["messages"] == [{"role": "user", "content": "hello"}]
    assert cloned["params"]["session"] is session  # Preserved without crashing
    assert cloned["params"]["count"] == 10
    assert cloned["flags"] == {"a", "b"}
    assert cloned["tuple_val"] == (1, 2, [3, 4])

    # Mutating cloned list does not mutate original list
    cloned["messages"].append({"role": "assistant", "content": "mutated"})
    assert len(data["messages"]) == 1


def test_resolve_thinking_level_hierarchy():
    settings = {
        "llm": {
            "providers": {"openrouter": {"enabled": True}, "gemini": {"enabled": True}},
            "model_catalog": {
                "gemini-3.7-flash": {"provider": "gemini", "default_thinking": "high"},
                "gemini-3.5-flash-lite": {"provider": "gemini", "default_thinking": "none"},
                "z-ai/glm-5.2:free": {"provider": "openrouter"},
            },
        }
    }
    factory = LLMFactory(settings)

    # 1. Exact model match
    role_cfg_exact = {"thinking": {"z-ai/glm-5.2:free": "max", "openrouter": "low"}}
    assert factory._resolve_thinking_level("z-ai/glm-5.2:free", role_cfg_exact, "openrouter") == "max"

    # 2. Short name match
    role_cfg_short = {"thinking": {"glm-5.2:free": "high", "openrouter": "low"}}
    assert factory._resolve_thinking_level("z-ai/glm-5.2:free", role_cfg_short, "openrouter") == "high"

    # 3. Slot match
    role_cfg_slot = {"thinking": {"primary": "xhigh", "fallback_1": "low", "openrouter": "medium"}}
    assert (
        factory._resolve_thinking_level("z-ai/glm-5.2:free", role_cfg_slot, "openrouter", slot_name="primary")
        == "xhigh"
    )
    assert (
        factory._resolve_thinking_level("minimax/minimax-m3:free", role_cfg_slot, "openrouter", slot_name="fallback_1")
        == "low"
    )

    # 4. Model Catalog default
    role_cfg_cat = {"thinking": {"openrouter": "medium"}}
    assert factory._resolve_thinking_level("gemini-3.7-flash", role_cfg_cat, "gemini") == "high"
    assert factory._resolve_thinking_level("gemini-3.5-flash-lite", role_cfg_cat, "gemini") == "none"

    # 5. Provider fallback
    assert factory._resolve_thinking_level("z-ai/glm-5.2:free", role_cfg_cat, "openrouter") == "medium"

    # 6. Global string thinking
    role_cfg_str = {"thinking": "medium"}
    assert factory._resolve_thinking_level("z-ai/glm-5.2:free", role_cfg_str, "openrouter") == "medium"

    # 7. Default fallback
    assert factory._resolve_thinking_level("unknown-model", {}, "unknown-prov") == "none"


@pytest.mark.asyncio
async def test_fallback_wrapper_dynamic_thinking_level():
    settings = {
        "llm": {
            "providers": {"openrouter": {"enabled": True}, "gemini": {"enabled": True}},
            "model_catalog": {
                "claude-sonnet-5": {"provider": "openrouter"},
                "gemini-3.5-flash-lite": {"provider": "gemini"},
            },
            "task_roles": {
                "granular_task": {
                    "primary": "claude-sonnet-5",
                    "fallback_1": "gemini-3.5-flash-lite",
                    "thinking": {"primary": "max", "fallback_1": "low"},
                }
            },
        }
    }
    factory = LLMFactory(settings)

    mock_primary = AsyncMock()
    mock_primary.generate.side_effect = Exception("Primary failed")
    mock_primary.thinking_level = "max"

    mock_fallback = AsyncMock()
    mock_fallback.generate.return_value = "Fallback success"
    mock_fallback.thinking_level = "low"

    def side_effect(model_name, role_config, slot_name=None):
        if model_name == "claude-sonnet-5":
            return mock_primary
        return mock_fallback

    with patch.object(factory, "_create_client_instance", side_effect=side_effect):
        wrapper = FallbackClientWrapper(
            factory, "claude-sonnet-5", ["gemini-3.5-flash-lite"], settings["llm"]["task_roles"]["granular_task"]
        )
        assert wrapper.thinking_level == "max"
        result = await wrapper.generate("test")
        assert result == "Fallback success"
        assert wrapper.model == "gemini-3.5-flash-lite"
        assert wrapper.thinking_level == "low"


@pytest.mark.asyncio
async def test_fallback_wrapper_activity_log_recorded():
    import asyncio
    from monika.infrastructure.database.models import ActivityLog
    from contextlib import asynccontextmanager

    settings = {
        "llm": {
            "providers": {"anthropic": {"enabled": True}, "gemini": {"enabled": True}},
            "model_catalog": {
                "claude-sonnet-5": {"provider": "anthropic"},
                "gemini-3.5-flash-lite": {"provider": "gemini"},
            },
            "task_roles": {"audit_task": {"primary": "claude-sonnet-5", "fallback_1": "gemini-3.5-flash-lite"}},
        }
    }
    factory = LLMFactory(settings)

    mock_primary = AsyncMock()
    mock_primary.generate.side_effect = Exception("Primary provider authentication failed 401 invalid api key")

    mock_fallback = AsyncMock()
    mock_fallback.generate.return_value = "Fallback recovered"

    mock_session = create_mock_async_session()
    added_items = []
    mock_session.add = MagicMock(side_effect=lambda item: added_items.append(item))
    mock_session.commit = AsyncMock()

    @asynccontextmanager
    async def mock_get_session():
        yield mock_session

    def side_effect(model_name, role_config, slot_name=None):
        if model_name == "claude-sonnet-5":
            return mock_primary
        return mock_fallback

    with (
        patch.object(factory, "_create_client_instance", side_effect=side_effect),
        patch("monika.infrastructure.database.db.get_session", mock_get_session),
    ):
        wrapper = FallbackClientWrapper(
            factory, "claude-sonnet-5", ["gemini-3.5-flash-lite"], settings["llm"]["task_roles"]["audit_task"]
        )
        result = await wrapper.generate("test")
        assert result == "Fallback recovered"
        assert wrapper.model == "gemini-3.5-flash-lite"

        # Let the background logging task finish
        await asyncio.sleep(0.05)

        assert len(added_items) == 1
        log_entry = added_items[0]
        assert isinstance(log_entry, ActivityLog)
        assert log_entry.category == "system"
        assert log_entry.actor == "llm_factory"
        assert "LLMFallbackAudit" in log_entry.description
        assert "downgraded from primary" in log_entry.description
        mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_fallback_wrapper_typesafe_array_schema_skip_audit():
    settings = {
        "llm": {
            "providers": {"typesafe": {"enabled": True}, "gemini": {"enabled": True}},
            "model_catalog": {"jev-latest": {"provider": "typesafe"}, "gemini-3.5-flash-lite": {"provider": "gemini"}},
            "task_roles": {
                "news_task": {
                    "primary": "jev-latest",
                    "fallback_1": "gemini-3.5-flash-lite",
                }
            },
        }
    }
    factory = LLMFactory(settings)
    mock_fb = AsyncMock()
    mock_fb.classify_json.return_value = [{"index": 1, "impact": "HIGH"}]

    def side_effect(model_name, role_config, slot_name=None, task_role=None):
        return mock_fb

    mock_session = create_mock_async_session()
    added_items = []
    mock_session.add = MagicMock(side_effect=lambda item: added_items.append(item))
    mock_session.commit = AsyncMock()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_get_session():
        yield mock_session

    with (
        patch.object(factory, "_create_client_instance", side_effect=side_effect),
        patch("monika.infrastructure.database.db.get_session", mock_get_session),
        patch("monika.infrastructure.providers.llm_factory.logger") as mock_logger,
    ):
        wrapper = FallbackClientWrapper(
            factory,
            "jev-latest",
            ["gemini-3.5-flash-lite"],
            settings["llm"]["task_roles"]["news_task"],
            task_role="news_task",
        )
        res = await wrapper.classify_json(prompt="test", schema={"type": "array", "items": {}})
        assert res == [{"index": 1, "impact": "HIGH"}]
        await asyncio.sleep(0.05)
        warn_msgs = [call.args[0] for call in mock_logger.warning.call_args_list if call.args]
        audit_msgs = [m for m in warn_msgs if "[LLMFallbackAudit]" in m]
        assert len(audit_msgs) == 1
        assert "does not support top-level array schema in classify_json" in audit_msgs[0]


def test_resolve_provider_disabled_fallback_to_openrouter():
    settings = {
        "llm": {
            "providers": {
                "deepseek": {"enabled": False},
                "openai": {"enabled": False},
                "anthropic": {"enabled": False},
                "openrouter": {"enabled": True},
            },
        }
    }
    factory = LLMFactory(settings)
    assert factory._resolve_provider("deepseek-v4.1-flash") == "openrouter"
    assert factory._resolve_provider("gpt-6-astra") == "openrouter"
    assert factory._resolve_provider("claude-sonnet-5") == "openrouter"


@pytest.mark.asyncio
async def test_run_agent_timeout_not_capped_by_hot_path():
    settings = {
        "llm": {
            "providers": {"openrouter": {"enabled": True}},
            "task_roles": {
                "stage2_per_asset_primary": {
                    "primary": "test-agent-model",
                    "max_tool_turns": 12,
                }
            },
        }
    }
    factory = LLMFactory(settings)
    mock_client = AsyncMock()
    mock_client.run_agent.return_value = {"success": True, "final_text": "analysis completed"}

    with (
        patch.object(factory, "_create_client_instance", return_value=mock_client),
        patch("asyncio.wait_for", wraps=asyncio.wait_for) as mock_wait_for,
    ):
        wrapper = FallbackClientWrapper(
            factory,
            "test-agent-model",
            [],
            settings["llm"]["task_roles"]["stage2_per_asset_primary"],
            task_role="stage2_per_asset_primary",
        )
        res = await wrapper.run_agent(
            session=None,
            system_prompt="sys",
            user_message="user",
            tools=[],
        )
        assert res["success"] is True
        # Verify that asyncio.wait_for was called with agent timeout budget (12 * 45 = 540s), not 120s
        assert mock_wait_for.called
        timeout_arg = mock_wait_for.call_args[1].get("timeout")
        assert timeout_arg >= 300.0
        assert timeout_arg == 540.0


@pytest.mark.asyncio
async def test_all_models_cooldown_returns_descriptive_error():
    settings = {
        "llm": {
            "providers": {"openrouter": {"enabled": True}},
            "task_roles": {
                "test_cooldown": {
                    "primary": "model-1",
                    "fallback_1": "model-2",
                }
            },
        }
    }
    factory = LLMFactory(settings)
    wrapper = FallbackClientWrapper(
        factory,
        "model-1",
        ["model-2"],
        settings["llm"]["task_roles"]["test_cooldown"],
        task_role="test_cooldown",
    )
    import time

    wrapper._slot_cooldowns["primary"] = time.time() + 9999.0
    wrapper._slot_cooldowns["fallback_1"] = time.time() + 9999.0

    res = await wrapper.run_agent(session=None, system_prompt="s", user_message="u", tools=[])
    assert res["success"] is False
    assert res["error"] is not None
    assert "All candidate models skipped" in res["error"]
    assert "None" != res["error"]


def test_get_client_for_task_with_empty_settings_loads_default():
    # Calling get_client_for_task with {} should resolve via load_settings, not empty dictionary
    with patch("monika.core.config.settings.load_settings") as mock_load:
        mock_load.return_value = {
            "llm": {
                "default_model": "test-default-model",
                "default_provider": "gemini",
                "task_roles": {"trade_reflection": {"primary": "test-reflection-model", "provider": "gemini"}},
            }
        }
        with patch.object(LLMFactory, "_create_client_instance") as mock_create:
            mock_create.return_value = MagicMock()
            client = get_client_for_task("trade_reflection", {})
            assert client is not None
            mock_load.assert_called_once()


def test_get_client_for_task_role_alias_resolution():
    settings = {
        "llm": {
            "default_model": "test-default",
            "task_roles": {
                "risk_gate_conservative": {"primary": "conservative-model", "provider": "gemini"},
            },
        }
    }
    factory = LLMFactory(settings)
    with patch.object(factory, "_create_client_instance") as mock_create:
        mock_create.return_value = MagicMock()
        # "conservative_risk" should map to alias "risk_gate_conservative"
        client = factory.get_client_for_task("conservative_risk")
        assert client is not None
        assert client.model == "conservative-model"


def test_role_provider_override_gemini_3_8_flash_and_openrouter_coexistence():
    from monika.core.config.settings import load_settings
    from monika.infrastructure.providers.gemini_provider import GeminiProvider
    from monika.infrastructure.providers.openrouter_provider import OpenRouterProvider

    settings = load_settings()
    factory = LLMFactory(settings)

    # Catalog default for gemini-3.8-flash remains openrouter
    assert settings["llm"]["model_catalog"]["gemini-3.8-flash"]["provider"] == "openrouter"
    assert factory._resolve_provider("gemini-3.8-flash") == "openrouter"

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-gemini-key", "OPENROUTER_API_KEY": "test-or-key"}):
        for role_name in ("news_digest", "news_digest_macro_overview"):
            role_cfg = settings["llm"]["task_roles"][role_name]
            assert role_cfg["primary"] == "gemini-3.8-flash"
            raw_prov = role_cfg["provider"]
            prov_str = raw_prov.get("primary") if isinstance(raw_prov, dict) else raw_prov
            assert prov_str == "gemini"
            assert factory._resolve_provider("gemini-3.8-flash", role_config=role_cfg, slot_name="primary") == "gemini"

            wrapper = factory.get_client_for_task(role_name)
            assert wrapper.provider_name == "gemini"
            inner_client = wrapper._get_client("primary")
            assert isinstance(inner_client, GeminiProvider)
            assert inner_client.model == "gemini-3.8-flash"

        # debate_judge uses gemini-3.8-flash with provider: openrouter -> must stay on OpenRouterProvider
        judge_cfg = settings["llm"]["task_roles"]["debate_judge"]
        assert judge_cfg["primary"] == "gemini-3.8-flash"
        judge_prov = judge_cfg["provider"]
        judge_prov_str = judge_prov.get("primary") if isinstance(judge_prov, dict) else judge_prov
        assert judge_prov_str == "openrouter"
        assert factory._resolve_provider("gemini-3.8-flash", role_config=judge_cfg, slot_name="primary") == "openrouter"
        judge_wrapper = factory.get_client_for_task("debate_judge")
        assert judge_wrapper.provider_name == "openrouter"
        judge_inner = judge_wrapper._get_client("primary")
        assert isinstance(judge_inner, OpenRouterProvider)
        assert judge_inner.model == "google/gemini-3.8-flash"


def test_role_provider_override_across_all_direct_vendors():
    from monika.infrastructure.providers.anthropic_provider import AnthropicProvider
    from monika.infrastructure.providers.deepseek_provider import DeepSeekProvider
    from monika.infrastructure.providers.openai_provider import OpenAIProvider
    from monika.infrastructure.providers.zai_provider import ZAIProvider

    settings = {
        "llm": {
            "providers": {
                "openrouter": {"enabled": True},
                "anthropic": {"enabled": True},
                "openai": {"enabled": True},
                "deepseek": {"enabled": True},
                "zai": {"enabled": True},
            },
            "model_catalog": {
                "claude-opus-5.5": {"provider": "openrouter", "default_thinking": "high"},
                "opus-5.5": {"provider": "openrouter", "default_thinking": "high"},
                "gpt-6-astra": {"provider": "openrouter", "default_thinking": "high"},
                "gpt-6-luna-xhigh": {"provider": "openrouter", "default_thinking": "xhigh"},
                "deepseek-v4.1-flash": {"provider": "openrouter", "default_thinking": "high"},
                "glm-5.3-flash": {"provider": "openrouter", "default_thinking": "high"},
            },
        }
    }
    factory = LLMFactory(settings)

    with patch.dict(
        "os.environ",
        {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENAI_API_KEY": "sk-oai-test",
            "DEEPSEEK_API_KEY": "sk-ds-test",
            "ZAI_API_KEY": "sk-zai-test",
        },
    ):
        # 1. Anthropic direct (both canonical name and short alias)
        ant_role = {"primary": "claude-opus-5.5", "provider": "anthropic"}
        assert factory._resolve_provider("claude-opus-5.5", role_config=ant_role, slot_name="primary") == "anthropic"
        c_ant = factory._create_client_instance("claude-opus-5.5", ant_role, slot_name="primary")
        assert isinstance(c_ant, AnthropicProvider)
        assert c_ant.model == "claude-opus-5.5"

        c_ant_alias = factory._create_client_instance("opus-5.5", {"primary": "opus-5.5", "provider": "anthropic"})
        assert isinstance(c_ant_alias, AnthropicProvider)
        assert c_ant_alias.model == "claude-opus-5.5"
        assert c_ant_alias.raw_model_name == "opus-5.5"

        # 2. OpenAI direct (both standard and internal thinking-suffixed alias)
        oai_role = {"primary": "gpt-6-astra", "provider": "openai"}
        assert factory._resolve_provider("gpt-6-astra", role_config=oai_role, slot_name="primary") == "openai"
        c_oai = factory._create_client_instance("gpt-6-astra", oai_role, slot_name="primary")
        assert isinstance(c_oai, OpenAIProvider)
        assert c_oai.model == "gpt-6-astra"

        c_oai_luna = factory._create_client_instance(
            "gpt-6-luna-xhigh", {"primary": "gpt-6-luna-xhigh", "provider": "openai"}
        )
        assert isinstance(c_oai_luna, OpenAIProvider)
        assert c_oai_luna.model == "gpt-6-luna"
        assert c_oai_luna.raw_model_name == "gpt-6-luna-xhigh"

        # 3. DeepSeek direct
        ds_role = {"primary": "deepseek-v4.1-flash", "provider": "deepseek"}
        assert factory._resolve_provider("deepseek-v4.1-flash", role_config=ds_role, slot_name="primary") == "deepseek"
        c_ds = factory._create_client_instance("deepseek/deepseek-v4.1-flash", ds_role, slot_name="primary")
        assert isinstance(c_ds, DeepSeekProvider)
        assert c_ds.model == "deepseek-v4.1-flash"

        # 4. Z.AI direct
        zai_role = {"primary": "glm-5.3-flash", "provider": "zai"}
        assert factory._resolve_provider("glm-5.3-flash", role_config=zai_role, slot_name="primary") == "zai"
        c_zai = factory._create_client_instance("z-ai/glm-5.3-flash:free", zai_role, slot_name="primary")
        assert isinstance(c_zai, ZAIProvider)
        assert c_zai.model == "glm-5.3-flash"


def test_cross_vendor_fallback_chain_preserves_incompatible_fallback_provider():
    settings = {
        "llm": {
            "providers": {"gemini": {"enabled": True}, "openrouter": {"enabled": True}, "groq": {"enabled": True}},
            "model_catalog": {
                "gemini-3.8-flash": {"provider": "openrouter"},
                "gemini-3.5-flash": {"provider": "gemini"},
                "glm-5.3-flash": {"provider": "openrouter"},
                "qwen3.8-27b": {"provider": "groq"},
            },
        }
    }
    factory = LLMFactory(settings)
    role_cfg = {
        "primary": "gemini-3.8-flash",
        "provider": "gemini",
        "fallback_1": "gemini-3.5-flash",
        "fallback_2": "glm-5.3-flash",
        "fallback_3": "qwen3.8-27b",
    }

    assert factory._resolve_provider("gemini-3.8-flash", role_config=role_cfg, slot_name="primary") == "gemini"
    assert factory._resolve_provider("gemini-3.5-flash", role_config=role_cfg, slot_name="fallback_1") == "gemini"
    assert factory._resolve_provider("glm-5.3-flash", role_config=role_cfg, slot_name="fallback_2") == "openrouter"
    assert factory._resolve_provider("qwen3.8-27b", role_config=role_cfg, slot_name="fallback_3") == "groq"


def test_explicit_provider_prefix_preserves_catalog_thinking_and_strips_prefix():
    from monika.infrastructure.providers.anthropic_provider import AnthropicProvider

    settings = {
        "llm": {
            "providers": {"anthropic": {"enabled": True}, "openrouter": {"enabled": True}},
            "model_catalog": {
                "claude-opus-5.5": {
                    "provider": "openrouter",
                    "model_name": "anthropic/claude-opus-5.5",
                    "default_thinking": "xhigh",
                }
            },
        }
    }
    factory = LLMFactory(settings)
    role_cfg = {"primary": "anthropic:claude-opus-5.5", "provider": "openrouter"}

    # Explicit prefix wins over both catalog and role_config["provider"]
    assert (
        factory._resolve_provider("anthropic:claude-opus-5.5", role_config=role_cfg, slot_name="primary") == "anthropic"
    )
    # Catalog default_thinking is still found after stripping prefix
    assert (
        factory._resolve_thinking_level("anthropic:claude-opus-5.5", role_cfg, "anthropic", slot_name="primary")
        == "xhigh"
    )

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
        client = factory._create_client_instance("anthropic:claude-opus-5.5", role_cfg, slot_name="primary")
        assert isinstance(client, AnthropicProvider)
        assert client.model == "claude-opus-5.5"
        assert client.thinking_level in ("xhigh", "high")


def test_same_model_cross_provider_fallback_chain():
    from monika.infrastructure.providers.gemini_provider import GeminiProvider
    from monika.infrastructure.providers.openrouter_provider import OpenRouterProvider

    settings = {
        "llm": {
            "providers": {"gemini": {"enabled": True}, "openrouter": {"enabled": True}},
            "model_catalog": {
                "gemini-3.8-flash": {"provider": "openrouter", "default_thinking": "high"},
            },
            "task_roles": {
                "role_slot_prov": {
                    "primary": "gemini-3.8-flash",
                    "provider": "gemini",
                    "fallback_1": "gemini-3.8-flash",
                    "fallback_1_provider": "openrouter",
                },
                "role_providers_map": {
                    "primary": "gemini-3.8-flash",
                    "fallback_1": "gemini-3.8-flash",
                    "providers": {
                        "primary": "gemini",
                        "fallback_1": "openrouter",
                    },
                },
                "role_prefix": {
                    "primary": "gemini:gemini-3.8-flash",
                    "fallback_1": "openrouter:gemini-3.8-flash",
                },
            },
        }
    }
    factory = LLMFactory(settings)

    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-gem-key", "OPENROUTER_API_KEY": "test-or-key"}):
        for role_name in ("role_slot_prov", "role_providers_map", "role_prefix"):
            wrapper = factory.get_client_for_task(role_name)
            assert len(wrapper.fallbacks) == 1
            assert wrapper.provider_name == "gemini"

            c_primary = wrapper._get_client("primary")
            assert isinstance(c_primary, GeminiProvider)
            assert c_primary.model == "gemini-3.8-flash"

            c_fallback = wrapper._get_client("fallback_1")
            assert isinstance(c_fallback, OpenRouterProvider)
            assert c_fallback.model == "google/gemini-3.8-flash"
