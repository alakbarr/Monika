import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from analysis.providers.llm_factory import LLMFactory, FallbackClientWrapper, get_client_for_task, create_client

@pytest.fixture
def mock_settings():
    return {
        "llm": {
            "providers": {
                "anthropic": {"enabled": True},
                "gemini": {"enabled": True}
            },
            "model_catalog": {
                "claude-sonnet-5": {"provider": "anthropic"},
                "gemini-3.5-flash-lite": {"provider": "gemini"}
            },
            "task_roles": {
                "test_task": {
                    "primary": "claude-sonnet-5",
                    "fallback_1": "gemini-3.5-flash-lite",
                    "max_tokens": 100,
                    "max_tool_turns": 2
                }
            }
        }
    }

def test_resolve_provider(mock_settings):
    factory = LLMFactory(mock_settings)
    assert factory._resolve_provider("claude-sonnet-5") == "anthropic"
    assert factory._resolve_provider("gemini-3.5-flash-lite") == "gemini"
    assert factory._resolve_provider("gpt-4") == "openai" # Guess

@patch('analysis.providers.anthropic_provider.AnthropicProvider')
def test_create_client_instance_anthropic(mock_anthropic, mock_settings):
    factory = LLMFactory(mock_settings)
    client = factory._create_client_instance("claude-sonnet-5", {"max_tokens": 50})
    assert client is not None
    mock_anthropic.assert_called_once()

@patch('analysis.providers.gemini_provider.GeminiProvider')
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
    
    with patch.object(factory, '_create_client_instance', return_value=mock_claude):
        wrapper = FallbackClientWrapper(factory, "claude-sonnet-5", ["gemini-3.5-flash-lite"], mock_settings["llm"]["task_roles"]["test_task"])
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
        
    with patch.object(factory, '_create_client_instance', side_effect=side_effect):
        wrapper = FallbackClientWrapper(factory, "claude-sonnet-5", ["gemini-3.5-flash-lite"], mock_settings["llm"]["task_roles"]["test_task"])
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
    
    with patch.object(factory, '_create_client_instance', return_value=mock_claude):
        wrapper = FallbackClientWrapper(factory, "claude-sonnet-5", ["gemini-3.5-flash-lite"], mock_settings["llm"]["task_roles"]["test_task"])
        result = await wrapper.generate_content(system_prompt="sys", user_message="msg")
        assert result == '{"decision": "buy"}'
        mock_claude.generate_content.assert_called_once_with(
            system_prompt="sys", user_message="msg", response_schema=None, temperature=None
        )


