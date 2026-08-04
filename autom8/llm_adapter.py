from typing import Any, Dict


def normalize(request_options: Dict[str, Any]) -> Dict[str, Any]:
    normalized_request_options = dict(request_options)
    if normalized_request_options["model"].startswith("xai/"):
        normalized_request_options["max_tokens"] = normalized_request_options.pop("max_completion_tokens")
    return normalized_request_options
