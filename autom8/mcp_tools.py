import logging
import re
from contextlib import contextmanager
from functools import partial
from hashlib import sha256
from typing import Any

from mcp.types import PaginatedRequestParams

from .mcp_client import connect_servers
from .results import ToolResult


logger = logging.getLogger("autom8.mcp")


def _model_tool_name(server_name: str, tool_name: str) -> str:
    original_name = f"{server_name}__{tool_name}"
    model_name = re.sub(r"[^a-zA-Z0-9_-]", "_", original_name)
    if model_name != original_name or len(model_name) > 64:
        model_name = f"{model_name[:51]}_{sha256(original_name.encode()).hexdigest()[:12]}"
    return model_name


class MCPTools:
    def __init__(self, server_configs: dict[str, dict[str, Any]], tool_selection: dict[str, Any], reserved_names):
        self.server_configs = {server_name: server_configs[server_name] for server_name, selected_tools in tool_selection.items() if selected_tools}
        self.tool_selection = tool_selection
        self.reserved_names = set(reserved_names)
        self.definitions: list[dict[str, Any]] = []
        self._routes: dict[str, Any] = {}
        self._portal = None
        self._failed_servers: set[str] = set()

    @contextmanager
    def connect(self):
        if not self.server_configs:
            yield self
            return
        try:
            with connect_servers(self.server_configs) as (portal, sessions):
                self._portal = portal
                for server_name, session in sessions.items():
                    discovered_tools = []
                    cursor = None
                    try:
                        while True:
                            page = portal.call(partial(session.list_tools, params=PaginatedRequestParams(cursor=cursor)))
                            discovered_tools.extend(page.tools)
                            cursor = page.nextCursor
                            if not cursor:
                                break
                    except Exception:
                        logger.warning("Could not discover tools on MCP server '%s'; continuing without its tools.", server_name)
                        logger.debug("MCP discovery failed for '%s'", server_name, exc_info=True)
                        continue
                    selected_tools = self.tool_selection[server_name]
                    if selected_tools != "*":
                        missing_tools = set(selected_tools) - {tool.name for tool in discovered_tools}
                        if missing_tools:
                            raise ValueError(f"Unknown MCP tools on server '{server_name}': {', '.join(sorted(missing_tools))}")
                    for tool in discovered_tools:
                        if selected_tools != "*" and tool.name not in selected_tools:
                            continue
                        model_name = _model_tool_name(server_name, tool.name)
                        if model_name in self.reserved_names or model_name in self._routes:
                            raise ValueError(f"MCP tool name collision: '{model_name}'")
                        self._routes[model_name] = (server_name, session, tool.name)
                        self.definitions.append({"type": "function", "name": model_name, "description": tool.description or "",
                                                 "parameters": tool.inputSchema, "strict": False})
                yield self
        finally:
            self.definitions.clear()
            self._routes.clear()
            self._failed_servers.clear()
            self._portal = None

    def handles(self, tool_name: str) -> bool:
        return tool_name in self._routes

    def call(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        server_name, session, original_name = self._routes[tool_name]
        failure_output = {"content": [{"type": "text", "text": "Tool unavailable. Execution was not confirmed; do not assume it had no effect."}],
                          "isError": True}
        if server_name in self._failed_servers:
            return ToolResult(type="mcp", values=[failure_output], model_output=failure_output)
        try:
            result = self._portal.call(session.call_tool, original_name, arguments)
        except Exception:
            logger.warning("MCP call '%s/%s' failed; continuing without this server's tools.", server_name, original_name)
            logger.debug("MCP tool call failed for '%s/%s'", server_name, original_name, exc_info=True)
            self._failed_servers.add(server_name)
            self.definitions[:] = [definition for definition in self.definitions if self._routes[definition["name"]][0] != server_name]
            return ToolResult(type="mcp", values=[failure_output], model_output=failure_output)
        raw_result = result.model_dump(mode="json", by_alias=True, exclude_none=True)
        model_content = []
        for content in raw_result["content"]:
            if content["type"] == "text":
                model_content.append({"type": "text", "text": content["text"]})
            elif content["type"] == "resource_link":
                resource_link_fields = ("type", "uri", "name", "title", "description", "mimeType", "size")
                model_content.append({field: content[field] for field in resource_link_fields if field in content})
            elif content["type"] == "resource" and "text" in content["resource"]:
                resource = content["resource"]
                model_content.append({"type": "resource",
                                      "resource": {field: resource[field] for field in ("uri", "mimeType", "text") if field in resource}})
            else:
                model_content.append({"type": "text", "text": f"MCP returned {content['type']} content, available to the application separately."})
        model_output = {"content": model_content, "isError": result.isError}
        if result.structuredContent is not None:
            model_output["structuredContent"] = result.structuredContent
        return ToolResult(type="mcp", values=[raw_result], model_output=model_output)
