from types import SimpleNamespace

import pytest

from autom8 import Agent, ToolResult
from autom8.tools import TOOL_REGISTRY


def test_invoke_requires_model():
    agent = Agent(tool_registry={})
    with pytest.raises(ValueError, match="No model specified"):
        agent.invoke("hello")


def test_execute_llm_call_forwards_optional_reasoning_effort(monkeypatch):
    captured_request_options = []
    def fake_completion(**request_options):
        captured_request_options.append(request_options)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="A", tool_calls=None))])
    monkeypatch.setattr("autom8.agent.completion", fake_completion)
    config = {"model": "m", "system_prompt": "S", "tool_registry": {}, "max_completion_tokens": 2000, "tool_choice": "auto", "reasoning_effort": "medium"}
    Agent.from_config(config).invoke("Q")
    Agent(model="m", tool_registry={}).invoke("Q")
    assert captured_request_options[0]["reasoning_effort"] == "medium"
    assert "reasoning_effort" not in captured_request_options[1]


def test_from_config_decorates_only_builtin_tools(monkeypatch):
    def custom_tool() -> ToolResult:
        return ToolResult(type="data", values=[], model_output={})

    decorated_calls = []

    def tool_decorator(tool):
        def decorated_tool(*args, **kwargs):
            decorated_calls.append(kwargs)
            return tool(*args, **kwargs)
        return decorated_tool

    config = {
        "model": "m",
        "system_prompt": "S",
        "tool_registry": {"read_file": TOOL_REGISTRY["read_file"], "custom": custom_tool},
        "max_completion_tokens": 2000,
        "tool_choice": "auto",
        "parallel_tool_calls": None,
    }
    agent = Agent.from_config(config, builtin_tool_decorator=tool_decorator)
    read_file_schema = next(tool_schema for tool_schema in agent.tools if tool_schema["function"]["name"] == "read_file")
    requested_tool_call = SimpleNamespace(id="1", function=SimpleNamespace(name="read_file", arguments='{"filename": "missing.txt"}'))
    responses = iter([SimpleNamespace(content=None, tool_calls=[requested_tool_call]), SimpleNamespace(content="Done", tool_calls=None)])
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: next(responses))
    agent.invoke("Read the file")

    assert agent.tool_registry["read_file"] is not TOOL_REGISTRY["read_file"]
    assert read_file_schema["function"]["parameters"]["required"] == ["filename"]
    assert decorated_calls == [{"filename": "missing.txt"}]
    assert agent.tool_registry["custom"] is custom_tool


def test_execute_llm_call_disables_parallel_tool_calls(monkeypatch):
    request_options = {}
    monkeypatch.setattr("autom8.agent.completion", lambda **kwargs: request_options.update(kwargs) or SimpleNamespace(choices=[SimpleNamespace(message="A")]))
    agent = Agent(model="m", tool_registry={"custom": lambda: None}, parallel_tool_calls=False)
    agent._execute_llm_call([], "m", None)
    assert request_options["parallel_tool_calls"] is False


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
