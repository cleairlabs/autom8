import logging
from pathlib import Path

from pyfiglet import Figlet


# IMPORTAND: Run pip install "autom8[dev]" for this to work.
from dotenv import load_dotenv
load_dotenv()


try:
    import readline  # Enables line editing (e.g., arrow keys) on compatible terminals
except ImportError:
    pass

try:
    from prompt_toolkit import prompt as terminal_input  # pt_prompt
    from prompt_toolkit.formatted_text import ANSI
except Exception:  # pragma: no cover - optional dependency
    terminal_input = None

from autom8 import Agent, load_agent_config

USER_COLOR = "\u001b[94m"
ASSISTANT_COLOR = "\u001b[93m"
RESET_COLOR = "\u001b[0m"


def main() -> None:
    mcp_logger = logging.getLogger("autom8.mcp")
    mcp_handler = logging.StreamHandler()
    mcp_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    mcp_logger.addHandler(mcp_handler)
    mcp_logger.setLevel(logging.WARNING)
    mcp_logger.propagate = False
    print(Figlet(font="big").renderText("Autom8"))

    # config_path = Path(__file__).with_name("grok_agent_config.yaml")
    config_path = Path(__file__).with_name("agent_config.yaml")
    agent_config = load_agent_config(str(config_path))
    agent = Agent.from_config(agent_config)
    with agent.connect(): # Not strictly needed. Used to not reload/reconnect to MCP/tool descovery for every query
        server_statuses = list(agent.mcp_status.values())
        print(f"Ready · {len(agent.tool_registry)} Python tools · "
              f"{server_statuses.count('connected')} MCP connected · {server_statuses.count('unavailable')} unavailable")
        while True:
            try:
                if terminal_input is not None:
                    user_input = terminal_input(ANSI(f"\n{USER_COLOR}>{RESET_COLOR} "), mouse_support=True)
                else:
                    user_input = input(f"\n{USER_COLOR}>{RESET_COLOR} ")
            except (KeyboardInterrupt, EOFError):
                break

            result = agent.invoke(user_input, on_tool_call=lambda name, arguments: print(f"\nCalling {name}: {arguments}"))

            print(f"\n{ASSISTANT_COLOR}{result.response}{RESET_COLOR}")


if __name__ == "__main__":
    main()
