import inspect
import json
import os

from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
from typing import Any, Dict, List

load_dotenv()


YOU_COLOR = "\u001b[94m"
ASSISTANT_COLOR = "\u001b[93m"
RESET_COLOR = "\u001b[0m"


def _resolve_abs_path(path_str: str) -> Path:
    """
    file.py -> /Users/home/mihail/modern-software-dev-lectures/file.py
    """
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path

def read_file_tool(filename: str) -> Dict[str, Any]:
    """
    Gets the full content of a file provided by the user.
    :param filename: The name of the file to read.
    :return: The full content of the file.
    """
    full_path = _resolve_abs_path(filename)
    print(full_path)
    with open(str(full_path), "r") as f:
        content = f.read()
    return {
        "file_path": str(full_path),
        "content": content
    }

def list_files_tool(path: str) -> Dict[str, Any]:
    """
    Lists the files in a directory provided by the user.
    :param path: The path to a directory to list files from.
    :return: A list of files in the directory.
    """
    full_path = _resolve_abs_path(path)
    all_files = []
    for item in full_path.iterdir():
        all_files.append({
            "filename": item.name,
            "type": "file" if item.is_file() else "dir"
        })
    return {
        "path": str(full_path),
        "files": all_files
    }

def edit_file_tool(path: str, old_str: str, new_str: str) -> Dict[str, Any]:
    """
    Replaces first occurrence of old_str with new_str in file. If old_str is empty,
    create/overwrite file with new_str.
    :param path: The path to the file to edit.
    :param old_str: The string to replace.
    :param new_str: The string to replace with.
    :return: A dictionary with the path to the file and the action taken.
    """
    full_path = _resolve_abs_path(path)
    if old_str == "":
        full_path.write_text(new_str, encoding="utf-8")
        return {
            "path": str(full_path),
            "action": "created_file"
        }
    original = full_path.read_text(encoding="utf-8")
    if original.find(old_str) == -1:
        return {
            "path": str(full_path),
            "action": "old_str not found"
        }
    edited = original.replace(old_str, new_str, 1)
    full_path.write_text(edited, encoding="utf-8")
    return {
        "path": str(full_path),
        "action": "Edited: old_str replaced by new_str successfully"
    }

TOOL_REGISTRY = {
    "read_file": read_file_tool,
    "list_files": list_files_tool,
    "edit_file": edit_file_tool 
}





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
