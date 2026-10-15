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


def test_load_mcp_config_expands_selected_server_environment(tmp_path, monkeypatch):
    import yaml
    monkeypatch.setenv("AUTOM8_TEST_TOKEN", "test-secret")
    path = tmp_path / "agents.yaml"
    path.write_text(yaml.safe_dump({"mcp_servers": {"issues": {"transport": "streamable_http", "url": "https://example.com/mcp",
                                                              "headers": {"Authorization": "Bearer ${AUTOM8_TEST_TOKEN}"}},
                                                   "unused": {"transport": "stdio", "command": "${AUTOM8_UNSET_COMMAND}"}},
                                    "agents": [{"id": "a", "system_prompt": "S", "mcp_tools": {"issues": ["search"]}},
                                               {"id": "b", "system_prompt": "S"}]}))
    config = load_agent_config(str(path), "a")
    assert config["mcp_tools"] == {"issues": ["search"]}
    assert list(config["mcp_servers"]) == ["issues"]
    assert config["mcp_servers"]["issues"]["headers"] == {"Authorization": "Bearer test-secret"}
    assert load_agent_config(str(path), "b")["mcp_servers"] == {}


@pytest.mark.parametrize("server_config, selection, error", [
    ({"transport": "stdio", "command": "python"}, "*", None),
    ({"transport": "stdio", "command": "python"}, [], None),
    ({"transport": "invalid"}, "*", "transport"),
    ({"transport": "stdio"}, "*", "command"),
    ({"transport": "streamable_http", "url": "file:///tmp/mcp"}, "*", "HTTP"),
    ({"transport": "stdio", "command": "python", "args": "server.py"}, "*", "args"),
    ({"transport": "stdio", "command": "python", "env": {"TOKEN": 123}}, "*", "env"),
    ({"transport": "stdio", "command": "python", "headers": []}, "*", "headers"),
    ({"transport": "stdio", "command": "python", "timeout_seconds": 0}, "*", "timeout_seconds"),
    ({"transport": "stdio", "command": "python", "timeout_seconds": True}, "*", "timeout_seconds"),
    ({"transport": "stdio", "command": "python", "timeout_seconds": float("inf")}, "*", "timeout_seconds"),
    ({"transport": "stdio", "command": "python"}, "add", "list of tool names"),
    ({"transport": "stdio", "command": "python"}, [123], "list of tool names")])
def test_load_mcp_config_validation(tmp_path, server_config, selection, error):
    import yaml
    path = tmp_path / "agents.yaml"
    path.write_text(yaml.safe_dump({"mcp_servers": {"server": server_config},
                                    "agents": [{"system_prompt": "S", "mcp_tools": {"server": selection}}]}))
    if error:
        with pytest.raises(ValueError, match=error):
            load_agent_config(str(path))
    else:
        config = load_agent_config(str(path))
        assert bool(config["mcp_servers"]) == bool(selection)


def test_load_mcp_config_rejects_unknown_server_and_missing_environment(tmp_path, monkeypatch):
    import yaml
    monkeypatch.delenv("AUTOM8_UNSET_COMMAND", raising=False)
    path = tmp_path / "agents.yaml"
    configuration = {"agents": [{"system_prompt": "S", "mcp_tools": {"missing": "*"}}]}
    path.write_text(yaml.safe_dump(configuration))
    with pytest.raises(ValueError, match="Unknown MCP server"):
        load_agent_config(str(path))
    configuration["mcp_servers"] = {"missing": {"transport": "stdio", "command": "${AUTOM8_UNSET_COMMAND}"}}
    path.write_text(yaml.safe_dump(configuration))
    with pytest.raises(ValueError, match="Missing environment variable 'AUTOM8_UNSET_COMMAND'"):
        load_agent_config(str(path))


@pytest.mark.parametrize("timeout", [0, -1, True, "10", float("inf"), float("nan")])
def test_load_mcp_config_validates_startup_timeout(tmp_path, timeout):
    import yaml
    path = tmp_path / "agents.yaml"
    path.write_text(yaml.safe_dump({"mcp_servers": {"server": {"transport": "stdio", "command": "python", "startup_timeout_seconds": timeout}},
                                    "agents": [{"system_prompt": "S", "mcp_tools": {"server": "*"}}]}))
    with pytest.raises(ValueError, match="startup_timeout_seconds"):
        load_agent_config(str(path))


def test_load_mcp_config_ignores_unselected_and_disabled_server_values(tmp_path, monkeypatch):
    import yaml
    monkeypatch.delenv("AUTOM8_UNUSED_TOKEN", raising=False)
    path = tmp_path / "agents.yaml"
    path.write_text(yaml.safe_dump({"mcp_servers": {"selected": {"transport": "stdio", "command": "python", "startup_timeout_seconds": 2},
                                                    "unused": {"transport": "invalid", "env": {"TOKEN": "${AUTOM8_UNUSED_TOKEN}"}},
                                                    "disabled": {"transport": "stdio", "command": "${AUTOM8_UNUSED_TOKEN}"}},
                                    "agents": [{"system_prompt": "S", "mcp_tools": {"selected": ["add"], "disabled": []}}]}))
    config = load_agent_config(str(path))
    assert config["mcp_servers"] == {"selected": {"transport": "stdio", "command": "python", "startup_timeout_seconds": 2}}
    assert config["mcp_tools"] == {"selected": ["add"]}
