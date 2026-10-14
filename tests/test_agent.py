from types import SimpleNamespace

import pytest
from litellm.types.llms.openai import ResponseAPIUsage, ResponsesAPIResponse

from autom8 import Agent, ToolResult
from autom8.tools import TOOL_REGISTRY


def text_response(text: str, annotations=None) -> SimpleNamespace:
    output_item = {"type": "message",
                   "role": "assistant",
                   "status": "completed",
                   "content": [{"type": "output_text", "text": text, "annotations": annotations or []}]}
    return SimpleNamespace(output=[output_item], output_text=text)


def test_invoke_requires_model():
    agent = Agent(tool_registry={})
    with pytest.raises(ValueError, match="No model specified"):
        agent.invoke("hello")


def test_execute_llm_call_forwards_optional_reasoning_effort(monkeypatch):
    captured_request_options = []
    def fake_responses(**request_options):
        captured_request_options.append(request_options)
        return text_response("A")
    monkeypatch.setattr("autom8.agent.responses", fake_responses)
    config = {"model": "m", "system_prompt": "S", "tool_registry": {}, "max_completion_tokens": 2000, "tool_choice": "auto",
              "reasoning_effort": "medium"}
    Agent.from_config(config).invoke("Q")
    Agent(model="m", tool_registry={}).invoke("Q")
    assert captured_request_options[0]["reasoning"] == {"effort": "medium"}
    assert "reasoning" not in captured_request_options[1]


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
    read_file_schema = next(tool_schema for tool_schema in agent.tools if tool_schema.get("name") == "read_file")
    requested_tool_call = {"type": "function_call", "call_id": "1", "name": "read_file", "arguments": '{"filename": "missing.txt"}'}
    model_responses = iter([SimpleNamespace(output=[requested_tool_call], output_text=""), text_response("Done")])
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: next(model_responses))
    agent.invoke("Read the file")

    assert agent.tool_registry["read_file"] is not TOOL_REGISTRY["read_file"]
    assert read_file_schema["parameters"]["required"] == ["filename"]
    assert read_file_schema["strict"] is False
    assert decorated_calls == [{"filename": "missing.txt"}]
    assert agent.tool_registry["custom"] is custom_tool


def test_execute_llm_call_forwards_tools_and_response_options(monkeypatch):
    request_options = {}
    monkeypatch.setattr("autom8.agent.responses", lambda **kwargs: request_options.update(kwargs) or text_response("A"))
    hosted_tool = {"type": "web_search", "search_context_size": "high"}
    response_format = {"type": "json_schema", "json_schema": {"name": "answer", "schema": {}, "strict": True}}
    agent = Agent(model="m", tool_registry={"custom": lambda: None}, parallel_tool_calls=False, hosted_tools=[hosted_tool])
    agent._execute_llm_call([{"role": "user", "content": "Q"}], "m", response_format)
    assert request_options["input"] == [{"role": "user", "content": "Q"}]
    assert request_options["max_output_tokens"] == 2000
    assert request_options["parallel_tool_calls"] is False
    assert request_options["text_format"] == response_format
    assert request_options["tools"][-1] == hosted_tool
    assert request_options["tools"][0]["type"] == "function"
    assert request_options["tools"][0]["name"] == "custom"


def test_invoke_records_user_and_assistant_messages(monkeypatch):
    agent = Agent(model="m", system_prompt="S", tool_registry={})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: text_response("A"))
    result = agent.invoke("Q")
    assert result.response == "A"
    assert result.tool_calls == []
    assert result.response_items == agent.sessions[0][-1:]
    assert agent.sessions[0][:2] == [{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}]
    assert agent.sessions[0][-1]["type"] == "message"


def test_invoke_resets_session_when_instructions_change(monkeypatch):
    agent = Agent(model="m", system_prompt="S", tool_registry={})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: text_response("A"))
    agent.invoke("one")
    agent.invoke("two", instructions="T")
    assert agent.sessions[0][0] == {"role": "system", "content": "T"}
    assert agent.sessions[0][1] == {"role": "user", "content": "two"}
    assert agent.sessions[0][-1]["content"][0]["text"] == "A"


def test_invoke_returns_typed_tool_results(monkeypatch):
    tool_result = ToolResult(type="image",
                             values=["/tmp/one.png", "/tmp/two.png"],
                             model_output={"status": "success", "message": "The images will be delivered separately."})

    def generate_images(prompt):
        return tool_result
    requested_tool_call = {"type": "function_call", "call_id": "1", "name": "generate_images", "arguments": '{"prompt": "mountains"}'}
    model_responses = iter([SimpleNamespace(output=[requested_tool_call], output_text=""), text_response("Done")])
    agent = Agent(model="m", tool_registry={"generate_images": generate_images})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: next(model_responses))
    result = agent.invoke("Generate two images")
    assert result.response == "Done"
    assert result.results("image") == ["/tmp/one.png", "/tmp/two.png"]
    assert result.tool_calls[0].name == "generate_images"
    assert result.tool_calls[0].arguments == {"prompt": "mountains"}
    assert result.tool_calls[0].result == tool_result
    assert agent.sessions[0][-2]["output"] == '{"status": "success", "message": "The images will be delivered separately."}'
    assert "/tmp/one.png" not in agent.sessions[0][-2]["output"]
    assert [response_item["type"] for response_item in result.response_items] == ["function_call", "message"]


