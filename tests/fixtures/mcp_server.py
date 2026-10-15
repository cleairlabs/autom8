"""A real SDK server used by the stdio and HTTP integration tests."""
import os
from pathlib import Path

import anyio
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent

server = FastMCP("autom8-test", json_response=True, log_level="ERROR")


@server.tool()
def add(left: int, right: int = 1) -> dict[str, int]:
    """Add two integers."""
    return {"total": left + right, "pid": os.getpid()}


@server.tool()
def fail() -> str:
    """Return a tool execution error."""
    raise ValueError("deliberate tool failure")


@server.tool()
async def wait(seconds: float) -> str:
    """Wait long enough to exercise request timeouts."""
    await anyio.sleep(seconds)
    return "finished"


@server.tool()
def mixed() -> CallToolResult:
    """Return text, an image, and application metadata."""
    return CallToolResult(content=[TextContent(type="text", text="An image"), ImageContent(type="image", data="aGVsbG8=", mimeType="image/png")],
                          _meta={"application_only": "private metadata"})


if __name__ == "__main__":
    if os.environ.get("AUTOM8_TEST_TRANSPORT") == "http":
        import uvicorn
        application = server.streamable_http_app()

        async def record_requests(scope, receive, send):
            if scope["type"] == "http":
                authorization = dict(scope["headers"]).get(b"authorization", b"").decode()
                with Path(os.environ["AUTOM8_TEST_REQUEST_LOG"]).open("a") as request_log:
                    request_log.write(f"{scope['method']} {authorization}\n")
            await application(scope, receive, send)

        uvicorn.run(record_requests, host="127.0.0.1", port=int(os.environ["AUTOM8_TEST_PORT"]), log_level="error")
    else:
        server.run()
