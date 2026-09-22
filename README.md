<div align='center'>
    <picture>
        <source media="(prefers-color-scheme: light)" srcset="docs/autom8-lightmode-logo.png">
        <img alt="autom8 logo" src="docs/autom8-darkmode-logo.png" width="30%" height="50%">
    </picture>
</div>

[![Pytests](https://github.com/cleairlabs/autom8/actions/workflows/pytests.yml/badge.svg)](https://github.com/cleairlabs/autom8/actions/workflows/pytests.yml)


Autom8 is a minimal framework for building AI agents.
It uses LiteLLM for model calls, so models are selected with provider-prefixed names like `openai/gpt-5`, `anthropic/claude-sonnet-4-5`, `mistral/mistral-large-latest`, or `gemini/gemini-2.0-flash`.

## Install from GitHub

Install directly from GitHub with `pip`:
```bash
pip install git+https://github.com/cleairlabs/autom8.git
```

The `pip` install provides the reusable library code only. If you install from GitHub, create your own script and pass an explicit path to your YAML config when calling `load_agent_config(...)`. If you clone the repository locally, a runnable example script and sample config are included in `examples/`.

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

`Agent.invoke(...)` returns an `AgentResult` containing the final response and any tool calls made while producing it.
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

custom_tools:
  <tool_name>: package.module:function_name

agents:
  - id: string
    model: provider/model-name
    system_prompt: string
    tool_names:
      - string
```

Pass `response_format` to `Agent.invoke(...)` when a single call should use structured output.
The value is passed through to LiteLLM.

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

## Built-in tools

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
For example, with [cleair](https://docs.cleair.ai/):
```bash
pip install "cleair @ git+https://github.com/cleairlabs/cleair.git@main#subdirectory=sdks/python"
```

```python
import cleair
from autom8 import Agent, load_agent_config

cleair.init(cleair_api_key="<api-key>")
agent_config = load_agent_config("agent_config.yaml")
agent = Agent.from_config(agent_config, builtin_tool_decorator=cleair.observe(as_type=cleair.type.TOOL))
```
