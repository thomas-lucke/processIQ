"""Tests for processiq.config — Settings, task config resolution."""

import pytest
from pydantic import ValidationError

from processiq.config import (
    ANALYSIS_MODE_BALANCED,
    ANALYSIS_MODE_COST,
    ANALYSIS_MODE_DEEP,
    TASK_ANALYSIS,
    TASK_CLARIFICATION,
    TASK_EXPLANATION,
    TASK_EXTRACTION,
    TASK_INVESTIGATION,
    LLMTaskConfig,
    Settings,
)

# ---------------------------------------------------------------------------
# LLMTaskConfig
# ---------------------------------------------------------------------------


class TestLLMTaskConfig:
    def test_all_defaults_none(self):
        config = LLMTaskConfig()
        assert config.provider is None
        assert config.model is None
        assert config.temperature is None

    def test_temperature_validation_upper(self):
        with pytest.raises(ValidationError):
            LLMTaskConfig(temperature=2.1)

    def test_temperature_validation_lower(self):
        with pytest.raises(ValidationError):
            LLMTaskConfig(temperature=-0.1)

    def test_valid_temperature_boundary(self):
        c = LLMTaskConfig(temperature=0.0)
        assert c.temperature == 0.0
        c2 = LLMTaskConfig(temperature=2.0)
        assert c2.temperature == 2.0

    def test_valid_provider_values(self):
        for p in ("anthropic", "openai", "ollama"):
            c = LLMTaskConfig(provider=p)
            assert c.provider == p

    def test_invalid_provider_rejected(self):
        with pytest.raises(ValidationError):
            LLMTaskConfig(provider="gemini")


# ---------------------------------------------------------------------------
# Settings.get_task_config
# ---------------------------------------------------------------------------


class TestGetTaskConfig:
    def test_known_tasks_return_config(self):
        s = Settings()
        for task in (
            TASK_EXTRACTION,
            TASK_CLARIFICATION,
            TASK_EXPLANATION,
            TASK_ANALYSIS,
            TASK_INVESTIGATION,
        ):
            config = s.get_task_config(task)
            assert isinstance(config, LLMTaskConfig)

    def test_unknown_task_returns_empty_config(self):
        s = Settings()
        config = s.get_task_config("nonexistent_task")
        assert isinstance(config, LLMTaskConfig)
        assert config.model is None

    def test_returns_different_configs_per_task(self):
        """Task configs are independent objects."""
        s = Settings()
        c1 = s.get_task_config(TASK_EXTRACTION)
        c2 = s.get_task_config(TASK_ANALYSIS)
        # Both are LLMTaskConfig, but they are separate instances
        assert isinstance(c1, LLMTaskConfig)
        assert isinstance(c2, LLMTaskConfig)


# ---------------------------------------------------------------------------
# Settings.get_default_model
# ---------------------------------------------------------------------------


class TestGetDefaultModel:
    def test_returns_string(self):
        s = Settings()
        model = s.get_default_model("openai")
        assert isinstance(model, str)
        assert len(model) > 0

    def test_different_providers_may_return_different_models(self):
        s = Settings()
        openai_model = s.get_default_model("openai")
        anthropic_model = s.get_default_model("anthropic")
        # Both should be non-empty strings
        assert openai_model
        assert anthropic_model

    def test_none_provider_uses_configured(self):
        s = Settings()
        result = s.get_default_model(None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_custom_model_returned_for_configured_provider(self):
        s = Settings(llm_provider="openai", llm_model="gpt-custom-test")
        assert s.get_default_model("openai") == "gpt-custom-test"

    def test_other_provider_not_affected_by_custom_model(self):
        s = Settings(llm_provider="openai", llm_model="gpt-custom-test")
        # anthropic model should NOT be "gpt-custom-test"
        anthropic_model = s.get_default_model("anthropic")
        assert anthropic_model != "gpt-custom-test"


# ---------------------------------------------------------------------------
# Settings.get_resolved_config
# ---------------------------------------------------------------------------


class TestGetResolvedConfig:
    def test_returns_three_tuple(self):
        s = Settings()
        result = s.get_resolved_config()
        assert len(result) == 3

    def test_provider_string_in_result(self):
        s = Settings()
        provider, model, temperature = s.get_resolved_config()
        assert isinstance(provider, str)
        assert isinstance(model, str)
        assert isinstance(temperature, float)

    def test_explicit_provider_override_used(self):
        s = Settings(llm_provider="openai")
        provider, _, _ = s.get_resolved_config(provider="anthropic")
        assert provider == "anthropic"

    def test_task_only_returns_valid_config(self):
        s = Settings()
        provider, model, temperature = s.get_resolved_config(task=TASK_ANALYSIS)
        assert provider in ("anthropic", "openai", "ollama")
        assert model
        assert 0.0 <= temperature <= 2.0

    def test_analysis_mode_and_task_returns_valid(self):
        s = Settings()
        for mode in (ANALYSIS_MODE_COST, ANALYSIS_MODE_BALANCED, ANALYSIS_MODE_DEEP):
            provider, model, temp = s.get_resolved_config(
                task=TASK_ANALYSIS, analysis_mode=mode
            )
            assert provider
            assert model
            assert 0.0 <= temp <= 2.0

    def test_temperature_within_valid_range(self):
        s = Settings(llm_temperature=0.7)
        _, _, temperature = s.get_resolved_config()
        assert 0.0 <= temperature <= 2.0

    def test_task_config_provider_override(self):
        """Task-specific provider in env config should override global."""
        task_cfg = LLMTaskConfig(
            provider="anthropic", model="claude-haiku-4-5-20251001"
        )
        s = Settings(llm_provider="openai", llm_task_analysis=task_cfg)
        provider, model, _ = s.get_resolved_config(task=TASK_ANALYSIS)
        assert provider == "anthropic"
        assert model == "claude-haiku-4-5-20251001"

    def test_task_config_temperature_override(self):
        task_cfg = LLMTaskConfig(temperature=0.9)
        s = Settings(llm_temperature=0.0, llm_task_analysis=task_cfg)
        _, _, temperature = s.get_resolved_config(task=TASK_ANALYSIS)
        assert temperature == 0.9


# ---------------------------------------------------------------------------
# Settings constants
# ---------------------------------------------------------------------------


class TestSettingsConstants:
    def test_task_name_constants_are_strings(self):
        for task in (
            TASK_EXTRACTION,
            TASK_CLARIFICATION,
            TASK_EXPLANATION,
            TASK_ANALYSIS,
            TASK_INVESTIGATION,
        ):
            assert isinstance(task, str)

    def test_analysis_mode_constants_are_strings(self):
        for mode in (ANALYSIS_MODE_COST, ANALYSIS_MODE_BALANCED, ANALYSIS_MODE_DEEP):
            assert isinstance(mode, str)

    def test_default_confidence_threshold_valid(self):
        s = Settings()
        assert 0.0 <= s.confidence_threshold <= 1.0

    def test_default_agent_max_cycles_valid(self):
        s = Settings()
        assert 1 <= s.agent_max_cycles <= 10

    def test_confidence_threshold_validation(self):
        with pytest.raises(ValidationError):
            Settings(confidence_threshold=1.5)
        with pytest.raises(ValidationError):
            Settings(confidence_threshold=-0.1)

    def test_agent_max_cycles_validation(self):
        with pytest.raises(ValidationError):
            Settings(agent_max_cycles=0)
        with pytest.raises(ValidationError):
            Settings(agent_max_cycles=11)
