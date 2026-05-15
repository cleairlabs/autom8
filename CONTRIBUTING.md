# Contributing

We welcome contributions and pull requests.
Extending the supported out-of-the-box tools is especially welcome, See `autom8/tools.py`.

## Install locally

Start by cloning the **GitHub** repository, then create and activate a virtual environment before installing with the dev extra:

```bash
git clone https://github.com/cleairlabs/autom8.git
cd autom8
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Run the example

A runnable demo script and sample config live in `examples/`.

Run the example from the `examples/` directory:

```bash
cd examples
python autom8_example_agent.py
```
