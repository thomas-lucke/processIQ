import os
from typing import Literal

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from processiq.model_presets import PROVIDER_DEFAULTS, get_model_for_task


class LLMTaskConfig(BaseModel):
    """Model configuration override for a specific task.

    All fields are optional - unset fields inherit from global settings.
    """

    provider: Literal["anthropic", "openai", "ollama"] | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


# Task names used throughout the application
TASK_EXTRACTION = "extraction"
TASK_CLARIFICATION = "clarification"
TASK_EXPLANATION = "explanation"
TASK_ANALYSIS = "analysis"
TASK_INVESTIGATION = "investigation"

# Analysis mode presets (user-friendly model selection)
ANALYSIS_MODE_COST = "cost_optimized"
ANALYSIS_MODE_BALANCED = "balanced"
ANALYSIS_MODE_DEEP = "deep_analysis"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Persistence (conversation state checkpointing)
    persistence_enabled: bool = Field(
        default=True,
        description="Enable conversation state persistence with SqliteSaver.",
    )
    persistence_db_path: str = Field(
        default="data/processiq.db",
        description="Path to SQLite database for conversation persistence.",
    )

    # API Keys
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    langsmith_api_key: SecretStr = SecretStr("")
    langsmith_endpoint: str = "https://eu.api.smith.langchain.com"
    langsmith_tracing: bool = True
    langchain_project: str = "processiq"

    # LLM Configuration
    llm_provider: Literal["anthropic", "openai", "ollama"] = "openai"
    llm_model: str = ""  # Empty = use provider default
    llm_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="LLM temperature (0.0 for deterministic output)",
    )
    llm_explanations_enabled: bool = Field(
        default=True,
        description="Enable LLM-generated explanations. Disable for testing or cost control.",
    )
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout: int = Field(
        default=120,
        ge=10,
        description=(
            "Request timeout in seconds for Ollama LLM calls. "
            "Increase this if your hardware is slow and requests time out. "
            "On CPU-only machines, 300+ seconds may be needed for large models."
        ),
    )

    # Per-task LLM overrides (JSON format in env vars)
    # Example: LLM_TASK_EXTRACTION='{"model": "gpt-5-nano"}'
    llm_task_extraction: LLMTaskConfig = Field(default_factory=LLMTaskConfig)
    llm_task_clarification: LLMTaskConfig = Field(default_factory=LLMTaskConfig)
    llm_task_explanation: LLMTaskConfig = Field(default_factory=LLMTaskConfig)
    llm_task_analysis: LLMTaskConfig = Field(default_factory=LLMTaskConfig)
    llm_task_investigation: LLMTaskConfig = Field(default_factory=LLMTaskConfig)

    # Agentic investigation loop
    agent_loop_slider_enabled: bool = Field(
        default=False,
        description="Show cycle depth slider in Advanced Options. ENV: AGENT_LOOP_SLIDER_ENABLED",
    )
    agent_max_cycles: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max investigation turns (LLM decisions, not tool call count). ENV: AGENT_MAX_CYCLES",
    )

    # Application
    log_level: str = "INFO"  # DEBUG for development, INFO for demo
    confidence_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum confidence to proceed without asking for more data",
    )

    def get_default_model(self, provider: str | None = None) -> str:
        """Get the default model for a provider.

        Args:
            provider: Provider to get default for. If None, uses configured provider.

        Returns:
            Model name string.
        """
        if provider is None:
            provider = self.llm_provider
        if provider == self.llm_provider and self.llm_model:
            return self.llm_model
        return PROVIDER_DEFAULTS.get(provider, "gpt-5-nano")

    def get_task_config(self, task: str) -> LLMTaskConfig:
        """Get the LLM configuration for a specific task.

        Args:
            task: Task name (extraction, clarification, explanation, analysis).

        Returns:
            LLMTaskConfig with task-specific overrides (may have None fields).
        """
        task_configs = {
            TASK_EXTRACTION: self.llm_task_extraction,
            TASK_CLARIFICATION: self.llm_task_clarification,
            TASK_EXPLANATION: self.llm_task_explanation,
            TASK_ANALYSIS: self.llm_task_analysis,
            TASK_INVESTIGATION: self.llm_task_investigation,
        }
        return task_configs.get(task, LLMTaskConfig())

    def get_resolved_config(
        self,
        task: str | None = None,
        analysis_mode: str | None = None,
        provider: str | None = None,
    ) -> tuple[str, str, float]:
        """Get fully resolved LLM config (provider, model, temperature).

        Resolution order (first non-None wins):
        1. Model presets (provider + analysis_mode + task -> model_presets.py)
        2. Task-specific env var config
        3. Global settings

        Args:
            task: Optional task name for task-specific overrides.
            analysis_mode: Optional analysis mode preset (cost_optimized, balanced, deep_analysis).
            provider: Optional provider override (from UI selection).

        Returns:
            Tuple of (provider, model, temperature).
        """
        # Start with global defaults
        resolved_provider = provider or self.llm_provider
        temperature = self.llm_temperature
        model: str | None = None

        # Apply model presets from model_presets.py
        if analysis_mode and task:
            preset_model = get_model_for_task(resolved_provider, analysis_mode, task)
            if preset_model:
                model = preset_model

        # Apply task-specific env var overrides (can override preset if explicitly set)
        if task:
            task_config = self.get_task_config(task)
            if task_config.provider:
                resolved_provider = task_config.provider
            if task_config.temperature is not None:
                temperature = task_config.temperature
            if task_config.model:
                model = task_config.model

        # Get model if not yet set (from provider default)
        if model is None:
            model = self.get_default_model(resolved_provider)

        return resolved_provider, model, temperature


settings = Settings()

# Propagate LangSmith config to os.environ so the SDK can auto-detect it.
# pydantic-settings reads .env into Python attributes but does NOT set os.environ,
# which is what the LangSmith SDK checks directly.
_langsmith_key = settings.langsmith_api_key.get_secret_value()
if _langsmith_key:
    os.environ.setdefault("LANGSMITH_API_KEY", _langsmith_key)
if settings.langsmith_tracing:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGSMITH_TRACING", "true")
os.environ.setdefault("LANGSMITH_ENDPOINT", settings.langsmith_endpoint)
os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)
