import asyncio
import inspect
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from mcp.types import CallToolResult, ListToolsResult, Tool

from autom8 import Agent, ToolResult, load_agent_config
from autom8.mcp_tools import MCPTools, _model_tool_name

SERVER_SCRIPT = Path(__file__).with_name("fixtures") / "mcp_server.py"


def stdio_config(**overrides):
    return {"transport": "stdio", "command": sys.executable, "args": [str(SERVER_SCRIPT)], **overrides}


@pytest.fixture
def http_server(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    request_log = tmp_path / "requests.log"
    server_environment = {**os.environ, "AUTOM8_TEST_TRANSPORT": "http", "AUTOM8_TEST_PORT": str(port),
                          "AUTOM8_TEST_REQUEST_LOG": str(request_log)}
    process = subprocess.Popen([sys.executable, str(SERVER_SCRIPT)], env=server_environment)
    try:
        deadline = time.monotonic() + 15
        while True:
            if process.poll() is not None:
                pytest.fail("HTTP test server exited before starting")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    pytest.fail("HTTP test server did not start")
                time.sleep(0.05)
        yield {"transport": "streamable_http", "url": f"http://127.0.0.1:{port}/mcp",
               "headers": {"Authorization": "Bearer test-token"}}, request_log
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_yaml_agent_uses_mcp_and_python_tools_without_api_changes(tmp_path, monkeypatch):
    config_path = tmp_path / "agents.yaml"
    config_path.write_text(yaml.safe_dump({"mcp_servers": {"calculator": stdio_config()},
                                          "agents": [{"id": "a", "model": "m", "system_prompt": "S", "mcp_tools": {"calculator": ["add"]}}]}))
    agent = Agent.from_config(load_agent_config(str(config_path)))
    local_calls = []

    def local_tool():
        local_calls.append(True)
        return ToolResult(type="data", values=["local"], model_output="local")

    agent.tool_registry["local"] = local_tool
    agent._tool_signatures["local"] = inspect.signature(local_tool)
    agent.tools = agent._build_tools()
    requests = []
    callbacks = []

    def fake_responses(**request):
        requests.append(request)
        step = (len(requests) - 1) % 3
        if step < 2:
            return SimpleNamespace(output=[{"type": "function_call", "call_id": str(step),
                                            "name": "calculator__add" if step == 0 else "local",
                                            "arguments": '{"left": 2, "right": 3}' if step == 0 else "{}"}], output_text="")
        return SimpleNamespace(output=[], output_text="5")

    monkeypatch.setattr("autom8.agent.responses", fake_responses)
    for _ in range(2):
        result = agent.invoke("Add two and three", on_tool_call=lambda name, arguments: callbacks.append((name, arguments)))
        assert result.response == "5"
        assert result.results("mcp")[0]["structuredContent"]["total"] == 5
        process_id = result.results("mcp")[0]["structuredContent"]["pid"]
        with pytest.raises(ProcessLookupError):
            os.kill(process_id, 0)
        assert not agent._mcp_tools.definitions
    definition = next(tool for tool in requests[0]["tools"] if tool["name"] == "calculator__add")
    assert definition["parameters"]["properties"]["left"]["type"] == "integer"
    assert definition["parameters"]["required"] == ["left"]
    assert definition["parameters"]["properties"]["right"]["default"] == 1
    assert len(callbacks) == 4
    assert local_calls == [True, True]
    assert [tool.name for tool in result.tool_calls] == ["calculator__add", "local"]


def test_streamable_http_headers_and_session_cleanup(http_server):
    server_config, request_log = http_server
    tools = MCPTools({"calculator": server_config}, {"calculator": ["add"]}, [])
    with tools.connect():
        assert tools.call("calculator__add", {"left": 4}).model_output["structuredContent"]["total"] == 5
    requests = request_log.read_text().splitlines()
    assert "DELETE Bearer test-token" in requests
    assert all(request.endswith("Bearer test-token") for request in requests)
    assert not tools.handles("calculator__add")


def test_tool_errors_and_binary_results_are_preserved():
    tools = MCPTools({"server": stdio_config()}, {"server": ["fail", "mixed"]}, [])
    with tools.connect():
        failure = tools.call("server__fail", {})
        assert failure.model_output["isError"] is True
        assert "deliberate tool failure" in failure.to_model_json()
        result = tools.call("server__mixed", {})
        assert result.values[0]["content"][1]["data"] == "aGVsbG8="
        assert result.values[0]["_meta"]["application_only"] == "private metadata"
        assert "aGVsbG8=" not in result.to_model_json()
        assert "private metadata" not in result.to_model_json()
        assert "An image" in result.to_model_json()


def test_connections_close_when_the_model_fails(monkeypatch):
    agent = Agent(model="m", tool_registry={}, mcp_servers={"server": stdio_config()}, mcp_tools={"server": ["add"]})
    process_ids = []

    def fail_response(**request):
        result = agent._mcp_tools.call("server__add", {"left": 1})
        process_ids.append(result.model_output["structuredContent"]["pid"])
        raise ValueError("model failed")

    monkeypatch.setattr("autom8.agent.responses", fail_response)
    with pytest.raises(ValueError, match="model failed"):
        agent.invoke("hello")
    with pytest.raises(ProcessLookupError):
        os.kill(process_ids[0], 0)
    assert not agent._mcp_tools.definitions


def test_request_timeout_disables_server_without_retrying(caplog):
    tools = MCPTools({"server": stdio_config(timeout_seconds=1)}, {"server": ["wait"]}, [])
    with tools.connect():
        result = tools.call("server__wait", {"seconds": 10})
        assert result.model_output["isError"] is True
        assert "Execution was not confirmed" in result.to_model_json()
        assert tools.definitions == []
        assert tools.call("server__wait", {"seconds": 0}).model_output["isError"] is True
    assert "server/wait" in caplog.text
    assert not tools._failed_servers


@pytest.mark.parametrize("selection, reserved_names, error", [(["missing"], [], "Unknown MCP tools"), (["add"], ["server__add"], "collision")])
def test_discovery_failures_cleanup_and_do_not_run_model(selection, reserved_names, error):
    tools = MCPTools({"server": stdio_config()}, {"server": selection}, reserved_names)
    with pytest.raises(ValueError, match=error):
        with tools.connect():
            pytest.fail("Invalid discovery must fail before calling the model")
    assert not tools.definitions
    assert not tools.handles("server__add")


def test_connection_failure_is_logged_and_omitted(caplog):
    tools = MCPTools({"missing": stdio_config(command="/autom8-missing-executable")}, {"missing": "*"}, [])
    with tools.connect():
        assert tools.definitions == []
        assert not tools.handles("missing__add")
    assert "MCP server 'missing' is unavailable" in caplog.text


def test_discovery_follows_pagination_and_preserves_nested_schema(monkeypatch):
    schema = {"type": "object",
              "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {"enabled": {"type": "boolean"}}}}}}
    cursors = []

    async def list_tools(*, params):
        cursors.append(params.cursor)
        return ListToolsResult(tools=[Tool(name="first" if params.cursor is None else "second", inputSchema=schema)],
                               nextCursor="page-2" if params.cursor is None else None)

    class Portal:
        def call(self, function, *arguments):
            return asyncio.run(function(*arguments))

    @contextmanager
    def fake_connect(server_configs):
        yield Portal(), {"server": SimpleNamespace(list_tools=list_tools)}

    monkeypatch.setattr("autom8.mcp_tools.connect_servers", fake_connect)
    tools = MCPTools({"server": {}}, {"server": "*"}, [])
    with tools.connect():
        assert cursors == [None, "page-2"]
        assert [definition["name"] for definition in tools.definitions] == ["server__first", "server__second"]
        assert tools.definitions[1]["parameters"] == schema


def test_model_tool_names_are_stable_and_distinct():
    names = [_model_tool_name("server", name) for name in ("search", "search.items", "search_items", "a" * 128, "a" * 127 + "b")]
    assert names[0] == "server__search"
    assert len(set(names)) == len(names)
    assert all(len(name) <= 64 for name in names)
    assert _model_tool_name("server", "search.items") == names[1]


def test_multiple_servers_have_distinct_tools_and_close_all_processes():
    tools = MCPTools({"first": stdio_config(), "second": stdio_config()}, {"first": ["add"], "second": ["add"]}, [])
    process_ids = []
    with tools.connect():
        for server_name in ("first", "second"):
            result = tools.call(f"{server_name}__add", {"left": 1})
            process_ids.append(result.model_output["structuredContent"]["pid"])
    assert len(set(process_ids)) == 2
    for process_id in process_ids:
        with pytest.raises(ProcessLookupError):
            os.kill(process_id, 0)


@pytest.mark.parametrize("server_order", [("missing", "first", "second"), ("first", "missing", "second"), ("first", "second", "missing")])
def test_partial_connection_failure_keeps_healthy_servers_and_cleans_up(server_order, caplog):
    server_configs = {name: stdio_config(command="/autom8-missing-executable") if name == "missing" else stdio_config() for name in server_order}
    tools = MCPTools(server_configs, {name: ["add"] for name in server_order}, [])
    process_ids = []
    with tools.connect():
        assert {definition["name"] for definition in tools.definitions} == {"first__add", "second__add"}
        for server_name in ("first", "second"):
            result = tools.call(f"{server_name}__add", {"left": 1})
            assert result.model_output["structuredContent"]["total"] == 2
            process_ids.append(result.values[0]["structuredContent"]["pid"])
    for process_id in process_ids:
        with pytest.raises(ProcessLookupError):
            os.kill(process_id, 0)
    assert "MCP server 'missing' is unavailable" in caplog.text
    assert not tools.definitions


@pytest.fixture
def fake_mcp_connection(monkeypatch):
    def configure(sessions):
        closed = []

        class Portal:
            def call(self, function, *arguments):
                return asyncio.run(function(*arguments))

        @contextmanager
        def fake_connect(server_configs):
            try:
                yield Portal(), sessions
            finally:
                closed.append(True)

        monkeypatch.setattr("autom8.mcp_tools.connect_servers", fake_connect)
        return closed
    return configure


@pytest.mark.parametrize("content, expected", [
    ({"type": "text", "text": "Public text", "_meta": {"private_token": "text-secret"}, "extension": "application-only"},
     {"type": "text", "text": "Public text"}),
    ({"type": "resource_link", "uri": "https://example.com/document", "name": "document", "title": "Document",
      "description": "Public document", "mimeType": "text/plain", "size": 10, "_meta": {"private_token": "link-secret"},
      "icons": [{"src": "https://example.com/private-icon?token=icon-secret"}], "extension": "application-only"},
     {"type": "resource_link", "uri": "https://example.com/document", "name": "document", "title": "Document",
      "description": "Public document", "mimeType": "text/plain", "size": 10}),
    ({"type": "resource", "_meta": {"private_token": "block-secret"}, "extension": "application-only",
      "resource": {"uri": "https://example.com/document", "mimeType": "text/plain", "text": "Public document",
                   "_meta": {"private_token": "resource-secret"}, "extension": "application-only"}},
     {"type": "resource", "resource": {"uri": "https://example.com/document", "mimeType": "text/plain", "text": "Public document"}})])
def test_content_metadata_stays_in_application_results(fake_mcp_connection, content, expected):
    response = CallToolResult.model_validate({"content": [content], "_meta": {"private_token": "result-secret"},
                                              "structuredContent": {"_meta": "legitimate result data"}})

    async def list_tools(*, params):
        return ListToolsResult(tools=[Tool(name="read", inputSchema={"type": "object"})])

    async def call_tool(name, arguments):
        return response

    closed = fake_mcp_connection({"server": SimpleNamespace(list_tools=list_tools, call_tool=call_tool)})
    tools = MCPTools({"server": {}}, {"server": ["read"]}, [])
    with tools.connect():
        result = tools.call("server__read", {})
    assert result.model_output["content"] == [expected]
    assert result.model_output["structuredContent"] == {"_meta": "legitimate result data"}
    assert result.values[0] == response.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert result.values[0]["content"][0]["_meta"] == content["_meta"]
    assert "private_token" not in result.to_model_json()
    assert "application-only" not in result.to_model_json()
    assert closed == [True]


@pytest.mark.parametrize("failure_page", [None, "page-2"])
def test_discovery_errors_are_logged_and_omit_all_server_tools(fake_mcp_connection, failure_page, caplog):
    discovery_error = TimeoutError("discovery timed out")
    cursors = []

    async def first_list_tools(*, params):
        return ListToolsResult(tools=[Tool(name="first", inputSchema={"type": "object"})])

    async def second_list_tools(*, params):
        cursors.append(params.cursor)
        if params.cursor == failure_page:
            raise discovery_error
        return ListToolsResult(tools=[Tool(name="second", inputSchema={"type": "object"})], nextCursor="page-2")

    closed = fake_mcp_connection({"first": SimpleNamespace(list_tools=first_list_tools), "second": SimpleNamespace(list_tools=second_list_tools)})
    tools = MCPTools({"first": {}, "second": {}}, {"first": "*", "second": "*"}, [])
    with tools.connect():
        assert [definition["name"] for definition in tools.definitions] == ["first__first"]
        assert not tools.handles("second__second")
    assert "Could not discover tools on MCP server 'second'" in caplog.text
    assert cursors == ([None] if failure_page is None else [None, "page-2"])
    assert not tools.definitions
    assert not tools.handles("first__first")
    assert closed == [True]


def test_agent_continues_with_python_tools_when_all_servers_fail_and_recovers(monkeypatch, caplog):
    def local_tool():
        return ToolResult(type="data", values=["local"], model_output="local")

    agent = Agent(model="m", tool_registry={"local": local_tool},
                  mcp_servers={"server": stdio_config(command="/autom8-missing-executable")}, mcp_tools={"server": ["add"]})
    requests = []

    def fake_responses(**request):
        requests.append(request)
        if len(requests) == 1:
            assert [tool["name"] for tool in request["tools"]] == ["local"]
            assert "unavailable" not in str(request["input"])
            return SimpleNamespace(output=[{"type": "function_call", "call_id": "local-1", "name": "local", "arguments": "{}"}], output_text="")
        return SimpleNamespace(output=[], output_text="Done")

    monkeypatch.setattr("autom8.agent.responses", fake_responses)
    result = agent.invoke("Hello")
    assert result.response == "Done"
    assert result.results("data") == ["local"]
    assert "MCP server 'server' is unavailable" in caplog.text
    agent._mcp_tools.server_configs["server"] = stdio_config()
    agent.invoke("Again")
    assert {tool["name"] for tool in requests[-1]["tools"]} == {"local", "server__add"}


def test_mid_invocation_failure_keeps_healthy_tools_and_does_not_retry(fake_mcp_connection, monkeypatch, caplog):
    failed_calls = []

    async def list_tools(*, params):
        return ListToolsResult(tools=[Tool(name="run", inputSchema={"type": "object"})])

    async def broken_call(name, arguments):
        failed_calls.append(name)
        raise ConnectionError("private connection details")

    async def healthy_call(name, arguments):
        return CallToolResult(content=[{"type": "text", "text": "healthy result"}])

    closed = fake_mcp_connection({"broken": SimpleNamespace(list_tools=list_tools, call_tool=broken_call),
                                  "healthy": SimpleNamespace(list_tools=list_tools, call_tool=healthy_call)})
    agent = Agent(model="m", tool_registry={}, mcp_servers={"broken": {}, "healthy": {}}, mcp_tools={"broken": "*", "healthy": "*"})
    request_count = 0

    def fake_responses(**request):
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return SimpleNamespace(output=[{"type": "function_call", "call_id": str(index), "name": name, "arguments": "{}"}
                                           for index, name in enumerate(("broken__run", "broken__run", "healthy__run"))], output_text="")
        assert [tool["name"] for tool in request["tools"]] == ["healthy__run"]
        assert "private connection details" not in str(request["input"])
        return SimpleNamespace(output=[], output_text="Done")

    monkeypatch.setattr("autom8.agent.responses", fake_responses)
    result = agent.invoke("Run tools")
    assert result.response == "Done"
    assert failed_calls == ["run"]
    assert [call.result.model_output["isError"] for call in result.tool_calls] == [True, True, False]
    assert "broken/run" in caplog.text
    assert closed == [True]


def test_cleanup_failure_is_logged_and_does_not_mask_model_errors(monkeypatch, caplog):
    from autom8.mcp_client import connect_servers

    closed = []

    @contextmanager
    def fake_connection(server_config):
        try:
            yield object()
        finally:
            closed.append(server_config["name"])
            if server_config["name"] == "broken":
                raise ConnectionError("cleanup failed")

    monkeypatch.setattr("autom8.mcp_client._connect_server", fake_connection)

    class Portal:
        def wrap_async_context_manager(self, connection):
            return connection

    @contextmanager
    def fake_portal():
        yield Portal()

    monkeypatch.setattr("autom8.mcp_client.start_blocking_portal", fake_portal)
    for model_error in (False, True):
        try:
            with connect_servers({"healthy": {"name": "healthy"}, "broken": {"name": "broken"}}):
                if model_error:
                    raise ValueError("model failed")
        except ValueError as exception:
            assert model_error
            assert str(exception) == "model failed"
        else:
            assert not model_error
    assert closed == ["broken", "healthy", "broken", "healthy"]
    assert "Could not close MCP server 'broken' cleanly" in caplog.text
