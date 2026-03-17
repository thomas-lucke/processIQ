"""Jinja2 prompt template loader for ProcessIQ.

Usage:
    from processiq.prompts import render_prompt

    # Render a template with variables
    prompt = render_prompt("system", profile=business_profile)
    prompt = render_prompt("analyze", metrics_text="...", industry="technology")

Available templates:
    - system: Base system prompt for the agent
    - extract_new: Extract a new process from a first description
    - extract_update: Apply edits or supplements to existing process data
    - extract_estimate: Fill in missing values with estimates (user-requested)
    - extract_converse: Conversational response when input is too vague to extract
    - analyze: LLM-based process analysis
    - clarification: Generate questions when confidence is too low to analyze
    - improvement_suggestions: Post-extraction data quality hints
    - followup: Answer follow-up questions about analysis results
    - investigation_system: System prompt for the agentic investigation loop

Deprecated templates (kept for reference, no longer used):
    - extraction: Replaced by the four extract_* templates above
"""

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

logger = logging.getLogger(__name__)

# Template directory is the same directory as this file
TEMPLATE_DIR = Path(__file__).parent

# Create Jinja2 environment
# autoescape=False is intentional: templates render plain-text LLM prompts, not HTML.
# XSS is not a concern here. nosec B701
_env = Environment(  # nosec B701
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
    has_process: bool = False,
) -> str:
    """Route to the appropriate extraction prompt based on context and intent.

    This function replaces the old single extraction.j2 (which made the
    extract/update/estimate/converse routing decision internally via the LLM)
    with a deterministic code router.

    Scope note: this router only handles inputs that reach the extraction
    pipeline (extract_from_text / normalize_with_llm). Post-analysis follow-up
    questions ("explain recommendation X") are handled by a separate path
    (continue_conversation → followup.j2) and never reach this function.

    Routing logic:
        1. Conversational signal detected (question, meta-question about the
           tool, off-topic) → extract_converse regardless of has_process.
           Prevents conversational inputs from being misrouted to an update or
           extraction prompt that would treat them as process data.
        2. has_process=False → extract_new  (first extraction from description)
        3. has_process=True + estimate signal → extract_estimate
        4. has_process=True + anything else → extract_update

    Args:
        content: Raw text content from the user.
        additional_context: Optional business context to improve extraction.
        hints: Optional list of hints for the LLM.
        conversation_context: Serialised current process + recent messages.
            Non-empty means existing process data is present.
        has_process: True when process data already exists in the session.
            Overrides conversation_context presence check if explicitly set.

    Returns:
        Rendered prompt string for the selected template.
    """
    # Determine effective has_process: explicit flag or non-empty context
    effective_has_process = has_process or bool(conversation_context.strip())

    # Conversational inputs must be caught first, regardless of has_process.
    # Without this, a question typed into the extraction input while process
    # data exists would be routed to extract_update — wrong prompt, wrong task.
    if _is_conversational(content):
        template = "extract_converse"
    elif effective_has_process:
        template = _detect_update_template(content)
    else:
        template = "extract_new"

    logger.debug(
        "Extraction router: has_process=%s → template=%s",
        effective_has_process,
        template,
    )

    extra_vars: dict[str, Any] = {}
    if template == "extract_converse":
        extra_vars["has_process"] = effective_has_process

    return render_prompt(
        template,
        content=content,
        additional_context=additional_context,
        hints=hints,
        conversation_context=conversation_context,
        **extra_vars,
    )


