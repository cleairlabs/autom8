import inspect
import json
import os

from openai import OpenAI
from dotenv import load_dotenv
from typing import Any, Dict, List

from tools import TOOL_REGISTRY

load_dotenv()

YOU_COLOR = "\u001b[94m"
ASSISTANT_COLOR = "\u001b[93m"
RESET_COLOR = "\u001b[0m"

class Agent:
    def __init__(self, model: str = "gpt-5", api_key: str | None = None):
        if api_key is None:
            api_key = os.environ["OPENAI_API_KEY"]
        self.model = model
        self.openai_client = OpenAI(api_key=api_key)
        self.tools = self._build_tools()
        self.SYSTEM_PROMPT = """
        You are a coding assistant whose goal it is to help us solve coding tasks.
        Use available tools when needed.
        If no tool is needed, respond normally.
        """

    def _build_tools(self) -> List[Dict[str, Any]]:
        tools = []
        for tool_name, tool in TOOL_REGISTRY.items():
            signature = inspect.signature(tool)
            properties = {name: {"type": "string"} for name in signature.parameters}
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": (tool.__doc__ or "").strip(),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": list(signature.parameters.keys()),
                        "additionalProperties": False
                    }
                }
            })
        return tools

    def _execute_llm_call(self, conversation: List[Dict[str, str]]):
        response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=conversation, # type: ignore
            max_completion_tokens=2000,
            tools=self.tools, # type: ignore
            tool_choice="auto"
        )
        return response.choices[0].message

    def run(self):
        print(self.SYSTEM_PROMPT.strip())
        conversation = [{
            "role": "system",
            "content": self.SYSTEM_PROMPT
        }]
        while True:
            try:
                user_input = input(f"{YOU_COLOR}You:{RESET_COLOR}:")
            except (KeyboardInterrupt, EOFError):
                break
            conversation.append({
                "role": "user",
                "content": user_input.strip()
            })
            while True:
                assistant_message = self._execute_llm_call(conversation)
                tool_calls = assistant_message.tool_calls or []
                if not tool_calls:
                    print(f"{ASSISTANT_COLOR}Assistant:{RESET_COLOR}: {assistant_message.content}")
                    conversation.append({
                        "role": "assistant",
                        "content": assistant_message.content # type: ignore
                    })
                    break
                conversation.append({
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": tool_calls
                }) # type: ignore
                for call in tool_calls:
                    name = call.function.name # type: ignore
                    args = json.loads(call.function.arguments or "{}") # type: ignore
                    tool = TOOL_REGISTRY[name]
                    resp = ""
                    print(name, args)
                    if name == "read_file":
                        resp = tool(args.get("filename", "."))
                    elif name == "list_files":
                        resp = tool(args.get("path", "."))
                    elif name == "edit_file":
                        resp = tool(args.get("path", "."), 
                                    args.get("old_str", ""), 
                                    args.get("new_str", ""))
                    conversation.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(resp)
                    })





if __name__ == "__main__":
    Agent().run()
