<div align='center'>
    <picture>
        <source media="(prefers-color-scheme: light)" srcset="docs/autom8-lightmode-logo.png">
        <img alt="autom8 logo" src="docs/autom8-darkmode-logo.png" width="30%" height="50%">
    </picture>
</div>


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

For direct usage without YAML, pass the model to `invoke(...)`:

```python
from autom8 import Agent

agent = Agent()
agent.invoke("Hello", model="openai/gpt-5")
```

Set `model` when most calls should use the same model:

```python
agent = Agent(model="openai/gpt-5")
agent.invoke("Hello")
agent.invoke("Hello", model="anthropic/claude-sonnet-4-5")
```

Configure provider keys with LiteLLM's standard environment variables, for example `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`, or `GEMINI_API_KEY`.

For local development setup, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Agent config reference

```yaml
defaults:
  model: provider/model-name
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

## Predefined tools

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
