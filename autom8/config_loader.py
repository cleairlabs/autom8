from pathlib import Path
from typing import Any, Dict

import yaml

from .tools import TOOL_REGISTRY


def load_agent_config(path: str, agent_id: str | None = None) -> Dict[str, Any]:
    with open(Path(path), "r", encoding="utf-8") as file_handle:
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
    tool_registry = {}
    for tool_name in tool_names:
        if tool_name not in TOOL_REGISTRY:
            raise ValueError(f"Unknown tool '{tool_name}' in agent_config.yaml")
        tool_registry[tool_name] = TOOL_REGISTRY[tool_name]

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
