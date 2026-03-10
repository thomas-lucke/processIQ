"""LangGraph node functions for ProcessIQ agent.

Each node represents a step in the analysis pipeline.
Nodes log entry/exit and return state updates.

Architecture:
- Algorithms calculate FACTS (metrics, percentages, dependencies)
- LLM makes JUDGMENTS (what's a problem, what's core value)
- ROI estimates come from LLM recommendations (contextual, not formulaic)
"""

import logging
from typing import Any

from processiq.agent.state import AgentState
from processiq.analysis import (
    ConfidenceResult,
    calculate_confidence,
    calculate_process_metrics,
    format_metrics_for_llm,
    identify_critical_gaps,
)
from processiq.config import TASK_ANALYSIS, TASK_INVESTIGATION, settings
from processiq.models import (
    AnalysisInsight,
    BusinessProfile,
    Constraints,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM Helper Functions
# ---------------------------------------------------------------------------


def _get_llm_model(
    task: str | None = None,
    analysis_mode: str | None = None,
    provider: str | None = None,
) -> Any:
    """Get the LLM model, with lazy import to avoid circular dependencies.

    Args:
        task: Optional task name for task-specific model config.
        analysis_mode: Optional analysis mode preset.
        provider: Optional provider override.
    """
    from processiq.llm import get_chat_model

    return get_chat_model(task=task, analysis_mode=analysis_mode, provider=provider)


# ---------------------------------------------------------------------------
# Graph Nodes
# ---------------------------------------------------------------------------


def check_context_sufficiency(state: AgentState) -> dict[str, Any]:
    """Node: Check if we have sufficient context to proceed.

    Agentic Decision Point #1: Decides whether to ask for more data
    or proceed with analysis.
    """
    logger.info("Node: check_context_sufficiency - START")

    process = state.get("process")
    if process is None:
        raise ValueError("AgentState missing required 'process' field")
    constraints = state.get("constraints")
    profile = state.get("profile")

    confidence_result: ConfidenceResult = calculate_confidence(
        process=process,
        constraints=constraints,
        profile=profile,
    )

    reasoning = f"Context check: confidence={confidence_result.score:.1%} ({confidence_result.level})"

    if not confidence_result.is_sufficient:
        critical_gaps = identify_critical_gaps(confidence_result)
        reasoning += f", identified {len(critical_gaps)} critical gaps"
        logger.info("Context insufficient, needs clarification")

        return {
            "confidence_score": confidence_result.score,
            "data_gaps": confidence_result.data_gaps,
            "needs_clarification": True,
            "clarification_questions": confidence_result.suggestions_for_improvement[
                :3
            ],
            "reasoning_trace": [*state.get("reasoning_trace", []), reasoning],
            "current_phase": "needs_clarification",
        }

    logger.info("Context sufficient, proceeding to analysis")
    return {
        "confidence_score": confidence_result.score,
        "data_gaps": confidence_result.data_gaps,
        "needs_clarification": False,
        "reasoning_trace": [*state.get("reasoning_trace", []), reasoning],
        "current_phase": "analysis",
    }


def initial_analysis_node(state: AgentState) -> dict[str, Any]:
    """Node: Run initial single-pass LLM analysis.

    Algorithms calculate FACTS (time percentages, dependencies, patterns).
    LLM makes JUDGMENTS (what's a problem vs core value).

    The LLM receives structured metrics and returns AnalysisInsight with:
    - Issues (problems with root cause hypotheses)
    - Recommendations (tied to specific issues)
    - Not-problems (steps that look slow but are core value)

    After analysis, caches ProcessMetrics in state and seeds the investigation
    message history for the investigation loop.
    """
    from langchain_core.messages import HumanMessage

    logger.info("Node: initial_analysis - START")

    process = state.get("process")
    if process is None:
        raise ValueError("AgentState missing required 'process' field")

    constraints = state.get("constraints")
    profile = state.get("profile")

    # Calculate metrics (FACTS, not judgments)
    metrics = calculate_process_metrics(process)
    metrics_text = format_metrics_for_llm(metrics)

    logger.debug(
        "Metrics calculated: %d steps, %.1fh total, %d reviews, %d external",
        metrics.step_count,
        metrics.total_time_hours,
        metrics.patterns.review_step_count,
        metrics.patterns.external_touchpoints,
    )

    # Build context for LLM
    business_context = _format_business_context_for_llm(profile) if profile else None
    constraints_summary = (
        _format_constraints_for_llm(constraints) if constraints else None
    )

    # Format feedback history (if user has rated previous recommendations)
    feedback = state.get("feedback_history", {})
    feedback_text = _format_feedback_history(feedback) if feedback else None

    # Persistent memory context (from RAG retrieval in interface.py)
    similar_past = state.get("similar_past_analyses") or None
    persistent_rejections = state.get("persistent_rejections") or None
    cross_session_patterns = state.get("cross_session_patterns") or None

    # Call LLM for analysis
    analysis_mode = state.get("analysis_mode")
    llm_provider = state.get("llm_provider")
    timed_out = False
    try:
        insight = _run_llm_analysis(
            metrics_text=metrics_text,
            business_context=business_context,
            constraints_summary=constraints_summary,
            profile=profile,
            analysis_mode=analysis_mode,
            llm_provider=llm_provider,
            feedback_history=feedback_text,
            similar_past_analyses=similar_past,
            persistent_rejections=persistent_rejections,
            cross_session_patterns=cross_session_patterns,
        )
    except TimeoutError:
        insight = None
        timed_out = True

    if insight is None:
        logger.warning("LLM analysis failed, no insight produced")
        error_msg = "timeout" if timed_out else "LLM analysis failed. Please try again."
        return {
            "analysis_insight": None,
            "process_metrics": metrics,
            "error": error_msg,
            "reasoning_trace": [
                *state.get("reasoning_trace", []),
                "LLM analysis failed",
            ],
            "current_phase": "finalization",
        }

    logger.info(
        "Node: initial_analysis - DONE: %d issues, %d recommendations, %d not-problems",
        len(insight.issues),
        len(insight.recommendations),
        len(insight.not_problems),
    )

    reasoning = (
        f"Initial analysis: {len(insight.issues)} issues identified, "
        f"{len(insight.recommendations)} recommendations, "
        f"{len(insight.not_problems)} steps identified as core value (not waste)"
    )

    # Seed investigation message history
    user_context = profile.notes.strip() if profile and profile.notes else ""
    issue_summary = (
        "\n".join(f"- {i.title} (severity={i.severity})" for i in insight.issues)
        if insight.issues
        else "No issues found."
    )
    investigation_seed = (
        f"Initial analysis complete.\n\n"
        f"Issues found:\n{issue_summary}\n\n"
        + (f"User context: {user_context}\n\n" if user_context else "")
        + "Use the available tools to investigate issues that warrant deeper analysis. "
        "Stop calling tools when you have gathered enough to refine the recommendations."
    )

    return {
        "analysis_insight": insight,
        "process_metrics": metrics,
        "messages": [HumanMessage(content=investigation_seed)],
        "reasoning_trace": [*state.get("reasoning_trace", []), reasoning],
        "current_phase": "investigation",
    }


def investigate_node(state: AgentState) -> dict[str, Any]:
    """Node: LLM with tool access decides what to investigate.

    Uses native function calling. Loops via tool_node until the LLM stops
    calling tools or the cycle limit is reached.

    Falls back to finalize immediately if the provider does not support
    tool calling (e.g., some Ollama models).
    """
    from langchain_core.messages import AIMessage, SystemMessage

    from processiq.agent.tools import INVESTIGATION_TOOLS
    from processiq.prompts import get_investigation_system_prompt

    cycle = state.get("cycle_count", 0)
    logger.info("Node: investigate - START (cycle %d)", cycle)

    # Ollama fallback: not all local models support function calling
    provider = state.get("llm_provider") or settings.llm_provider
    if provider == "ollama":
        logger.info("Node: investigate - Ollama provider, skipping tool loop")
        return {"current_phase": "finalization"}

    model = _get_llm_model(
        task=TASK_INVESTIGATION,
        analysis_mode=state.get("analysis_mode"),
        provider=state.get("llm_provider"),
    )
    model_with_tools = model.bind_tools(INVESTIGATION_TOOLS)

    # Build message list: system prompt + accumulated messages
    system_msg = SystemMessage(
        content=get_investigation_system_prompt(
            insight=state.get("analysis_insight"),
            profile=state.get("profile"),
            constraints=state.get("constraints"),
        )
    )
    messages = [system_msg, *state.get("messages", [])]

    response: AIMessage = model_with_tools.invoke(messages)

    tool_calls = getattr(response, "tool_calls", [])
    logger.info("Node: investigate - DONE: %d tool call(s) requested", len(tool_calls))

    return {
        "messages": [response],
        "cycle_count": cycle + (1 if tool_calls else 0),
        "current_phase": "investigating" if tool_calls else "finalization",
    }


def finalize_analysis_node(state: AgentState) -> dict[str, Any]:
    """Node: Finalize and package the analysis results.

    Incorporates any tool findings from the investigation loop into the
    structured AnalysisInsight.investigation_findings field.
    """
    from langchain_core.messages import ToolMessage

    logger.info("Node: finalize_analysis - START")

    insight = state.get("analysis_insight")
    confidence = state.get("confidence_score", 0.0)
    error = state.get("error")

    # Extract tool results from message history into the structured field
    tool_findings = [
        msg.content
        for msg in state.get("messages", [])
        if isinstance(msg, ToolMessage) and msg.content
    ]

    if tool_findings and insight:
        insight.investigation_findings = tool_findings
        logger.info(
            "Node: finalize_analysis - incorporated %d investigation finding(s)",
            len(tool_findings),
        )

    if error:
        reasoning = f"Analysis finalized with error: {error}"
    elif insight:
        findings_note = (
            f", {len(tool_findings)} investigation finding(s)" if tool_findings else ""
        )
        reasoning = (
            f"Analysis finalized: {len(insight.issues)} issues, "
            f"{len(insight.recommendations)} recommendations, "
            f"confidence={confidence:.0%}{findings_note}"
        )
    else:
        reasoning = "Analysis finalized with no results"

    logger.info("Node: finalize_analysis - DONE (confidence=%.0f%%)", confidence * 100)

    return {
        "reasoning_trace": [*state.get("reasoning_trace", []), reasoning],
        "current_phase": "complete",
    }


# ---------------------------------------------------------------------------
# LLM Analysis Helpers
# ---------------------------------------------------------------------------


def _format_feedback_history(feedback: dict[str, dict[str, object]]) -> str | None:
    """Format recommendation feedback into text for the LLM prompt.

    Args:
        feedback: Dict keyed by recommendation title, values have
                  "vote" ("up"/"down") and optional "reason".

    Returns:
        Formatted text for the prompt, or None if no feedback.
    """
    if not feedback:
        return None

    lines = []
    rejected = [(t, f) for t, f in feedback.items() if f["vote"] == "down"]
    accepted = [(t, f) for t, f in feedback.items() if f["vote"] == "up"]

    if rejected:
        lines.append("REJECTED recommendations (do NOT suggest these again):")
        for title, f in rejected:
            reason = f.get("reason")
            if reason:
                lines.append(f'- "{title}" -- Reason: {reason}')
            else:
                lines.append(f'- "{title}" -- (no reason given)')

    if accepted:
        if lines:
            lines.append("")
        lines.append("ACCEPTED recommendations (user found these valuable):")
        for title, _ in accepted:
            lines.append(f'- "{title}"')

    return "\n".join(lines) if lines else None


def _normalize_issue_links(insight: AnalysisInsight) -> AnalysisInsight:
    """Fix addresses_issue fields that don't exactly match any issue title.

    The LLM sometimes generates addresses_issue with slightly different casing
    or wording than the issue.title it was meant to reference. This breaks the
    exact-match grouping in the UI, leaving recommendations unlinked.

    Resolution order:
    1. Exact match (already correct — leave as-is)
    2. Case-insensitive match
    3. Substring match (addresses_issue is contained in a title, or vice versa)
    4. Leave unchanged (unlinked recommendation, renders separately)
    """
    if not insight.issues or not insight.recommendations:
        return insight

    issue_titles = [i.title for i in insight.issues]
    title_lower = {t.lower(): t for t in issue_titles}

    for rec in insight.recommendations:
        ai = rec.addresses_issue
        if not ai:
            continue

        # 1. Exact match — nothing to do
        if ai in issue_titles:
            continue

        # 2. Case-insensitive match
        canonical = title_lower.get(ai.lower())
        if canonical:
            logger.debug(
                "Normalized addresses_issue %r -> %r (case-insensitive)", ai, canonical
            )
            rec.addresses_issue = canonical
            continue

        # 3. Substring match
        ai_lower = ai.lower()
        for title in issue_titles:
            if ai_lower in title.lower() or title.lower() in ai_lower:
                logger.debug(
                    "Normalized addresses_issue %r -> %r (substring)", ai, title
                )
                rec.addresses_issue = title
                break

    return insight


def _run_llm_analysis(
    metrics_text: str,
    business_context: str | None = None,
    constraints_summary: str | None = None,
    profile: BusinessProfile | None = None,
    analysis_mode: str | None = None,
    llm_provider: str | None = None,
    feedback_history: str | None = None,
    similar_past_analyses: list[dict[str, Any]] | None = None,
    persistent_rejections: list[tuple[str, str]] | None = None,
    cross_session_patterns: list[str] | None = None,
) -> AnalysisInsight | None:
    """Run LLM-based process analysis using structured output.

    Uses LangChain's with_structured_output() for guaranteed schema compliance.
    The LLM returns an AnalysisInsight directly via tool calling -- no manual
    JSON parsing needed.

    Returns AnalysisInsight on success, None on failure.
    Retries once on failure.
    """
    if not settings.llm_explanations_enabled:
        logger.debug("LLM explanations disabled, skipping LLM analysis")
        return None

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from processiq.prompts import get_analysis_prompt, get_system_prompt

        model = _get_llm_model(
            task=TASK_ANALYSIS,
            analysis_mode=analysis_mode,
            provider=llm_provider,
        )

        structured_model = model.with_structured_output(AnalysisInsight)

        system_msg = get_system_prompt(profile=profile)
        user_msg = get_analysis_prompt(
            metrics_text=metrics_text,
            business_context=business_context,
            constraints_summary=constraints_summary,
            feedback_history=feedback_history,
            similar_past_analyses=similar_past_analyses,
            persistent_rejections=persistent_rejections,
            cross_session_patterns=cross_session_patterns,
        )

        messages = [
            SystemMessage(content=system_msg),
            HumanMessage(content=user_msg),
        ]

        # Try up to 2 times (retry once on failure)
        for attempt in range(2):
            logger.debug(
                "Calling LLM for process analysis (attempt %d)...", attempt + 1
            )

            try:
                result = structured_model.invoke(messages)
                insight: AnalysisInsight | None = (
                    result if isinstance(result, AnalysisInsight) else None
                )
            except Exception as e:
                err_str = str(e).lower()
                is_timeout = (
                    "timed out" in err_str
                    or "timeout" in err_str
                    or "read timeout" in err_str
                )
                logger.warning(
                    "Structured output failed on attempt %d: %s", attempt + 1, e
                )
                if is_timeout:
                    raise TimeoutError("LLM request timed out") from e
                if attempt >= 1:
                    return None
                continue

            if insight is None:
                logger.warning("LLM returned None on attempt %d", attempt + 1)
                if attempt == 0:
                    continue
                return None

            logger.info("LLM analysis parsed successfully via structured output")
            return _normalize_issue_links(insight)

        return None

    except Exception as e:
        logger.error("LLM analysis failed: %s", e)
        return None


def _format_business_context_for_llm(profile: BusinessProfile) -> str:
    """Format the full business profile as readable context for LLM."""
    from processiq.models.memory import RevenueRange

    parts = []

    # Industry
    if profile.industry is not None:
        industry_str = profile.custom_industry or profile.industry.value
        parts.append(f"Industry: {industry_str}")

    # Company size
    if profile.company_size is not None:
        size_labels = {
            "startup": "Startup (under 50 employees)",
            "small": "Small business (50-200 employees)",
            "mid_market": "Mid-market company (200-1000 employees)",
            "enterprise": "Enterprise (over 1000 employees)",
        }
        parts.append(
            f"Company size: {size_labels.get(profile.company_size.value, profile.company_size.value)}"
        )

    # Revenue range (only if provided)
    if profile.annual_revenue != RevenueRange.PREFER_NOT_TO_SAY:
        revenue_labels = {
            "under_100k": "Under $100K/year",
            "100k_to_500k": "$100K - $500K/year",
            "500k_to_1m": "$500K - $1M/year",
            "1m_to_5m": "$1M - $5M/year",
            "5m_to_20m": "$5M - $20M/year",
            "20m_to_100m": "$20M - $100M/year",
            "over_100m": "Over $100M/year",
        }
        parts.append(
            f"Annual revenue: {revenue_labels.get(profile.annual_revenue.value, profile.annual_revenue.value)}"
        )

    # Regulatory environment
    parts.append(f"Regulatory environment: {profile.regulatory_environment.value}")

    # Rejected approaches
    if profile.rejected_approaches:
        parts.append(
            f"Previously rejected approaches (DO NOT suggest): {', '.join(profile.rejected_approaches)}"
        )

    # Free-text notes (most important for context)
    if profile.notes and profile.notes.strip():
        parts.append(f"\nAdditional context from the user:\n{profile.notes.strip()}")

    return "\n".join(parts)


def _format_constraints_for_llm(constraints: Constraints) -> str:
    """Format constraints as a readable summary for LLM."""
    parts = []

    if constraints.budget_limit:
        parts.append(f"Budget limit: ${constraints.budget_limit:,.0f}")

    if constraints.cannot_hire:
        parts.append("Cannot hire new staff")

    if constraints.must_maintain_audit_trail:
        parts.append("Must maintain audit trail")

    if constraints.max_implementation_weeks:
        parts.append(
            f"Max implementation time: {constraints.max_implementation_weeks} weeks"
        )

    if constraints.max_error_rate_increase_pct:
        parts.append(
            f"Max acceptable error rate increase: {constraints.max_error_rate_increase_pct}%"
        )

    if constraints.priority:
        parts.append(f"Priority: {constraints.priority.value}")

    if constraints.custom_constraints:
        parts.append(
            "Additional constraints: " + "; ".join(constraints.custom_constraints)
        )

    return "; ".join(parts) if parts else "No specific constraints"
