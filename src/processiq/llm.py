"""Centralized LLM factory for ProcessIQ.

All LLM calls should go through this module to ensure consistent
configuration, logging, and error handling across the application.

Usage:
    from processiq.llm import get_chat_model

    # For general chat/generation
    model = get_chat_model()
    response = model.invoke([HumanMessage(content="...")])

    # For task-specific model (uses per-task config from settings)
    from processiq.config import TASK_ANALYSIS
    model = get_chat_model(task=TASK_ANALYSIS)
    response = model.invoke([HumanMessage(content="...")])

    # For structured output (Pydantic model response)
    from processiq.models import SomeSchema
    structured = get_chat_model().with_structured_output(SomeSchema)
    result = structured.invoke([HumanMessage(content="...")])

    # Override provider/model for specific calls (overrides task config too)
    model = get_chat_model(provider="openai", model="gpt-4o")
"""

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel

from processiq.config import settings
from processiq.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


def extract_text_content(response: Any) -> str:
    """Extract text content from an LLM response, regardless of format.

    Handles the different ways models return content:
    - Plain string in response.content (most models)
    - List of content blocks in response.content (some newer models)
    - Content in additional_kwargs (reasoning models like o1/o3/gpt-5)
    """
    # Try response.content first
    if hasattr(response, "content"):
        content = response.content

        # Plain string — most common case
        if isinstance(content, str) and content.strip():
            return content

        # List of content blocks (e.g. [{"type": "text", "text": "..."}])
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    text_parts.append(block)
            joined = "\n".join(text_parts).strip()
            if joined:
                return joined

    # Reasoning models may put output in additional_kwargs
    if hasattr(response, "additional_kwargs"):
        kwargs = response.additional_kwargs
        # OpenAI reasoning models
        for key in ("reasoning_content", "content", "output"):
            if key in kwargs and isinstance(kwargs[key], str) and kwargs[key].strip():
                logger.info("Extracted content from additional_kwargs['%s']", key)
                return str(kwargs[key])

    # Last resort: stringify the whole response
    fallback = str(response).strip()
    if fallback:
        logger.warning("Fell back to str(response) for content extraction")
        return fallback

    return ""


def is_restricted_openai_model(model: str) -> bool:
    """Check if an OpenAI model has parameter restrictions.

    GPT-5 series and o-series models:
    - Only support temperature=1 (default)
    - Require max_completion_tokens instead of max_tokens
    """
    return model.startswith(("gpt-5", "o1", "o3"))


def get_chat_model(
    *,
    task: str | None = None,
    analysis_mode: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
) -> BaseChatModel:
    """Get a LangChain chat model based on configuration.

    Resolution order (first non-None wins):
    1. Explicit parameters (provider, model, temperature)
    2. Analysis mode preset (if mode and task provided)
    3. Task-specific env var config
    4. Global settings (llm_provider, llm_model, llm_temperature)

    Args:
        task: Task name for task-specific config (extraction, clarification, etc.).
        analysis_mode: Analysis mode preset (cost_optimized, balanced, deep_analysis).
        provider: Override the configured provider ("anthropic", "openai", "ollama").
        model: Override the configured model.
        temperature: Override the configured temperature.

    Returns:
        A LangChain BaseChatModel instance.

    Raises:
        ConfigurationError: If the provider is not supported or API key is missing.
    """
    # Get resolved config (applies analysis mode, provider, and task overrides)
    resolved_provider, resolved_model, resolved_temp = settings.get_resolved_config(
        task=task, analysis_mode=analysis_mode, provider=provider
    )

    # Apply explicit overrides (highest priority)
    provider = provider or resolved_provider
    model = model or resolved_model
    temperature = temperature if temperature is not None else resolved_temp

    task_info = f" (task={task})" if task else ""
    mode_info = f" [mode={analysis_mode}]" if analysis_mode else ""
    logger.info(
        "Using LLM: %s/%s (temperature=%.1f)%s%s",
        provider,
        model,
        temperature,
        task_info,
        mode_info,
    )

    if provider == "anthropic":
        return _get_anthropic_model(model, temperature)
    elif provider == "openai":
        return _get_openai_model(model, temperature)
    elif provider == "ollama":
        return _get_ollama_model(model, temperature)
    else:
        raise ConfigurationError(
            message=f"Unsupported LLM provider: {provider}",
            config_key="llm_provider",
            user_message=f"Provider '{provider}' is not supported. Use 'anthropic', 'openai', or 'ollama'.",
        )


def _get_anthropic_model(model: str, temperature: float) -> BaseChatModel:
    """Create an Anthropic chat model."""
    from langchain_anthropic import ChatAnthropic

    if not settings.anthropic_api_key.get_secret_value():
        raise ConfigurationError(
            message="Anthropic API key not configured",
            config_key="anthropic_api_key",
            user_message="Please set ANTHROPIC_API_KEY in your environment or .env file.",
        )

    return ChatAnthropic(  # type: ignore[call-arg]
        model=model,
        api_key=settings.anthropic_api_key,
        temperature=temperature,
        max_tokens=8192,
    )


def _get_openai_model(model: str, temperature: float) -> BaseChatModel:
    """Create an OpenAI chat model."""
    from langchain_openai import ChatOpenAI

    if not settings.openai_api_key.get_secret_value():
        raise ConfigurationError(
            message="OpenAI API key not configured",
            config_key="openai_api_key",
            user_message="Please set OPENAI_API_KEY in your environment or .env file.",
        )

    restricted = is_restricted_openai_model(model)

    if restricted and temperature != 1.0:
        logger.warning(
            "Model %s does not support temperature=%.1f, using default (1.0)",
            model,
            temperature,
        )

    # Reasoning models (gpt-5, o1, o3) use max_completion_tokens for BOTH
    # internal reasoning AND output. 4096 is not enough — reasoning alone
    # can consume the entire budget, leaving zero tokens for actual output.
    max_tokens = 16384 if restricted else 4096

    return ChatOpenAI(
        model=model,
        api_key=settings.openai_api_key,
        temperature=1.0 if restricted else temperature,
        max_completion_tokens=max_tokens,  # pyright: ignore[reportCallIssue]
    )


def _get_ollama_model(model: str, temperature: float) -> BaseChatModel:
    """Create an Ollama chat model (local LLM)."""
    from langchain_ollama import ChatOllama

    timeout = settings.ollama_timeout
    return ChatOllama(
        model=model,
        base_url=settings.ollama_base_url,
        temperature=temperature,
        num_predict=4096,
        reasoning=False,  # disable thinking phase — required for structured output
        client_kwargs={"timeout": timeout},
        sync_client_kwargs={"timeout": timeout},
    )
