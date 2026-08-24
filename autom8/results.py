import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ToolResult:
    type: str
    values: list[Any]
    model_output: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    def to_model_json(self) -> str:
        return json.dumps(self.model_output)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result: ToolResult


@dataclass
class AgentResult:
    response: str
    tool_calls: list[ToolCall]

    def results(self, result_type: str) -> list[Any]:
        values = []
        for tool_call in self.tool_calls:
            if tool_call.result.type == result_type:
                values.extend(tool_call.result.values)
        return values

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())
