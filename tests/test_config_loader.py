import pytest

from autom8 import load_agent_config


def test_load_agent_config_uses_defaults_and_selected_agent(tmp_path):
    path = tmp_path / "agents.yaml"
    path.write_text("defaults:\n  model: m\n  parallel_tool_calls: false\nagents:\n  - id: a\n    system_prompt: A\n  - id: b\n    system_prompt: B\n", encoding="utf-8")
    config = load_agent_config(str(path), "b")
    assert config["id"] == "b"
    assert config["model"] == "m"
    assert config["system_prompt"] == "B"
    assert config["parallel_tool_calls"] is False


def test_load_agent_config_rejects_unknown_agent_id(tmp_path):
    path = tmp_path / "agents.yaml"
    path.write_text("agents:\n  - id: a\n    system_prompt: A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Agent 'b' was not found"):
        load_agent_config(str(path), "b")
