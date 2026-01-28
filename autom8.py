from pyfiglet import Figlet

try:
    import readline  # Enables line editing (e.g., arrow keys) on compatible terminals
except ImportError:
    pass

try:
    from prompt_toolkit import prompt as terminal_input #pt_prompt
    from prompt_toolkit.formatted_text import ANSI
except Exception:  # pragma: no cover - optional dependency
    terminal_input = None

from agent import Agent

USER_COLOR = "\u001b[94m"
ASSISTANT_COLOR = "\u001b[93m"
RESET_COLOR = "\u001b[0m"


def main() -> None:
    print(Figlet(font="big").renderText("Autom8"))

    agent = Agent()    
    while True:
        try:
            if terminal_input is not None:
                user_input = terminal_input(ANSI(f"\n{USER_COLOR}>{RESET_COLOR} "), mouse_support=True)
            else:
                user_input = input(f"\n{USER_COLOR}>{RESET_COLOR} ")
        except (KeyboardInterrupt, EOFError):
            break
        
        assistant_text = agent.run_turn(user_input, on_tool_call=None)
        
        print(f"\n{ASSISTANT_COLOR}{assistant_text}{RESET_COLOR}")


if __name__ == "__main__":
    main()