def _is_conversational(content: str) -> bool:
    """Return True if the input is a question or conversational message.

    These should be routed to extract_converse regardless of whether process
    data exists — they are not describing or editing a process.
    """
    stripped = content.strip()
    lower = stripped.lower()

    # Ends with a question mark
    if stripped.endswith("?"):
        return True

    # Starts with a question word
    question_starters = (
        "what ",
        "why ",
        "how ",
        "when ",
        "where ",
        "who ",
        "which ",
        "can you ",
        "could you ",
        "would you ",
        "is there ",
        "are there ",
        "do you ",
        "does ",
        "should i ",
        "what's ",
        "what is ",
    )
    if any(lower.startswith(q) for q in question_starters):
        return True

    # Confirmation / done signals — short messages that indicate the user is
    # satisfied with the current state or wants to proceed, not editing data.
    # Only treated as conversational when the phrase is the dominant content
    # (i.e. the full message is short enough that it cannot be an edit instruction).
    done_signals = [
        "looks good",
        "looks right",
        "that's correct",
        "that's right",
        "thats correct",
        "thats right",
        "i'm done",
        "i'm finished",
        "im done",
        "im finished",
        "all done",
        "done editing",
        "please analyze",
        "ready to analyze",
        "analyze this",
        "analyze it",
        "this is correct",
        "this is right",
        "confirmed",
        "approve",
    ]
    # Only match if the message is short (≤ 60 chars) — longer messages likely
    # contain actual edit instructions that merely end with a confirmation phrase.
    return len(stripped) <= 60 and any(signal in lower for signal in done_signals)


def _detect_update_template(content: str) -> str:
    """Determine which update-mode template to use based on user intent signals.

    Called only when existing process data is present (has_process=True).

    Returns:
        "extract_estimate" if the user is asking for value estimation.
        "extract_update" for all other cases (edits, supplements, new data).
    """
    lower = content.lower()
    estimate_signals = [
        "estimate",
        "guess",
        "fill in",
        "fill out",
        "just assume",
        "approximate",
        "ballpark",
        "what would you say",
    ]
    if any(signal in lower for signal in estimate_signals):
        return "extract_estimate"
    return "extract_update"


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
    business_context: str | None = None,
    confidence_score: float | None = None,
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
        business_context: Optional formatted business context string. When
            provided, the LLM can calibrate suggestions to the business size
            and industry (e.g., cost benchmarks for an agency vs. enterprise).
        confidence_score: Overall confidence score (0.0-1.0). When below 0.6,
            the prompt instructs the LLM to open with a blocked-analysis notice.

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
        business_context=business_context,
        confidence_score=confidence_score,
    )


def get_analysis_prompt(
    metrics_text: str,
    business_context: str | None = None,
    constraints_summary: str | None = None,
    user_concerns: str | None = None,
    feedback_history: str | None = None,
    memory_brief: str | None = None,
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
        memory_brief: Optional pre-synthesised memory context from memory_synthesis_node.
            When provided, replaces the raw similar_past_analyses / persistent_rejections /
            cross_session_patterns blobs in the prompt.
        similar_past_analyses: Optional list of similar past analyses from ChromaDB.
            Ignored when memory_brief is set.
        persistent_rejections: Optional list of (title, reason) tuples from past sessions.
            Ignored when memory_brief is set.
        cross_session_patterns: Optional list of detected cross-session patterns.
            Ignored when memory_brief is set.

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
        memory_brief=memory_brief,
        similar_past_analyses=similar_past_analyses,
        persistent_rejections=persistent_rejections,
        cross_session_patterns=cross_session_patterns,
    )


def get_followup_prompt(
    user_question: str,
    insight: Any,
    constraints_summary: str | None = None,
    business_context: str | None = None,
    history: list[Any] | None = None,
) -> str:
    """Get prompt for answering follow-up questions about a completed analysis.

    Called after analysis is done when the user asks questions in chat
    (e.g. "explain recommendation 2", "what if we removed step 4?").

    Args:
        user_question: The user's follow-up message.
        insight: The AnalysisInsight from the completed analysis.
        constraints_summary: Optional formatted constraints string.
        business_context: Optional formatted business context string.
        history: Optional list of prior conversation turns (dicts with
            ``role`` and ``content`` keys).

    Returns:
        Rendered prompt string for the follow-up response.
    """
    return render_prompt(
        "followup",
        user_question=user_question,
        insight=insight,
        constraints_summary=constraints_summary,
        business_context=business_context,
        history=history or [],
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
