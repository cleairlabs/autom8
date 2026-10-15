from contextlib import AsyncExitStack, ExitStack, asynccontextmanager, contextmanager
from datetime import timedelta
import logging
from typing import Any

import anyio
import httpx
from anyio.from_thread import start_blocking_portal
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


logger = logging.getLogger("autom8.mcp")
logger.addHandler(logging.NullHandler())


@asynccontextmanager
async def _connect_server(server_config: dict[str, Any]):
    timeout_seconds = server_config.get("timeout_seconds", 60)
    async with AsyncExitStack() as connection_stack:
        if server_config["transport"] == "stdio":
            parameters = StdioServerParameters(command=server_config["command"], args=server_config.get("args", []),
                                               env=server_config.get("env"), cwd=server_config.get("cwd"))
            streams = await connection_stack.enter_async_context(stdio_client(parameters))
        else:
            http_client = await connection_stack.enter_async_context(httpx.AsyncClient(headers=server_config.get("headers"), timeout=timeout_seconds))
            streams = await connection_stack.enter_async_context(streamable_http_client(server_config["url"], http_client=http_client))
        session = await connection_stack.enter_async_context(ClientSession(streams[0], streams[1],
                                                                          read_timeout_seconds=timedelta(seconds=timeout_seconds)))
        with anyio.fail_after(server_config.get("startup_timeout_seconds", 10)):
            initialization = await session.initialize()
        if initialization.capabilities.tools is None:
            raise ValueError("MCP server does not advertise tool support")
        yield session


@contextmanager
def connect_servers(server_configs: dict[str, dict[str, Any]]):
    """Keep SDK contexts in one async task and expose them to synchronous callers."""
    with start_blocking_portal() as portal:
        connection_stack = ExitStack()
        try:
            def close_connection(server_name, connection):
                try:
                    connection.__exit__(None, None, None)
                except Exception:
                    logger.warning("Could not close MCP server '%s' cleanly.", server_name)
                    logger.debug("MCP cleanup failed for '%s'", server_name, exc_info=True)

            sessions = {}
            for server_name, server_config in server_configs.items():
                try:
                    connection = portal.wrap_async_context_manager(_connect_server(server_config))
                    sessions[server_name] = connection.__enter__()
                    connection_stack.callback(close_connection, server_name, connection)
                except Exception:
                    logger.warning("MCP server '%s' is unavailable; continuing without its tools.", server_name)
                    logger.debug("MCP connection failed for '%s'", server_name, exc_info=True)
            yield portal, sessions
        finally:
            # Close normally so SDK task groups do not wrap errors from the caller.
            connection_stack.close()
