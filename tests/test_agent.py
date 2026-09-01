from functools import wraps
from types import SimpleNamespace

import pytest

from autom8 import Agent, ToolResult
from autom8.tools import TOOL_REGISTRY


def test_invoke_requires_model():
    agent = Agent(tool_registry={})
    with pytest.raises(ValueError, match="No model specified"):
        agent.invoke("hello")


def test_from_config_decorates_only_builtin_tools():
    def custom_tool() -> ToolResult:
        return ToolResult(type="data", values=[], model_output={})

    def tool_decorator(tool):
        @wraps(tool)
        def decorated_tool(*args, **kwargs):
            return tool(*args, **kwargs)
        return decorated_tool

    config = {
        "model": "m",
        "system_prompt": "S",
        "tool_registry": {"read_file": TOOL_REGISTRY["read_file"], "custom": custom_tool},
        "max_completion_tokens": 2000,
        "tool_choice": "auto",
    }
    agent = Agent.from_config(config, builtin_tool_decorator=tool_decorator)
    assert agent.tool_registry["read_file"] is not TOOL_REGISTRY["read_file"]
    assert agent.tool_registry["read_file"].__wrapped__ is TOOL_REGISTRY["read_file"]
    assert agent.tool_registry["custom"] is custom_tool


def test_invoke_records_user_and_assistant_messages(monkeypatch):
    agent = Agent(model="m", system_prompt="S", tool_registry={})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: SimpleNamespace(content="A", tool_calls=None))
    result = agent.invoke("Q")
    assert result.response == "A"
    assert result.tool_calls == []
    assert agent.sessions[0] == [{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}, {"role": "assistant", "content": "A"}]


def test_invoke_resets_session_when_instructions_change(monkeypatch):
    agent = Agent(model="m", system_prompt="S", tool_registry={})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: SimpleNamespace(content="A", tool_calls=None))
    agent.invoke("one")
    agent.invoke("two", instructions="T")
    assert agent.sessions[0][0] == {"role": "system", "content": "T"}
    assert [message["content"] for message in agent.sessions[0]] == ["T", "two", "A"]


def test_invoke_returns_typed_tool_results(monkeypatch):
    tool_result = ToolResult(type="image",
                             values=["/tmp/one.png", "/tmp/two.png"],
                             model_output={"status": "success", "message": "The images will be delivered separately."})

    def generate_images(prompt):
        return tool_result
    requested_tool_call = SimpleNamespace(id="1", function=SimpleNamespace(name="generate_images", arguments='{"prompt": "mountains"}'))
    responses = iter([SimpleNamespace(content=None, tool_calls=[requested_tool_call]), SimpleNamespace(content="Done", tool_calls=None)])
    agent = Agent(model="m", tool_registry={"generate_images": generate_images})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: next(responses))
    result = agent.invoke("Generate two images")
    assert result.response == "Done"
    assert result.results("image") == ["/tmp/one.png", "/tmp/two.png"]
    assert result.tool_calls[0].name == "generate_images"
    assert result.tool_calls[0].arguments == {"prompt": "mountains"}
    assert result.tool_calls[0].result == tool_result
    assert agent.sessions[0][-2]["content"] == '{"status": "success", "message": "The images will be delivered separately."}'
    assert "/tmp/one.png" not in agent.sessions[0][-2]["content"]


def test_invoke_rejects_invalid_tool_result(monkeypatch):
    def search(query):
        return {"urls": ["https://example.com"]}
    requested_tool_call = SimpleNamespace(id="1", function=SimpleNamespace(name="search", arguments='{"query": "example"}'))
    response = SimpleNamespace(content=None, tool_calls=[requested_tool_call])
    agent = Agent(model="m", tool_registry={"search": search})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: response)
    with pytest.raises(TypeError, match="Tool 'search' must return ToolResult, got dict"):
        agent.invoke("Search")
