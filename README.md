<div align='center'>
    <picture>
        <source media="(prefers-color-scheme: light)" srcset="docs/autom8-lightmode-logo.png">
        <img alt="autom8 logo" src="docs/autom8-darkmode-logo.png" width="30%" height="50%">
    </picture>
</div>

[![Pytests](https://github.com/cleairlabs/autom8/actions/workflows/pytests.yml/badge.svg)](https://github.com/cleairlabs/autom8/actions/workflows/pytests.yml)


Autom8 is a framework for building AI agents.
It uses LiteLLM's Responses interface for model calls, so models are selected with provider-prefixed names like `openai/gpt-5`, `anthropic/claude-sonnet-4-5`, `mistral/mistral-large-latest`, or `gemini/gemini-2.0-flash`.

## Table of contents

- [Install from GitHub](#install-from-github)
- [Agent config reference](#agent-config-reference)
- [MCP tools](#mcp-tools)
- [Autom8 Built-in tools](#autom8-built-in-tools)
- [Observability](#observability)

## Install from GitHub

Install directly from GitHub with `pip`:
```bash
pip install git+https://github.com/cleairlabs/autom8.git
```

If you install from GitHub, create your own script and pass an explicit path to your YAML config when calling `load_agent_config(...)`.
If you clone the repository locally, a runnable example script and sample config are included in `examples/`.

Example:
```python
from autom8 import Agent, load_agent_config

agent_config = load_agent_config("agent_config.yaml")
agent = Agent.from_config(agent_config)
```

Or with multiple agents:
```python
from autom8 import Agent, load_agent_config

researcher_config = load_agent_config("agents.yaml", agent_id="researcher")
researcher = Agent.from_config(researcher_config)

coder_config = load_agent_config("agents.yaml", agent_id="coder")
coder = Agent.from_config(coder_config)
```

For direct usage without YAML, pass the model to `invoke(...)`:

```python
from autom8 import Agent

agent = Agent()
result = agent.invoke("Hello", model="openai/gpt-5")
print(result.response)
```

Set `model` when most calls should use the same model:

```python
agent = Agent(model="openai/gpt-5")
agent.invoke("Hello")
agent.invoke("Hello", model="anthropic/claude-sonnet-4-5")
```

`Agent.invoke(...)` returns an `AgentResult` containing the final response and any Python or MCP tool calls made while producing it.
The `response_items` field contains the typed Responses output items, including hosted-tool calls and citation annotations.
`cost_usd` is the LiteLLM-provided or calculated cost of all model calls made for that answer and `conversation_cost_usd` is the running total for its `chat_id`.
Both are in USD and are `None` if any required model-call cost is unavailable.
Conversation totals reset with `Agent.reset(chat_id)` or when the conversation's instructions change.
These totals cover LiteLLM model calls, not costs incurred by locally executed tools, and are held in memory with the conversation history.
Every tool must return a `ToolResult`.
Wrap existing tools before passing them to Autom8.
Use `values` when a tool returns more than one value of the same type:
```python
from autom8 import ToolResult

def generate_images(prompt: str):
    image_paths = generate_and_save_images(prompt)
    return ToolResult(type="image",
                      values=image_paths,
                      model_output={"status": "success", "message": "The images will be delivered separately."})

result = agent.invoke("Generate two images")
images = result.results("image")
```
`values` are returned to the calling application through `results()`.
`model_output` is the only tool-result payload added to the LLM conversation.
Do not put sensitive or application-only data in `model_output`.

Configure provider keys with LiteLLM's standard environment variables, for example `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`, or `GEMINI_API_KEY`.

For local development setup, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Agent config reference

```yaml
defaults:
  model: provider/model-name
  reasoning_effort: string
  max_completion_tokens: integer
  tool_choice: string
  parallel_tool_calls: boolean
  hosted_tools:
    - type: provider-hosted-tool-type

custom_tools:
  <tool_name>: package.module:function_name

agents:
  - id: string
    model: provider/model-name
    system_prompt: string
    tool_names:
      - string
    hosted_tools:
      - type: provider-hosted-tool-type
```

`tool_names` selects Python functions that Autom8 executes locally.
`hosted_tools` contains tools that the model provider executes, for example:

```yaml
agents:
  - id: researcher
    model: openai/gpt-5
    system_prompt: Research the question and cite reliable sources.
    hosted_tools:
      - type: web_search
```
Autom8 checks only that each hosted tool is a mapping with a non-empty `type`, then passes it to LiteLLM unchanged.
Hosted-tools availability depend on the selected provider and model, unsupported configurations raise a LiteLLM or provider error directly.


Pass `response_format` to `Agent.invoke(...)` when a single call should use structured output.
Autom8 passes it to LiteLLM as the Responses text format.
```python
response_format = {
    "type": "json_schema",
    "json_schema": {
        "name": "answer",
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"}
            },
            "required": ["summary"],
            "additionalProperties": False
        },
        "strict": True
    }
}

agent.invoke("Summarize this.", response_format=response_format)
```

`custom_tools` values must use normal Python imports in `module:function` format.
Custom tools must live in an importable Python module or package.
Autom8 does not resolve custom tools relative to the YAML file.
If your YAML file and custom tool module live in the same directory, run Python from that directory so the module is importable.
You may need to add an `__init__.py` file if your custom tools live in a package directory.

## MCP tools

Add MCP servers and select their tools in YAML. The existing Python API stays the same:

```python
agent = Agent.from_config(load_agent_config("agents.yaml"))
result = agent.invoke("Find the open issues for this project.")
```

The MCP SDK is included in Autom8's dependencies; existing installations need to reinstall or upgrade Autom8 once.

```yaml
mcp_servers:
  issues:
    transport: streamable_http
    url: https://issues.example.com/mcp
    headers:
      Authorization: "Bearer ${ISSUES_TOKEN}"
    timeout_seconds: 60

  documents:
    transport: stdio
    command: python
    args: ["./integrations/document_server.py"]
    env:
      DOCUMENTS_TOKEN: "${DOCUMENTS_TOKEN}"
    # cwd: /path/to/project

agents:
  - id: project_assistant
    model: openai/gpt-5
    system_prompt: Help users understand project issues and documentation.
    tool_names:
      - read_file
    mcp_tools:
      issues:
        - search_issues
        - get_issue
      documents: "*"
```

The URLs, script, and tool names above are illustrative; use a working server's connection details and exact advertised tool names.
See [examples/mcp_agent_config.yaml](examples/mcp_agent_config.yaml) for a complete HTTP configuration.

- Define connections under top-level `mcp_servers`; each agent's `mcp_tools` selects which servers and tools it can use.
- A list selects exact tool names. A quoted `"*"` exposes all tools from that server. An empty list disables it.
- Only selected servers are retained and connected; unselected and empty selections are not initialized or expanded. Python tools selected with `tool_names` and provider `hosted_tools` continue to work alongside MCP tools.
- `stdio` launches a local process using `command`, optional `args`, `env`, and `cwd`. Commands run directly, without a shell.
- `streamable_http` connects to an existing HTTP or HTTPS endpoint using `url` and optional `headers`.
- `${VARIABLE}` references expand in connection strings, arguments, working directories, environment values, and headers. Missing variables raise an error.
- Relative paths and `cwd` use the application's working directory, as Python tools do. Paths are not resolved relative to the YAML file.
- Local servers inherit only the SDK's minimal environment; explicitly pass API keys and other required variables through `env`.
- `startup_timeout_seconds` defaults to 10 and bounds initialization and the complete paginated tool discovery separately.
- `timeout_seconds` defaults to 60 and bounds MCP requests and HTTP operations. Increase it for tools that need longer to finish.

Autom8 discovers tools when opening MCP connections, preserves their JSON input schemas, and assigns names such as `issues__search_issues`.
Names containing unsupported model characters or exceeding 64 characters receive a normalized name with a stable hash suffix.
Missing selected tools and name collisions raise an error before the model is called.
Standalone `invoke()` calls open connections for that invocation and close them automatically on success or failure.
For an interactive application, explicitly connect before accepting input and reuse the connections across messages:

```python
agent = Agent.from_config(load_agent_config("agents.yaml"))
with agent.connect():
    print(agent.mcp_status)  # Selected servers only: connected or unavailable.
    first_result = agent.invoke("Find the open issues.")
    second_result = agent.invoke("Summarize the first issue.")
```

Construction performs no MCP network requests or process launches. Entering `connect()` initializes and discovers selected servers once;
nested contexts and `invoke()` reuse those connections. Leaving the outer context closes them, including on exceptions, Ctrl+C, and EOF.
Outside a connection context, `mcp_status` reports selected servers as disconnected. The CLI displays readiness before its first input prompt.
Local server processes restart when entering a new connection context, so their in-memory state is preserved only within that context.
`Agent` holds mutable conversation and MCP state; do not invoke the same instance concurrently.

MCP calls appear in `result.tool_calls` and trigger `on_tool_call(name, arguments)` before execution, just like Python tools.
`result.results("mcp")` returns full serialized MCP results, including binary content and application metadata.
Text, resource links, embedded text resources, structured content, and the `isError` flag are passed to the model.
Binary content remains available to the calling application; the model receives a notice instead of base64 data.
MCP `_meta` on results, content blocks, and embedded resources stays in application results and is not passed to the model.
Servers that fail connection or discovery are omitted from the model's tools; other servers and Python tools remain usable.
Failures are logged through Python's `autom8.mcp` logger, with exception details at DEBUG level. The library installs no output handler;
configure a handler to display warnings, as the CLI example does. No outage notice is added to the model's prompt.
If a connection or protocol failure occurs during a tool call, the model receives a generic error result and that server's tools are removed
from subsequent requests in the connection context. Already requested calls to that server are not executed again.
Server-reported tool errors remain ordinary tool results. To retry unavailable servers, leave the connection context and enter a new one.
Standalone invocations retry unavailable servers on the next invocation.
Invalid configuration, missing selected tool names, and name collisions still raise errors.
Tool calls are not automatically retried, since repeating a write operation could duplicate its effects.

This implementation supports MCP tools over stdio and Streamable HTTP with configured credentials or headers.
Interactive OAuth login, resources and prompts as separate capabilities, sampling, elicitation, and legacy HTTP+SSE are not implemented.
It uses the [official SDK's supported 1.x line](https://github.com/modelcontextprotocol/python-sdk/tree/v1.30.0) to retain Python 3.10 compatibility,
and [AnyIO's blocking portal](https://anyio.readthedocs.io/en/stable/threads.html#using-asynchronous-context-managers) to manage asynchronous connections behind the synchronous API.

## Autom8 Built-in tools

| Tool name | Arguments | Description |
| --- | --- | --- |
| `read_file` | `filename: str` | Read the full contents of a file. |
| `list_files` | `path: str` | List files and directories in a directory. |
| `edit_file` | `path: str`, `old_str: str`, `new_str: str` | Replace the first occurrence of `old_str`, or create/overwrite the file when `old_str` is empty. |
| `create_directory` | `path: str` | Create a directory, including parent directories. |
| `git_status` | none | Return `git status --porcelain`. |
| `git_add` | `path: str` | Stage a specific path with `git add -- path`. |
| `git_diff` | `path: str` | Return `git diff`, optionally limited to one path. |
| `git_commit` | `message: str` | Create a local git commit. |


## Observability
Pass `builtin_tool_decorator` to decorate Autom8's built-in tools. 

```python
from autom8 import Agent, load_agent_config

agent_config = load_agent_config("agent_config.yaml")
agent = Agent.from_config(agent_config, builtin_tool_decorator=<decorator>)
```
