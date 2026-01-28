from pathlib import Path
from typing import Any, Dict, Optional

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
    

def git_status_tool() -> str:
    """
    Return git status --porcelain output for the current repository.

    IMPORTANT: This function is read-only. It does not modify the working tree or index.
    Use it to determine what files are modified/untracked/staged in a parse-friendly format.

    Returns:
        The raw stdout from git status --porcelain (may be an empty string if clean).

    Raises:
        subprocess.CalledProcessError: If Git fails (e.g. repository not initialized).
    """
    import subprocess
    print(f"{GRAY}Running git status...{RESET}")
    cmd = ["git", "status", "--porcelain"]
    result = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return result.stdout


def git_add_tool(path: str) -> None:
    """
    Stage a specific path with git add -- path.

    IMPORTANT: Only call this function when the user has explicitly asked you to stage a file
    (or clearly instructed you to prepare changes for a commit). Do NOT call it proactively.

    This stages the provided file/directory path only (not the whole repo).

    Args:
        path: The file or directory path to stage.

    Raises:
        subprocess.CalledProcessError: If Git fails (e.g. path does not exist, repository not initialized).
    """
    import subprocess
    print(f"{GRAY}Running git add -- {path}...{RESET}")
    cmd = ["git", "add", "--", path]
    subprocess.run(cmd, check=True, text=True)


def git_diff_tool(path: Optional[str] = None) -> str:
    """
    Return a unified diff from git diff.

    IMPORTANT: This function is read-only. It does not modify the working tree or index.
    Use it to review changes before staging or committing.

    Args:
        path: If provided, limits the diff to this path.

    Returns:
        The raw stdout from the diff command (may be an empty string if no differences).

    Raises:
        subprocess.CalledProcessError: If Git fails (e.g. repository not initialized).
    """
    import subprocess
    cmd = ["git", "diff"]
    if path is not None:
        print(f"{GRAY}Running git diff -- {path}...{RESET}")
        cmd.append("--")
        cmd.append(path)
    else: print(f"{GRAY}Running git diff...{RESET}")
    result = subprocess.run(cmd, check=True, text=True, capture_output=True)
    return result.stdout


def git_commit_tool(message: str) -> None:
    """
    Create a local Git commit using the Autom8 bot identity.

    IMPORTANT: Only call this function when the user has explicitly requested that changes be committed
    or has clearly instructed you to upload/share the work via Git. 
    Do NOT call this function proactively just because files changed, tests pass, or a task seems finished. 
    If the user has not asked for a commit, leave the working tree as-is and report what changed instead.

    This function performs a local git commit and does not push to any remote. 
    Authentication/SSH keys are not used here; those are only relevant for git push.

    Args:
        message: The commit message to use.

    Raises:
        subprocess.CalledProcessError: If Git refuses to create the commit (e.g. nothing staged to commit,
        commit hooks fail, repository not initialized, etc.).
    """
    import subprocess
    print(f"{GRAY}Committing changes with message: {message}...{RESET}")
    cmd = [
        "git",
        "-c", "user.name=autom8",
        "-c", "user.email=autom8robot@proton.me",
        "-c", "commit.gpgsign=false",
        "commit",
        "-m", message,
    ]
    subprocess.run(cmd, check=True, text=True)





TOOL_REGISTRY = {
    "read_file": read_file_tool,
    "list_files": list_files_tool,
    "edit_file": edit_file_tool,
    "create_directory": create_directory_tool,
    # Git tools
    "git_status": git_status_tool,
    "git_add": git_add_tool,
    "git_diff": git_diff_tool,
    "git_commit": git_commit_tool,
}
