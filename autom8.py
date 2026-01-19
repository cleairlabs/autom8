from agent import Agent

USER_COLOR = "\u001b[94m"
ASSISTANT_COLOR = "\u001b[93m"
RESET_COLOR = "\u001b[0m"


def main() -> None:
    agent = Agent()
    print("Agent system prompt:\n", agent.SYSTEM_PROMPT.strip(), "\n\n")
    
    while True:
        try:
            user_input = input(f"{USER_COLOR}You:{RESET_COLOR} ")
        except (KeyboardInterrupt, EOFError):
            break
        
        assistant_text = agent.run_turn(user_input, on_tool_call=lambda name, args: print(name, args))
        
        print(f"\n{ASSISTANT_COLOR}Assistant:{RESET_COLOR} {assistant_text}")


if __name__ == "__main__":
    main()