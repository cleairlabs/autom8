import importlib
import math
import os
import re
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlsplit

import yaml

from .tools import TOOL_REGISTRY


def _load_custom_tool(tool_name: str, tool_path: str) -> Any:
    module_path, separator, function_name = tool_path.partition(":")
    if not separator or not module_path or not function_name:
        raise ValueError(f"Custom tool '{tool_name}' must use 'module:function' format")

    if module_path.endswith(".py") or module_path.startswith(".") or module_path.startswith("/"):
        raise ValueError(f"Custom tool '{tool_name}' must use an importable module path, not a file path")

    module = importlib.import_module(module_path)
    tool = getattr(module, function_name, None)
    if tool is None:
        raise ValueError(f"Custom tool '{tool_name}' function was not found: {tool_path}")
    if not callable(tool):
        raise ValueError(f"Custom tool '{tool_name}' is not callable: {tool_path}")
    return tool


def _load_mcp_config(raw_config: Dict[str, Any], selected_agent: Dict[str, Any]) -> tuple[dict, dict]:
    servers = raw_config.get("mcp_servers", {})
    tool_selection = selected_agent.get("mcp_tools", {})
    if not isinstance(servers, dict) or not isinstance(tool_selection, dict):
        raise ValueError("mcp_servers and mcp_tools must be mappings")

    def expand_environment(value: str) -> str:
        def replace_variable(match):
            variable_name = match.group(1)
            if variable_name not in os.environ:
                raise ValueError(f"Missing environment variable '{variable_name}' in MCP configuration")
            return os.environ[variable_name]
        return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", replace_variable, value)

    selected_servers = {}
    for server_name, selected_tools in tool_selection.items():
        if not isinstance(server_name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", server_name):
            raise ValueError("MCP server names must contain only letters, numbers, underscores, and hyphens")
        if selected_tools != "*" and (not isinstance(selected_tools, list) or any(not isinstance(name, str) or not name for name in selected_tools)):
            raise ValueError(f"mcp_tools for '{server_name}' must be a list of tool names or '*'")
        if server_name not in servers:
            raise ValueError(f"Unknown MCP server '{server_name}'")
        if not selected_tools:
            continue
        server_config = servers[server_name]
        if not isinstance(server_config, dict) or server_config.get("transport") not in ("stdio", "streamable_http"):
            raise ValueError(f"MCP server '{server_name}' must specify transport: stdio or streamable_http")
        server_config = dict(server_config)
        timeout_seconds = server_config.get("timeout_seconds", 60)
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
            raise ValueError(f"MCP server '{server_name}' timeout_seconds must be a positive finite number")
        required_field = "command" if server_config["transport"] == "stdio" else "url"
        if not isinstance(server_config.get(required_field), str) or not server_config[required_field]:
            raise ValueError(f"MCP server '{server_name}' requires '{required_field}'")
        server_config[required_field] = expand_environment(server_config[required_field])
        if required_field == "url":
            parsed_url = urlsplit(server_config["url"])
            if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
                raise ValueError(f"MCP server '{server_name}' url must be an HTTP or HTTPS URL")
        arguments = server_config.get("args", [])
        if not isinstance(arguments, list) or any(not isinstance(argument, str) for argument in arguments):
            raise ValueError(f"MCP server '{server_name}' args must be a list of strings")
        if "args" in server_config:
            server_config["args"] = [expand_environment(argument) for argument in arguments]
        if "cwd" in server_config:
            if not isinstance(server_config["cwd"], str):
                raise ValueError(f"MCP server '{server_name}' cwd must be a string")
            server_config["cwd"] = expand_environment(server_config["cwd"])
        for field_name in ("env", "headers"):
            values = server_config.get(field_name, {})
            if not isinstance(values, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in values.items()):
                raise ValueError(f"MCP server '{server_name}' {field_name} must be a mapping of strings")
            if field_name in server_config:
                server_config[field_name] = {key: expand_environment(value) for key, value in values.items()}
        selected_servers[server_name] = server_config
    return selected_servers, {name: tools for name, tools in tool_selection.items() if tools}


def load_agent_config(path: str, agent_id: str | None = None) -> Dict[str, Any]:
    config_path = Path(path)
    with open(config_path, "r", encoding="utf-8") as file_handle:
        raw_config = yaml.safe_load(file_handle) or {}

    defaults = raw_config.get("defaults", {})
    agents = raw_config.get("agents", [])
    if not agents:
        raise ValueError("agent_config.yaml must contain at least one agent")

    selected_agent = None
    if agent_id is None:
        selected_agent = agents[0]
    else:
        for candidate_agent in agents:
            if candidate_agent.get("id") == agent_id:
                selected_agent = candidate_agent
                break
        if selected_agent is None:
            raise ValueError(f"Agent '{agent_id}' was not found in agent_config.yaml")

    tool_names = selected_agent.get("tool_names", [])
    custom_tools = raw_config.get("custom_tools", {})
    if not isinstance(custom_tools, dict):
        raise ValueError("agent_config.yaml custom_tools must be a mapping of tool names to import paths")

    available_tools = dict(TOOL_REGISTRY)
    for tool_name in tool_names:
        if tool_name in TOOL_REGISTRY:
            continue
        if tool_name not in custom_tools:
            continue
        tool_path = custom_tools[tool_name]
        if not isinstance(tool_path, str):
            raise ValueError(f"Custom tool '{tool_name}' must define a string import path")
        available_tools[tool_name] = _load_custom_tool(tool_name, tool_path)

    tool_registry = {}
    for tool_name in tool_names:
        if tool_name not in available_tools:
            raise ValueError(f"Unknown tool '{tool_name}' in agent_config.yaml")
        tool_registry[tool_name] = available_tools[tool_name]

    system_prompt = selected_agent.get("system_prompt")
    if not system_prompt:
        raise ValueError("Each agent in agent_config.yaml must define system_prompt")

    hosted_tools = selected_agent.get("hosted_tools", defaults.get("hosted_tools", []))
    if not isinstance(hosted_tools, list):
        raise ValueError("hosted_tools must be a list")
    for hosted_tool in hosted_tools:
        if not isinstance(hosted_tool, dict) or not isinstance(hosted_tool.get("type"), str) or not hosted_tool["type"]:
            raise ValueError("Every hosted tool must be a mapping with a non-empty string type")

    mcp_servers, mcp_tools = _load_mcp_config(raw_config, selected_agent)

    return {
        "mcp_servers": mcp_servers,
        "mcp_tools": mcp_tools,
        "id": selected_agent.get("id"),
        "model": selected_agent.get("model", defaults.get("model", "openai/gpt-5")),
        "system_prompt": system_prompt,
        "tool_registry": tool_registry,
        "max_completion_tokens": defaults.get("max_completion_tokens", 2000),
        "tool_choice": defaults.get("tool_choice", "auto"),
        "reasoning_effort": defaults.get("reasoning_effort"),
        "parallel_tool_calls": defaults.get("parallel_tool_calls"),
        "hosted_tools": [dict(hosted_tool) for hosted_tool in hosted_tools],
    }
