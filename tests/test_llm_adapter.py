from autom8.llm_adapter import normalize


def test_normalize_uses_max_tokens_for_xai_models():
    request_options = {"model": "xai/grok-4.5", "max_completion_tokens": 1000}
    normalized_request_options = normalize(request_options)
    assert normalized_request_options == {"model": "xai/grok-4.5", "max_tokens": 1000}
    assert request_options == {"model": "xai/grok-4.5", "max_completion_tokens": 1000}


def test_normalize_leaves_other_models_unchanged():
    request_options = {"model": "openai/gpt-5", "max_completion_tokens": 1000}
    assert normalize(request_options) == request_options