def test_invoke_rejects_invalid_tool_result(monkeypatch):
    def search(query):
        return {"urls": ["https://example.com"]}
    requested_tool_call = {"type": "function_call", "call_id": "1", "name": "search", "arguments": '{"query": "example"}'}
    response = SimpleNamespace(output=[requested_tool_call], output_text="")
    agent = Agent(model="m", tool_registry={"search": search})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: response)
    with pytest.raises(TypeError, match="Tool 'search' must return ToolResult, got dict"):
        agent.invoke("Search")


def test_invoke_preserves_hosted_tool_items_and_citations(monkeypatch):
    citation = {"type": "url_citation", "start_index": 0, "end_index": 6, "title": "Source", "url": "https://example.com"}
    hosted_tool_call = {"type": "web_search_call", "id": "search-1", "status": "completed"}
    response = text_response("Answer", annotations=[citation])
    response.output.insert(0, hosted_tool_call)
    agent = Agent(model="m", tool_registry={}, hosted_tools=[{"type": "web_search"}])
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: response)
    result = agent.invoke("Search")
    assert result.response == "Answer"
    assert result.response_items[0] == hosted_tool_call
    assert result.response_items[1]["content"][0]["annotations"] == [citation]


def test_invoke_uses_responses_image_content(monkeypatch):
    captured_prompt = []
    agent = Agent(model="m", tool_registry={})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: captured_prompt.extend(prompt) or text_response("A"))
    agent.invoke("Describe", image_url="https://example.com/image.png")
    assert captured_prompt[1]["content"] == [{"type": "input_text", "text": "Describe"},
                                              {"type": "input_image", "image_url": "https://example.com/image.png"}]


def test_costs_include_all_model_calls_and_are_scoped_to_conversations(monkeypatch):
    def local_tool() -> ToolResult:
        return ToolResult(type="data", values=[], model_output="done")

    tool_request = {"type": "function_call", "call_id": "1", "name": "local_tool", "arguments": "{}"}
    first_response = SimpleNamespace(output=[tool_request], output_text="", _hidden_params={"response_cost": 0.01})
    second_response = text_response("Done")
    second_response._hidden_params = {"response_cost": 0.02}
    third_response = text_response("Again")
    third_response._hidden_params = {"response_cost": 0.03}
    model_responses = iter([first_response, second_response, third_response])
    agent = Agent(model="m", tool_registry={"local_tool": local_tool})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: next(model_responses))

    first_result = agent.invoke("Use the tool", chat_id=1)
    second_result = agent.invoke("Continue", chat_id=1)
    assert first_result.cost_usd == pytest.approx(0.03)
    assert first_result.conversation_cost_usd == pytest.approx(0.03)
    assert second_result.cost_usd == pytest.approx(0.03)
    assert second_result.conversation_cost_usd == pytest.approx(0.06)
    assert second_result.to_dict()["conversation_cost_usd"] == pytest.approx(0.06)

    other_response = text_response("Other")
    other_response._hidden_params = {"response_cost": 0.04}
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: other_response)
    assert agent.invoke("New conversation", chat_id=2).conversation_cost_usd == pytest.approx(0.04)
    agent.reset(1)
    assert agent.invoke("Restart", chat_id=1).conversation_cost_usd == pytest.approx(0.04)
    assert agent.invoke("Changed", chat_id=2, instructions="new").conversation_cost_usd == pytest.approx(0.04)


def test_missing_cost_does_not_report_partial_total(monkeypatch):
    agent = Agent(model="m", tool_registry={})
    known_response = text_response("Known")
    known_response._hidden_params = {"response_cost": 0.01}
    model_responses = iter([known_response, text_response("Unknown"), known_response])
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: next(model_responses))

    assert agent.invoke("First").conversation_cost_usd == pytest.approx(0.01)
    unknown_result = agent.invoke("Second")
    assert unknown_result.cost_usd is None
    assert unknown_result.conversation_cost_usd is None
    assert agent.invoke("Third").conversation_cost_usd is None


def test_invoke_calculates_cost_for_responses_api_usage(monkeypatch):
    response = ResponsesAPIResponse.model_construct(model="gpt-4o-mini", output=[],
                                                    usage=ResponseAPIUsage(input_tokens=100, output_tokens=50, total_tokens=150))
    agent = Agent(model="openai/gpt-4o-mini", tool_registry={})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: response)

    result = agent.invoke("Hello")
    assert response._hidden_params.get("response_cost") is None
    assert result.cost_usd == pytest.approx(0.000045)
    assert result.conversation_cost_usd == pytest.approx(0.000045)
