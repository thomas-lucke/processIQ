"""LLM model presets for each provider and analysis mode.

Edit this file to change which models are used for each provider/mode/task.

Structure: PROVIDER_MODEL_PRESETS[provider][mode][task] = "model-id"
For Ollama: PROVIDER_MODEL_PRESETS["ollama"][mode] = "model-id" (single model for all tasks)
"""

PROVIDER_MODEL_PRESETS: dict[str, dict[str, dict[str, str] | str]] = {
    "openai": {
        "cost_optimized": {
            "extraction": "gpt-4o-mini",
            "clarification": "gpt-4o-mini",
            "explanation": "gpt-5-nano",
            "analysis": "gpt-5-nano",
        },
        "balanced": {
            "extraction": "gpt-4o-mini",
            "clarification": "gpt-4o-mini",
            "explanation": "gpt-5-mini",
            "analysis": "gpt-5-mini",
        },
        "deep_analysis": {
            "extraction": "gpt-4o-mini",
            "clarification": "gpt-4o-mini",
            "explanation": "gpt-5",
            "analysis": "gpt-5",
        },
    },
    "anthropic": {
        "cost_optimized": {
            "extraction": "claude-haiku-4-5-20251001",
            "clarification": "claude-haiku-4-5-20251001",
            "explanation": "claude-haiku-4-5-20251001",
            "analysis": "claude-haiku-4-5-20251001",
        },
        "balanced": {
            "extraction": "claude-haiku-4-5-20251001",
            "clarification": "claude-haiku-4-5-20251001",
            "explanation": "claude-sonnet-4-5-20250929",
            "analysis": "claude-sonnet-4-5-20250929",
        },
        "deep_analysis": {
            "extraction": "claude-sonnet-4-5-20250929",
            "clarification": "claude-sonnet-4-5-20250929",
            "explanation": "claude-sonnet-4-5-20250929",
            "analysis": "claude-sonnet-4-5-20250929",
        },
    },
    "ollama": {
        "cost_optimized": {
            "extraction": "qwen3:8b",
            "clarification": "qwen3:8b",
            "explanation": "qwen3:8b",
            "analysis": "llama3.2:3",
        },
        "balanced": {
            "extraction": "qwen3:8b",
            "clarification": "qwen3:8b",
            "explanation": "qwen3:8b",
            "analysis": "llama3.2:3",
        },
        "deep_analysis": {
            "extraction": "qwen3:8b",
            "clarification": "qwen3:8b",
            "explanation": "qwen3:8b",
            "analysis": "llama3.2:3",
        },
    },
}

# Default model per provider (used when no mode/task match is found)
PROVIDER_DEFAULTS = {
    "openai": "gpt-5-nano",
    "anthropic": "claude-haiku-4-5-20251001",
    "ollama": "qwen3:8b",
}


def get_model_for_task(provider: str, analysis_mode: str, task: str) -> str | None:
    """Look up the model for a specific provider/mode/task combination.

    Returns None if no preset match is found.
    """
    provider_presets = PROVIDER_MODEL_PRESETS.get(provider)
    if not provider_presets:
        return None

    mode_config = provider_presets.get(analysis_mode)
    if mode_config is None:
        return None

    # Ollama: single string for all tasks
    if isinstance(mode_config, str):
        return mode_config

    return mode_config.get(task)
