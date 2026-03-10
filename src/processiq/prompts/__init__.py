"""Jinja2 prompt template loader for ProcessIQ.

Usage:
    from processiq.prompts import render_prompt

    # Render a template with variables
    prompt = render_prompt("system", profile=business_profile)
    prompt = render_prompt("analyze", metrics_text="...", industry="technology")

Available templates:
    - system: Base system prompt for the agent
    - extraction: Extract process data from text
    - analyze: LLM-based process analysis
    - clarification: Generate questions for missing data
    - improvement_suggestions: Post-extraction data quality hints
    - followup: Answer follow-up questions about analysis results
"""

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

logger = logging.getLogger(__name__)

# Template directory is the same directory as this file
TEMPLATE_DIR = Path(__file__).parent

# Create Jinja2 environment
_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
)


def render_prompt(template_name: str, **kwargs: Any) -> str:
    """Render a prompt template with the given variables.

    Args:
        template_name: Name of the template (without .j2 extension)
        **kwargs: Variables to pass to the template

    Returns:
        Rendered prompt string

    Raises:
        TemplateNotFound: If template doesn't exist
        jinja2.TemplateError: If template has syntax errors

    Example:
        >>> prompt = render_prompt("analyze",
        ...     metrics_text="Process: 5 steps, 10h total",
        ...     industry="technology",
        ... )
    """
    template_file = f"{template_name}.j2"

    try:
        template = _env.get_template(template_file)
        rendered: str = template.render(**kwargs)
        logger.debug("Rendered template: %s", template_name)
        return rendered.strip()
    except TemplateNotFound:
        logger.error("Template not found: %s", template_file)
        raise


def list_templates() -> list[str]:
    """List all available template names."""
    return [p.stem for p in TEMPLATE_DIR.glob("*.j2")]


def get_template_path(template_name: str) -> Path:
    """Get the file path for a template."""
    return TEMPLATE_DIR / f"{template_name}.j2"


# Convenience functions for common prompts


def get_system_prompt(
    profile: Any | None = None,
) -> str:
    """Get the system prompt, optionally with business profile context."""
    return render_prompt("system", profile=profile)


def get_extraction_prompt(
    content: str,
    additional_context: str = "",
    hints: list[str] | None = None,
    conversation_context: str = "",
) -> str:
    """Get the extraction prompt for parsing process data from text.

    Args:
        content: Raw text content to extract from (text description, table dump, etc.).
        additional_context: Optional context about the business or process.
        hints: Optional list of hints for the LLM.
        conversation_context: Optional context with current process data and recent
            messages for handling edit requests like "change step 3 time to 2 hours".

    Returns:
        Rendered prompt string.
    """
    return render_prompt(
        "extraction",
        content=content,
        additional_context=additional_context,
        hints=hints,
        conversation_context=conversation_context,
    )


def get_clarification_prompt(
    confidence: float,
    phase: str,
    data_gaps: list[str],
    partial_results: list[str] | None = None,
) -> str:
    """Get prompt for generating clarification questions."""
    return render_prompt(
        "clarification",
        confidence=confidence * 100,  # Convert to percentage
        phase=phase,
        data_gaps=data_gaps,
        partial_results=partial_results,
    )


def get_improvement_suggestions_prompt(
    process_name: str,
    step_count: int,
    steps_with_time: int,
    steps_with_cost: int,
    steps_with_errors: int,
    steps_with_dependencies: int,
    data_gaps: list[str] | None = None,
) -> str:
    """Get prompt for generating post-extraction improvement suggestions.

    Args:
        process_name: Name of the extracted process.
        step_count: Total number of steps extracted.
        steps_with_time: Count of steps that have time estimates.
        steps_with_cost: Count of steps that have cost data.
        steps_with_errors: Count of steps that have error rates.
        steps_with_dependencies: Count of steps that have dependencies defined.
        data_gaps: List of identified data gaps from confidence calculation.

    Returns:
        Rendered prompt string for LLM to generate improvement suggestions.
    """
    return render_prompt(
        "improvement_suggestions",
        process_name=process_name,
        step_count=step_count,
        steps_with_time=steps_with_time,
        steps_with_cost=steps_with_cost,
        steps_with_errors=steps_with_errors,
        steps_with_dependencies=steps_with_dependencies,
        data_gaps=data_gaps,
    )


def get_analysis_prompt(
    metrics_text: str,
    business_context: str | None = None,
    constraints_summary: str | None = None,
    user_concerns: str | None = None,
    feedback_history: str | None = None,
    similar_past_analyses: list[Any] | None = None,
    persistent_rejections: list[Any] | None = None,
    cross_session_patterns: list[str] | None = None,
) -> str:
    """Get prompt for LLM-based process analysis.

    This is the core prompt for the new analysis architecture where
    the LLM makes judgments about what's a problem vs core value.

    Args:
        metrics_text: Pre-calculated metrics formatted by format_metrics_for_llm().
        business_context: Optional formatted business context (industry, size, revenue, notes).
        constraints_summary: Optional summary of active constraints.
        user_concerns: Optional user-stated concerns to address.
        feedback_history: Optional formatted feedback from previous recommendations.
        similar_past_analyses: Optional list of similar past analyses from ChromaDB.
        persistent_rejections: Optional list of (title, reason) tuples from past sessions.
        cross_session_patterns: Optional list of detected cross-session patterns.

    Returns:
        Rendered prompt string for process analysis.
    """
    return render_prompt(
        "analyze",
        metrics_text=metrics_text,
        business_context=business_context,
        constraints_summary=constraints_summary,
        user_concerns=user_concerns,
        feedback_history=feedback_history,
        similar_past_analyses=similar_past_analyses,
        persistent_rejections=persistent_rejections,
        cross_session_patterns=cross_session_patterns,
    )


def get_investigation_system_prompt(
    insight: Any | None = None,
    profile: Any | None = None,
    constraints: Any | None = None,
) -> str:
    """Get the system prompt for the agentic investigation loop.

    Rendered once per investigate_node execution (prepended as SystemMessage).

    Args:
        insight: The AnalysisInsight from initial analysis.
        profile: Optional BusinessProfile for user context.
        constraints: Optional Constraints for feasibility checks.

    Returns:
        Rendered system prompt string.
    """
    return render_prompt(
        "investigation_system",
        insight=insight,
        profile=profile,
        constraints=constraints,
    )