def test_flatten_system_prompt():
    from analysis.providers.base_provider import _flatten_system_prompt
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
        
    with patch.object(factory, '_create_client_instance', side_effect=side_effect):
        wrapper = FallbackClientWrapper(
            factory, "claude-sonnet-5", ["gemini-3.5-flash-lite"],
            mock_settings["llm"]["task_roles"]["test_task"]
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
    from analysis.providers.llm_factory import _safe_clone
    
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
        "tuple_val": (1, 2, [3, 4])
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
            "providers": {
                "openrouter": {"enabled": True},
                "gemini": {"enabled": True}
            },
            "model_catalog": {
                "gemini-3.7-flash": {"provider": "gemini", "default_thinking": "high"},
                "gemini-3.5-flash-lite": {"provider": "gemini", "default_thinking": "none"},
                "z-ai/glm-5.2:free": {"provider": "openrouter"}
            }
        }
    }
    factory = LLMFactory(settings)

    # 1. Exact model match
    role_cfg_exact = {
        "thinking": {
            "z-ai/glm-5.2:free": "max",
            "openrouter": "low"
        }
    }
    assert factory._resolve_thinking_level("z-ai/glm-5.2:free", role_cfg_exact, "openrouter") == "max"

    # 2. Short name match
    role_cfg_short = {
        "thinking": {
            "glm-5.2:free": "high",
            "openrouter": "low"
        }
    }
    assert factory._resolve_thinking_level("z-ai/glm-5.2:free", role_cfg_short, "openrouter") == "high"

    # 3. Slot match
    role_cfg_slot = {
        "thinking": {
            "primary": "xhigh",
            "fallback_1": "low",
            "openrouter": "medium"
        }
    }
    assert factory._resolve_thinking_level("z-ai/glm-5.2:free", role_cfg_slot, "openrouter", slot_name="primary") == "xhigh"
    assert factory._resolve_thinking_level("minimax/minimax-m3:free", role_cfg_slot, "openrouter", slot_name="fallback_1") == "low"

    # 4. Model Catalog default
    role_cfg_cat = {
        "thinking": {
            "openrouter": "medium"
        }
    }
    assert factory._resolve_thinking_level("gemini-3.7-flash", role_cfg_cat, "gemini") == "high"
    assert factory._resolve_thinking_level("gemini-3.5-flash-lite", role_cfg_cat, "gemini") == "none"

    # 5. Provider fallback
    assert factory._resolve_thinking_level("z-ai/glm-5.2:free", role_cfg_cat, "openrouter") == "medium"

    # 6. Global string thinking
    role_cfg_str = {
        "thinking": "medium"
    }
    assert factory._resolve_thinking_level("z-ai/glm-5.2:free", role_cfg_str, "openrouter") == "medium"

    # 7. Default fallback
    assert factory._resolve_thinking_level("unknown-model", {}, "unknown-prov") == "none"


@pytest.mark.asyncio
async def test_fallback_wrapper_dynamic_thinking_level():
    settings = {
        "llm": {
            "providers": {
                "openrouter": {"enabled": True},
                "gemini": {"enabled": True}
            },
            "model_catalog": {
                "claude-sonnet-5": {"provider": "openrouter"},
                "gemini-3.5-flash-lite": {"provider": "gemini"}
            },
            "task_roles": {
                "granular_task": {
                    "primary": "claude-sonnet-5",
                    "fallback_1": "gemini-3.5-flash-lite",
                    "thinking": {
                        "primary": "max",
                        "fallback_1": "low"
                    }
                }
            }
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

    with patch.object(factory, '_create_client_instance', side_effect=side_effect):
        wrapper = FallbackClientWrapper(
            factory, "claude-sonnet-5", ["gemini-3.5-flash-lite"],
            settings["llm"]["task_roles"]["granular_task"]
        )
        assert wrapper.thinking_level == "max"
        result = await wrapper.generate("test")
        assert result == "Fallback success"
        assert wrapper.model == "gemini-3.5-flash-lite"
        assert wrapper.thinking_level == "low"


@pytest.mark.asyncio
async def test_fallback_wrapper_activity_log_recorded():
    import asyncio
    from database.models import ActivityLog
    from contextlib import asynccontextmanager

    settings = {
        "llm": {
            "providers": {
                "anthropic": {"enabled": True},
                "gemini": {"enabled": True}
            },
            "model_catalog": {
                "claude-sonnet-5": {"provider": "anthropic"},
                "gemini-3.5-flash-lite": {"provider": "gemini"}
            },
            "task_roles": {
                "audit_task": {
                    "primary": "claude-sonnet-5",
                    "fallback_1": "gemini-3.5-flash-lite"
                }
            }
        }
    }
    factory = LLMFactory(settings)

    mock_primary = AsyncMock()
    mock_primary.generate.side_effect = Exception("Primary provider timeout")

    mock_fallback = AsyncMock()
    mock_fallback.generate.return_value = "Fallback recovered"

    mock_session = AsyncMock()
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

    with patch.object(factory, '_create_client_instance', side_effect=side_effect), \
         patch('database.db.get_session', mock_get_session):
        wrapper = FallbackClientWrapper(
            factory, "claude-sonnet-5", ["gemini-3.5-flash-lite"],
            settings["llm"]["task_roles"]["audit_task"]
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





