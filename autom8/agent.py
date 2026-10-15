from contextlib import contextmanager
import inspect
import json

from litellm import completion_cost, responses
from typing import Any, Callable, Dict, List

from .mcp_tools import MCPTools
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
        mcp_servers: Dict[str, Any] | None = None,
        mcp_tools: Dict[str, Any] | None = None,
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
        self._mcp_tools = MCPTools(mcp_servers or {}, mcp_tools or {}, self.tool_registry)
        self.SYSTEM_PROMPT = system_prompt
        self.sessions: Dict[int, List[Dict[str, Any]]] = {}
        self.session_instructions: Dict[int, str] = {}
        self.session_costs: Dict[int, float | None] = {}


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
                    mcp_servers=config.get("mcp_servers"),
                    mcp_tools=config.get("mcp_tools"),
                    builtin_tool_decorator=builtin_tool_decorator)
        return agent


    @contextmanager
    def connect(self):
        """Initialize selected MCP servers and reuse their connections until the context exits."""
        with self._mcp_tools.connect():
            yield self


    @property
    def mcp_status(self) -> dict[str, str]:
        """Return connection status for selected servers only."""
        return self._mcp_tools.status


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
        available_tools = self.tools + self._mcp_tools.definitions
        if available_tools:
            request_options["tools"] = available_tools
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
        if model is None and self.default_model is None:
            raise ValueError("No model specified")
        with self._mcp_tools.connect():
            return self._invoke(message, chat_id=chat_id, instructions=instructions, model=model, image_url=image_url,
                                response_format=response_format, on_tool_call=on_tool_call)


    def _invoke(self,
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
            self.session_costs[chat_id] = 0.0

        prompt = self.sessions[chat_id]
        user_content = self._build_user_content(message, image_url)
        self._format_prompt(prompt, "user", user_content)
        tool_calls: List[ToolCall] = []
        response_items: List[Dict[str, Any]] = []
        cost_usd: float | None = 0.0
        while True:
            response = self._execute_llm_call(prompt, model, response_format)
            response_cost = (getattr(response, "_hidden_params", None) or {}).get("response_cost")
            if response_cost is None and getattr(response, "usage", None) is not None:
                try:
                    response_cost = completion_cost(completion_response=response, model=model)
                except Exception:
                    response_cost = None
            cost_usd = cost_usd + response_cost if cost_usd is not None and response_cost is not None else None
            conversation_cost = self.session_costs[chat_id]
            self.session_costs[chat_id] = conversation_cost + response_cost if conversation_cost is not None and response_cost is not None else None
            current_response_items = [self._serialize_response_item(response_item) for response_item in response.output] # type: ignore
            response_items.extend(current_response_items)
            prompt.extend(current_response_items)
            requested_tool_calls = [response_item for response_item in current_response_items if response_item.get("type") == "function_call"]
            if not requested_tool_calls:
                return AgentResult(response=response.output_text, tool_calls=tool_calls, response_items=response_items, # type: ignore
                                   cost_usd=cost_usd, conversation_cost_usd=self.session_costs[chat_id]) # type: ignore

            for call in requested_tool_calls:
                name = call["name"]
                args = json.loads(call.get("arguments") or "{}")
                if on_tool_call is not None:
                    on_tool_call(name, args)
                if self._mcp_tools.handles(name):
                    tool_result = self._mcp_tools.call(name, args)
                else:
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
        self.session_costs.pop(chat_id, None)
