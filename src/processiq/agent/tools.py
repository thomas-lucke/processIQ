"""Investigation tools for the ProcessIQ agentic analysis loop.

Called by the LLM via native function calling in the investigate node.
InjectedState provides access to the full AgentState at call time without
exposing it to the LLM tool schema.

Design note: Tools read process_metrics from state when available (set by
initial_analysis_node) to avoid redundant recomputation. They fall back to
calculate_process_metrics() only if metrics are not in state.
"""

import logging
from typing import Annotated, Any

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from processiq.analysis import calculate_process_metrics

logger = logging.getLogger(__name__)


def _get_metrics(state: dict[str, Any]) -> Any:
    """Get ProcessMetrics from state (cached) or compute if missing."""
    metrics = state.get("process_metrics")
    if metrics is not None:
        return metrics
    logger.debug("process_metrics not in state, recomputing")
    return calculate_process_metrics(state["process"])


@tool
def analyze_dependency_impact(
    step_name: str,
    question: str,
    state: Annotated[dict[str, Any], InjectedState],
) -> str:
    """Analyze how a specific process step impacts downstream work.

    Use this when a step appears problematic and you need to understand
    the cascade effect on everything that depends on it.

    Args:
        step_name: The exact name of the step to investigate.
        question: The specific aspect of dependency impact to analyze.
    """
    logger.info("Tool: analyze_dependency_impact - step=%s", step_name)
    metrics = _get_metrics(state)

    step_metric = next((s for s in metrics.steps if s.step_name == step_name), None)
    if step_metric is None:
        return f"Step '{step_name}' not found in process data."

    lines = [
        f"Step '{step_name}':",
        f"  Time: {step_metric.time_hours:.1f}h ({step_metric.time_pct:.0f}% of total)",
        f"  Cost: ${step_metric.cost:.0f} ({step_metric.cost_pct:.0f}% of total)",
        f"  Error rate: {step_metric.error_rate_pct:.0f}%",
        f"  Resources: {step_metric.resources}",
        f"  Type: {step_metric.step_type.value}",
        f"  Downstream steps blocked by this: {step_metric.downstream_count}",
        f"  Upstream dependencies: {step_metric.upstream_count}",
        f"  Question being investigated: {question}",
    ]
    if step_metric.is_longest:
        lines.append("  Flag: longest step in process")
    if step_metric.is_highest_error:
        lines.append("  Flag: highest error rate in process")

    return "\n".join(lines)


@tool
def validate_root_cause(
    issue_title: str,
    hypothesis: str,
    state: Annotated[dict[str, Any], InjectedState],
) -> str:
    """Test whether a root cause hypothesis is consistent with the process data.

    Use this before committing to an explanation for a pattern or issue.

    Args:
        issue_title: The issue you are investigating (from your initial analysis).
        hypothesis: Your proposed explanation for why this issue exists.
    """
    logger.info("Tool: validate_root_cause - issue=%s", issue_title)
    metrics = _get_metrics(state)
    insight = state.get("analysis_insight")
    constraints = state.get("constraints")

    # Find the specific issue to get affected steps
    affected_steps: list[str] = []
    if insight:
        for issue in insight.issues:
            if issue.title.lower() == issue_title.lower():
                affected_steps = issue.affected_steps
                break

    lines = [
        f"Hypothesis: {hypothesis}",
        f"Issue: {issue_title}",
        "",
        "Affected step data:",
    ]

    if affected_steps:
        for step_name in affected_steps:
            sm = next((s for s in metrics.steps if s.step_name == step_name), None)
            if sm:
                lines.append(
                    f"  {step_name}: {sm.time_hours:.1f}h, "
                    f"{sm.error_rate_pct:.0f}% errors, "
                    f"type={sm.step_type.value}, downstream={sm.downstream_count}"
                )
    else:
        lines.append("  (no affected steps found — searching process-wide patterns)")
        lines.append(
            f"  Review steps: {metrics.patterns.review_step_count} "
            f"({metrics.patterns.review_pct_of_steps:.0f}%)"
        )
        lines.append(f"  Longest chain: {metrics.patterns.sequential_chain_length}")
        lines.append(f"  External touchpoints: {metrics.patterns.external_touchpoints}")

    if constraints:
        lines.append("")
        lines.append("Active constraints (may be relevant):")
        if constraints.cannot_hire:
            lines.append("  - Cannot hire new staff")
        if constraints.must_maintain_audit_trail:
            lines.append("  - Must maintain audit trail")
        if constraints.budget_limit:
            lines.append(f"  - Budget limit: ${constraints.budget_limit:,.0f}")

    return "\n".join(lines)


@tool
def check_constraint_feasibility(
    recommendation_concept: str,
    concern: str,
    state: Annotated[dict[str, Any], InjectedState],
) -> str:
    """Verify whether a recommendation would conflict with user constraints.

    Use this before finalizing any significant recommendation.

    Args:
        recommendation_concept: The recommendation you are considering.
        concern: Which constraint or requirement you are checking against.
    """
    logger.info(
        "Tool: check_constraint_feasibility - rec=%s", recommendation_concept[:50]
    )
    constraints = state.get("constraints")

    if constraints is None:
        return "No constraints defined. Recommendation appears feasible."

    active = []
    if constraints.budget_limit:
        active.append(f"Budget limit: ${constraints.budget_limit:,.0f}")
    if constraints.cannot_hire:
        active.append("Cannot hire new staff")
    if constraints.must_maintain_audit_trail:
        active.append("Must maintain audit trail")
    if constraints.max_implementation_weeks:
        active.append(
            f"Max implementation time: {constraints.max_implementation_weeks} weeks"
        )
    if constraints.max_error_rate_increase_pct:
        active.append(
            f"Max error rate increase: {constraints.max_error_rate_increase_pct}%"
        )
    if constraints.custom_constraints:
        active.extend(constraints.custom_constraints)

    if not active:
        return "No binding constraints. Recommendation appears feasible."

    return (
        f"Checking: '{recommendation_concept}'\n"
        f"Concern: {concern}\n"
        f"Active constraints:\n" + "\n".join(f"- {c}" for c in active)
    )


INVESTIGATION_TOOLS = [
    analyze_dependency_impact,
    validate_root_cause,
    check_constraint_feasibility,
]
