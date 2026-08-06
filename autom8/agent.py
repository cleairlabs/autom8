import inspect
import json

from litellm import completion
from dotenv import load_dotenv
from typing import Any, Dict, List

from .llm_adapter import normalize
from .tools import TOOL_REGISTRY

load_dotenv()


class Agent:
    def __init__(
        self,
        model: str | None = None,
        system_prompt: str = "",
        tool_registry: Dict[str, Any] = TOOL_REGISTRY,
        max_completion_tokens: int = 2000,
        tool_choice: str = "auto",
    ):
        self.default_model = model
        self.tool_registry = tool_registry
        self.max_completion_tokens = max_completion_tokens
        self.tool_choice = tool_choice
        self.tools = self._build_tools()
        self.SYSTEM_PROMPT = system_prompt
        self.sessions: Dict[int, List[Dict[str, Any]]] = {}
        self.session_instructions: Dict[int, str] = {}


    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "Agent":
        agent = cls(model=config["model"],
                    system_prompt=config["system_prompt"],
                    tool_registry=config["tool_registry"],
                    max_completion_tokens=config["max_completion_tokens"],
                    tool_choice=config["tool_choice"])
        return agent


    def _reset_prompt(self, system_prompt: str) -> List[Dict[str, Any]]:
        return [{
            "role": "system",
            "content": system_prompt
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


    def _execute_llm_call(self, prompt: List[Dict[str, Any]], model: str, response_format: Dict[str, Any] | None):
        request_options = {
            "model": model,
            "messages": prompt,
            "max_completion_tokens": self.max_completion_tokens,
        }
        if self.tools:
            request_options["tools"] = self.tools
            request_options["tool_choice"] = self.tool_choice
        if response_format is not None:
            request_options["response_format"] = response_format

        response = completion(**normalize(request_options))  # type: ignore
        return response.choices[0].message # type: ignore


    def _format_prompt(self, prompt: List[Dict[str, Any]], role: str, input: Any, tool_calls=None):
        message = {
            "role": role
        }
        if isinstance(input, str):
            message["content"] = input.strip()
        else:
            message["content"] = "" if input is None else input
        if tool_calls: message["tool_calls"] = tool_calls
        prompt.append(message)


    def _build_user_content(self, message: str | None, image_url: str | None) -> Any:
        if image_url is None:
            if message is None:
                raise ValueError("message is required when image_url is not provided")
            return message
        content: List[Dict[str, Any]] = [{"type": "image_url", "image_url": {"url": image_url}}]
        if message is not None:
            content.insert(0, {"type": "text", "text": message})
        return content


    def invoke(self,
               message: str | None = None,
               *,
               chat_id: int = 0,
               instructions: str | None = None,
               model: str | None = None,
               image_url: str | None = None,
               response_format: Dict[str, Any] | None = None,
               on_tool_call=None) -> str:
        if model is None:
            if self.default_model is None:
                raise ValueError("No model specified")
            model = self.default_model
        active_instructions = self.SYSTEM_PROMPT if instructions is None else instructions
        current_instructions = self.session_instructions.get(chat_id)
        if current_instructions != active_instructions or chat_id not in self.sessions:
            self.sessions[chat_id] = self._reset_prompt(active_instructions)
            self.session_instructions[chat_id] = active_instructions

        prompt = self.sessions[chat_id]
        user_content = self._build_user_content(message, image_url)
        self._format_prompt(prompt, "user", user_content)

        while True:
            assistant_message = self._execute_llm_call(prompt, model, response_format)
            tool_calls = assistant_message.tool_calls or []
            if not tool_calls:
                self._format_prompt(prompt, "assistant", assistant_message.content)
                return assistant_message.content  # type: ignore

            self._format_prompt(prompt, "assistant", assistant_message.content, tool_calls)
            for call in tool_calls:
                name = call.function.name  # type: ignore
                args = json.loads(call.function.arguments or "{}")  # type: ignore
                if on_tool_call is not None:
                    on_tool_call(name, args)
                tool = self.tool_registry[name] # type: ignore
                signature = inspect.signature(tool)
                kwargs = {
                    param: args.get(param)
                    for param in signature.parameters
                    if param in args
                }
                resp = tool(**kwargs)
                prompt.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(resp)
                })


    def reset(self, chat_id: int) -> None:
        self.sessions.pop(chat_id, None)
        self.session_instructions.pop(chat_id, None)
