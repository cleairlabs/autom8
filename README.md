<div align='center'>
    <picture>
        <source media="(prefers-color-scheme: light)" srcset="docs/autom8-lightmode-logo.png">
        <img alt="lighbench logo" src="docs/autom8-darkmode-logo.png"" width="30%" height="50%">
    </picture>
</div>


Install directly from GitHub with `pip`:
```bash
pip install git+https://github.com/cleairlabs/autom8.git
```

Start by cloning the **GitHub** repository, then create and activate a virtual environment before installing with `pip`:
```bash
python -m venv .venv
```
```bash
source .venv/bin/activate
```
```bash
pip install -e .
```

The package installs the reusable library code only. Create your own script and pass an explicit path to your YAML config when calling `load_agent_config(...)`.

Example:
```python
from autom8 import Agent, load_agent_config

agent_config = load_agent_config("agent_config.yaml")
agent = Agent.from_config(agent_config)
```

A runnable demo script and sample config live in `examples/`. To run the example script, install the dev extra:
```bash
pip install -e .[dev]
```

Run the example from the `examples/` directory:
```bash
cd examples
python autom8_example_agent.py
```

## Agent config reference

```yaml
defaults:
  model: string
  max_completion_tokens: integer
  tool_choice: string

custom_tools:
  <tool_name>: package.module:function_name

agents:
  - id: string
    model: string
    system_prompt: string
    tool_names:
      - string
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
