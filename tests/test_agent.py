from types import SimpleNamespace

import pytest

from autom8 import Agent


def test_invoke_requires_model():
    agent = Agent(tool_registry={})
    with pytest.raises(ValueError, match="No model specified"):
        agent.invoke("hello")


def test_invoke_records_user_and_assistant_messages(monkeypatch):
    agent = Agent(model="m", system_prompt="S", tool_registry={})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: SimpleNamespace(content="A", tool_calls=None))
    assert agent.invoke("Q") == "A"
    assert agent.sessions[0] == [{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}, {"role": "assistant", "content": "A"}]


def test_invoke_resets_session_when_instructions_change(monkeypatch):
    agent = Agent(model="m", system_prompt="S", tool_registry={})
    monkeypatch.setattr(agent, "_execute_llm_call", lambda prompt, model, response_format: SimpleNamespace(content="A", tool_calls=None))
    agent.invoke("one")
    agent.invoke("two", instructions="T")
    assert agent.sessions[0][0] == {"role": "system", "content": "T"}
    assert [message["content"] for message in agent.sessions[0]] == ["T", "two", "A"]
