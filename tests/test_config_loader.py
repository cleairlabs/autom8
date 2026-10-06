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


def test_load_agent_config_reads_optional_reasoning_effort(tmp_path):
    path = tmp_path / "agents.yaml"
    path.write_text("defaults:\n  reasoning_effort: medium\nagents:\n  - id: a\n    system_prompt: A\n", encoding="utf-8")
    config = load_agent_config(str(path))
    assert config["reasoning_effort"] == "medium"


def test_load_agent_config_reads_hosted_tools_from_defaults_and_agent(tmp_path):
    path = tmp_path / "agents.yaml"
    yaml_config = ("defaults:\n  hosted_tools:\n    - type: web_search\nagents:\n  - id: a\n    system_prompt: A\n"
                   "  - id: b\n    system_prompt: B\n    hosted_tools: []\n")
    path.write_text(yaml_config, encoding="utf-8")
    assert load_agent_config(str(path), "a")["hosted_tools"] == [{"type": "web_search"}]
    assert load_agent_config(str(path), "b")["hosted_tools"] == []


@pytest.mark.parametrize("hosted_tools", ["web_search", [{}], [{"type": ""}]])
def test_load_agent_config_rejects_invalid_hosted_tools(tmp_path, hosted_tools):
    path = tmp_path / "agents.yaml"
    path.write_text(f"agents:\n  - id: a\n    system_prompt: A\n    hosted_tools: {hosted_tools!r}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hosted_tools|Every hosted tool"):
        load_agent_config(str(path))


def test_load_agent_config_rejects_unknown_agent_id(tmp_path):
    path = tmp_path / "agents.yaml"
    path.write_text("agents:\n  - id: a\n    system_prompt: A\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Agent 'b' was not found"):
        load_agent_config(str(path), "b")
