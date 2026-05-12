import importlib
from pathlib import Path
from typing import Any, Dict

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

    return {
        "id": selected_agent.get("id"),
        "model": selected_agent.get("model", defaults.get("model", "gpt-5")),
        "system_prompt": system_prompt,
        "tool_registry": tool_registry,
        "max_completion_tokens": defaults.get("max_completion_tokens", 2000),
        "tool_choice": defaults.get("tool_choice", "auto"),
    }
