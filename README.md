<div align='center'>
    <picture>
        <source media="(prefers-color-scheme: light)" srcset="docs/autom8-lightmode-logo.png">
        <img alt="lighbench logo" src="docs/autom8-darkmode-logo.png"" width="50%" height="50%">
    </picture>
</div>


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
