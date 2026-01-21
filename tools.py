from pathlib import Path
from typing import Any, Dict

GRAY = "\u001b[38;5;245m"
RESET = "\u001b[0m"


def _resolve_abs_path(path_str: str) -> Path:
    """
    Resolve a user-provided path into an absolute Path, expanding "~" and
    treating relative paths as relative to the current working directory.
    :param path_str: The path to resolve.
    :return: The absolute Path for the resolved location.
    """
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def read_file_tool(filename: str = ".") -> Dict[str, Any]:
    """
    Gets the full content of a file provided by the user.
    :param filename: The name of the file to read.
    :return: The full content of the file.
    """
    print(f"{GRAY}Reading {filename}...{RESET}")
    try:
        full_path = _resolve_abs_path(filename)
        with open(str(full_path), "r") as f:
            content = f.read()
        return {
            "file_path": str(full_path),
            "content": content
        }
    except Exception as e:
        return {"error": str(e)}


def list_files_tool(path: str = ".") -> Dict[str, Any]:
    """
    Lists the files in a directory provided by the user.
    :param path: The path to a directory to list files from.
    :return: A list of files in the directory.
    """
    print(f"{GRAY}Listing files at {path}...{RESET}")
    try:
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
    except Exception as e:
        return {"error": str(e)}


def edit_file_tool(path: str = ".", old_str: str = "", new_str: str = "") -> Dict[str, Any]:
    """
    Replaces first occurrence of old_str with new_str in file. If old_str is empty,
    create/overwrite file with new_str.
    :param path: The path to the file to edit.
    :param old_str: The string to replace.
    :param new_str: The string to replace with.
    :return: A dictionary with the path to the file and the action taken.
    """
    print(f"{GRAY}Editing file {path}...{RESET}")
    try:
        full_path = _resolve_abs_path(path)
        if not full_path.exists() and old_str != "":
            return {
                "path": str(full_path),
                "action": "path does not exist"
            }
        if old_str == "":
            full_path.write_text(new_str, encoding="utf-8")
            return {
                "path": str(full_path),
                "action": f"Created file {path}"
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
    except Exception as e:
        return {"error": str(e)}


def create_directory_tool(path: str = ".") -> Dict[str, Any]:
    """
    Creates a directory at the provided path. If parent directories do not exist,
    they are created automatically.
    :param path: The path to create.
    :return: A dictionary with the path and the action taken.
    """
    print(f"{GRAY}Creating directory {path}...{RESET}")
    try:
        full_path = _resolve_abs_path(path)
        full_path.mkdir(parents=True, exist_ok=True)
        return {
            "path": str(full_path),
            "action": "Directory created successfully"
        }
    except Exception as e:
        return {"error": str(e)}


TOOL_REGISTRY = {
    "read_file": read_file_tool,
    "list_files": list_files_tool,
    "edit_file": edit_file_tool,
    "create_directory": create_directory_tool
}