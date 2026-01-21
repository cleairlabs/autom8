from pyfiglet import Figlet

from agent import Agent

USER_COLOR = "\u001b[94m"
ASSISTANT_COLOR = "\u001b[93m"
RESET_COLOR = "\u001b[0m"


def main() -> None:
    print(Figlet(font="slant").renderText("Autom8"))

    agent = Agent()    
    while True:
        try:
            user_input = input(f"\n{USER_COLOR}>{RESET_COLOR} ")
        except (KeyboardInterrupt, EOFError):
            break
        
        assistant_text = agent.run_turn(user_input, on_tool_call=None)
        
        print(f"\n{ASSISTANT_COLOR}{assistant_text}{RESET_COLOR}")


if __name__ == "__main__":
    main()