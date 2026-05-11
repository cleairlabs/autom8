import inspect
import json
import os

from openai import OpenAI
from dotenv import load_dotenv
from typing import Any, Dict, List

from .tools import TOOL_REGISTRY

load_dotenv()


class Agent:
    def __init__(
        self,
        model: str = "gpt-5",
        api_key: str | None = None,
        system_prompt: str = "",
        tool_registry: Dict[str, Any] = TOOL_REGISTRY,
        max_completion_tokens: int = 2000,
        tool_choice: str = "auto",
    ):
        if api_key is None: api_key = os.environ["OPENAI_API_KEY"]
        self.model = model
        self.openai_client = OpenAI(api_key=api_key)
        self.tool_registry = tool_registry
        self.max_completion_tokens = max_completion_tokens
        self.tool_choice = tool_choice
        self.tools = self._build_tools()
        self.SYSTEM_PROMPT = system_prompt
        self.prompt = self._reset_prompt()

    @classmethod
    def from_config(cls, config: Dict[str, Any], api_key: str | None = None) -> "Agent":
        return cls(model=config["model"],
                   api_key=api_key,
                   system_prompt=config["system_prompt"],
                   tool_registry=config["tool_registry"],
                   max_completion_tokens=config["max_completion_tokens"],
                   tool_choice=config["tool_choice"])

    def _reset_prompt(self) -> List[Dict[str, str]]:
        return [{
            "role": "system",
            "content": self.SYSTEM_PROMPT
        }]

    def _build_tools(self) -> List[Dict[str, Any]]:
        tools = []
        for tool_name, tool in self.tool_registry.items():
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

    def _execute_llm_call(self, prompt: List[Dict[str, str]]):
        response = self.openai_client.chat.completions.create(
            model=self.model,
            messages=prompt,  # type: ignore
            max_completion_tokens=self.max_completion_tokens,
            tools=self.tools,  # type: ignore
            tool_choice=self.tool_choice  # type: ignore
        )
        return response.choices[0].message

    def _format_prompt(self, role, input, tool_calls=None):
        message = {
            "role": role,
            "content": "" if input is None else input.strip()
        }
        if tool_calls: message["tool_calls"] = tool_calls
        self.prompt.append(message)

    def invoke(self, user_input: str, on_tool_call=None) -> str:
        self._format_prompt("user", user_input)
        while True:
            assistant_message = self._execute_llm_call(self.prompt)
            tool_calls = assistant_message.tool_calls or []
            if not tool_calls:
                self._format_prompt("assistant", assistant_message.content)
                return assistant_message.content  # type: ignore

            self._format_prompt("assistant", assistant_message.content, tool_calls)
            for call in tool_calls:
                name = call.function.name  # type: ignore
                args = json.loads(call.function.arguments or "{}")  # type: ignore
                if on_tool_call is not None:
                    on_tool_call(name, args)
                tool = self.tool_registry[name]
                signature = inspect.signature(tool)
                kwargs = {
                    param: args.get(param)
                    for param in signature.parameters
                    if param in args
                }
                resp = tool(**kwargs)
                self.prompt.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(resp)
                })
