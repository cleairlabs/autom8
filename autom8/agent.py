import inspect
import json

from litellm import responses
from typing import Any, Callable, Dict, List

from .results import AgentResult, ToolCall, ToolResult
from .tools import TOOL_REGISTRY

# Type def.
ToolDecorator = Callable[[Callable[..., Any]], Callable[..., Any]]


class Agent:
    def __init__(
        self,
        model: str | None = None,
        system_prompt: str = "",
        tool_registry: Dict[str, Any] = TOOL_REGISTRY,
        max_completion_tokens: int = 2000,
        tool_choice: str = "auto",
        parallel_tool_calls: bool | None = None,
        builtin_tool_decorator: ToolDecorator | None = None,
        reasoning_effort: str | None = None,
        hosted_tools: List[Dict[str, Any]] | None = None,
    ):
        self.default_model = model
        self.tool_registry = dict(tool_registry)
        self._tool_signatures = {tool_name: inspect.signature(tool) for tool_name, tool in tool_registry.items()}
        if builtin_tool_decorator is not None:
            for tool_name, tool in tool_registry.items():
                if TOOL_REGISTRY.get(tool_name) is tool:
                    self.tool_registry[tool_name] = builtin_tool_decorator(tool)
        self.max_completion_tokens = max_completion_tokens
        self.tool_choice = tool_choice
        self.reasoning_effort = reasoning_effort
        self.parallel_tool_calls = parallel_tool_calls
        self.hosted_tools = [dict(hosted_tool) for hosted_tool in hosted_tools or []]
        self.tools = self._build_tools()
        self.SYSTEM_PROMPT = system_prompt
        self.sessions: Dict[int, List[Dict[str, Any]]] = {}
        self.session_instructions: Dict[int, str] = {}


    @classmethod
    def from_config(cls, config: Dict[str, Any], builtin_tool_decorator: ToolDecorator | None = None) -> "Agent":
        agent = cls(model=config["model"],
                    system_prompt=config["system_prompt"],
                    tool_registry=config["tool_registry"],
                    max_completion_tokens=config["max_completion_tokens"],
                    tool_choice=config["tool_choice"],
                    reasoning_effort=config.get("reasoning_effort"),
                    parallel_tool_calls=config.get("parallel_tool_calls"),
                    hosted_tools=config.get("hosted_tools"),
                    builtin_tool_decorator=builtin_tool_decorator)
        return agent


    def _reset_prompt(self, system_prompt: str) -> List[Dict[str, Any]]:
        return [{
            "role": "system",
            "content": system_prompt
        }]


    def _build_tools(self) -> List[Dict[str, Any]]:
        tools = []
        for tool_name, tool in self.tool_registry.items():
            signature = self._tool_signatures[tool_name]
            properties = {name: {"type": "string"} for name in signature.parameters}
            tools.append({
                "type": "function",
                "name": tool_name,
                "description": (tool.__doc__ or "").strip(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": list(signature.parameters.keys()),
                    "additionalProperties": False
                },
                "strict": False,
            })
        tools.extend(self.hosted_tools)
        return tools


    def _execute_llm_call(self, prompt: List[Dict[str, Any]], model: str, response_format: Dict[str, Any] | None):
        request_options = {
            "model": model,
            "input": prompt,
            "max_output_tokens": self.max_completion_tokens,
        }
        if self.tools:
            request_options["tools"] = self.tools
            request_options["tool_choice"] = self.tool_choice
            if self.parallel_tool_calls is not None:
                request_options["parallel_tool_calls"] = self.parallel_tool_calls
        if response_format is not None:
            request_options["text_format"] = response_format
        if self.reasoning_effort is not None:
            request_options["reasoning"] = {"effort": self.reasoning_effort}

        return responses(**request_options)  # type: ignore


    def _format_prompt(self, prompt: List[Dict[str, Any]], role: str, input: Any):
        message = {"role": role}
        if isinstance(input, str):
            message["content"] = input.strip()
        else:
            message["content"] = "" if input is None else input
        prompt.append(message)


    def _build_user_content(self, message: str | None, image_url: str | None) -> Any:
        if image_url is None:
            if message is None:
                raise ValueError("message is required when image_url is not provided")
            return message
        content: List[Dict[str, Any]] = [{"type": "input_image", "image_url": image_url}]
        if message is not None:
            content.insert(0, {"type": "input_text", "text": message})
        return content


    def _serialize_response_item(self, response_item: Any) -> Dict[str, Any]:
        if isinstance(response_item, dict):
            return dict(response_item)
        return response_item.model_dump(exclude_none=True)


    def invoke(self,
               message: str | None = None,
               *,
               chat_id: int = 0,
               instructions: str | None = None,
               model: str | None = None,
               image_url: str | None = None,
               response_format: Dict[str, Any] | None = None,
               on_tool_call=None) -> AgentResult:
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
        tool_calls: List[ToolCall] = []
        response_items: List[Dict[str, Any]] = []
        while True:
            response = self._execute_llm_call(prompt, model, response_format)
            current_response_items = [self._serialize_response_item(response_item) for response_item in response.output] # type: ignore
            response_items.extend(current_response_items)
            prompt.extend(current_response_items)
            requested_tool_calls = [response_item for response_item in current_response_items if response_item.get("type") == "function_call"]
            if not requested_tool_calls:
                return AgentResult(response=response.output_text, tool_calls=tool_calls, response_items=response_items) # type: ignore

            for call in requested_tool_calls:
                name = call["name"]
                args = json.loads(call.get("arguments") or "{}")
                if on_tool_call is not None:
                    on_tool_call(name, args)
                tool = self.tool_registry[name] # type: ignore
                signature = self._tool_signatures[name] # type: ignore
                kwargs = {
                    param: args.get(param)
                    for param in signature.parameters
                    if param in args
                }
                tool_result = tool(**kwargs)
                if not isinstance(tool_result, ToolResult):
                    raise TypeError(f"Tool '{name}' must return ToolResult, got {type(tool_result).__name__}")
                tool_calls.append(ToolCall(name=name, arguments=args, result=tool_result)) # type: ignore
                prompt.append({
                    "type": "function_call_output",
                    "call_id": call["call_id"],
                    "output": tool_result.to_model_json()
                })


    def reset(self, chat_id: int) -> None:
        self.sessions.pop(chat_id, None)
        self.session_instructions.pop(chat_id, None)
