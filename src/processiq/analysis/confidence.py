"""Confidence scoring for ProcessIQ.

Pure algorithmic logic - no LLM calls. Calculates confidence scores
based on data completeness and quality.
"""

import logging
from dataclasses import dataclass, field

from processiq.config import settings
from processiq.models import BusinessProfile, Constraints, ProcessData

logger = logging.getLogger(__name__)

# Confidence scoring weights (must sum to 1.0)
# Process data is most important for bottleneck detection
WEIGHT_PROCESS = 0.6
WEIGHT_CONSTRAINTS = 0.25
WEIGHT_PROFILE = 0.15

assert (  # nosec B101 — module-level invariant, not a runtime security check
    abs(WEIGHT_PROCESS + WEIGHT_CONSTRAINTS + WEIGHT_PROFILE - 1.0) < 1e-9
), (
    f"Confidence weights must sum to 1.0, got {WEIGHT_PROCESS + WEIGHT_CONSTRAINTS + WEIGHT_PROFILE}"
)


@dataclass
class ConfidenceResult:
    """Result of confidence scoring."""

    score: float  # 0.0 to 1.0
    data_gaps: list[str] = field(default_factory=list)
    suggestions_for_improvement: list[str] = field(default_factory=list)
    breakdown: dict[str, float] = field(default_factory=dict)  # Component scores

    @property
    def is_sufficient(self) -> bool:
        """Check if confidence meets threshold (configurable via CONFIDENCE_THRESHOLD)."""
        return self.score >= settings.confidence_threshold

    @property
    def level(self) -> str:
        """Human-readable confidence level."""
        if self.score >= 0.8:
            return "high"
        if self.score >= 0.6:
            return "moderate"
        if self.score >= 0.4:
            return "low"
        return "very low"


def calculate_confidence(
    process: ProcessData,
    constraints: Constraints | None = None,
    profile: BusinessProfile | None = None,
) -> ConfidenceResult:
    """Calculate overall confidence score for analysis.

    Args:
        process: The process data to evaluate.
        constraints: Optional business constraints.
        profile: Optional business profile.

    Returns:
        ConfidenceResult with score, gaps, and improvement suggestions.
    """
    logger.info("Calculating confidence for process: %s", process.name)

    data_gaps: list[str] = []
    suggestions: list[str] = []

    # Score components (weighted)
    process_score = _score_process_data(process, data_gaps, suggestions)
    constraints_score = _score_constraints(constraints, data_gaps, suggestions)
    profile_score = _score_profile(profile, data_gaps, suggestions)

    # Weighted average
    total_score = (
        process_score * WEIGHT_PROCESS
        + constraints_score * WEIGHT_CONSTRAINTS
        + profile_score * WEIGHT_PROFILE
    )

    result = ConfidenceResult(
        score=total_score,
        data_gaps=data_gaps,
        suggestions_for_improvement=suggestions,
        breakdown={
            "process_completeness": process_score,
            "constraints_completeness": constraints_score,
            "profile_completeness": profile_score,
        },
    )

    logger.info(
        "Confidence calculated: %.1f%% (%s), %d gaps identified",
        total_score * 100,
        result.level,
        len(data_gaps),
    )

    return result


def _score_process_data(
    process: ProcessData,
    data_gaps: list[str],
    suggestions: list[str],
) -> float:
    """Score the completeness and quality of process data."""
    if not process.steps:
        data_gaps.append("No process steps defined")
        suggestions.append("Add at least one process step")
        return 0.0

    scores: list[float] = []

    for step in process.steps:
        step_score = 1.0
        step_gaps: list[str] = []

        # Check for default/zero values that suggest missing data
        if step.error_rate_pct == 0.0:
            step_score -= 0.15
            step_gaps.append(f"error rate for '{step.step_name}'")

        if step.cost_per_instance == 0.0:
            step_score -= 0.2
            step_gaps.append(f"cost for '{step.step_name}'")

        if step.average_time_hours == 0.0:
            step_score -= 0.3
            step_gaps.append(f"time for '{step.step_name}'")

        if step.resources_needed == 1 and len(process.steps) > 3:
            # Suspicious if all steps have exactly 1 resource
            step_score -= 0.05

        scores.append(max(step_score, 0.0))

        if step_gaps:
            data_gaps.extend(step_gaps)

    # Check for dependencies
    steps_with_deps = sum(1 for s in process.steps if s.depends_on)
    if len(process.steps) > 1 and steps_with_deps == 0:
        data_gaps.append("No dependencies defined between steps")
        suggestions.append("Define step dependencies to enable cascade analysis")
        scores = [s * 0.9 for s in scores]  # Reduce all scores by 10%

    # Check for process description
    if not process.description:
        suggestions.append("Add a process description for better context")

    avg_score = sum(scores) / len(scores) if scores else 0.0

    # Bonus for having many steps (more data = more confidence)
    if len(process.steps) >= 5:
        avg_score = min(avg_score + 0.05, 1.0)

    return avg_score


def _score_constraints(
    constraints: Constraints | None,
    data_gaps: list[str],
    suggestions: list[str],
) -> float:
    """Score the completeness of constraint data."""
    if constraints is None:
        data_gaps.append("No constraints provided")
        suggestions.append("Define business constraints (budget, hiring, timeline)")
        return 0.3  # Partial score - analysis still possible without constraints

    score = 0.5  # Base score for having constraints

    # Check for specific constraint values
    if constraints.budget_limit is not None:
        score += 0.15
    else:
        suggestions.append("Consider adding a budget limit for better filtering")

    if constraints.timeline_weeks is not None:
        score += 0.15

    if constraints.custom_constraints:
        score += 0.1

    # Having any boolean constraints set is good
    if constraints.no_new_hires or constraints.must_maintain_audit_trail:
        score += 0.1

    return min(score, 1.0)


def _score_profile(
    profile: BusinessProfile | None,
    data_gaps: list[str],
    suggestions: list[str],
) -> float:
    """Score the completeness of business profile data."""
    if profile is None:
        data_gaps.append("No business profile provided")
        suggestions.append(
            "Add business context (industry, company size, regulatory environment)"
        )
        return 0.2  # Minimal score - CQ is reduced without profile

    score = 0.4  # Base score for having a profile

    # Industry and size are the most important
    score += 0.2  # Already have these (required fields)

    # Optional enrichments
    if profile.typical_constraints:
        score += 0.1

    if profile.previous_improvements:
        score += 0.1
        # This is valuable for CQ - knowing what was tried before

    if profile.rejected_approaches:
        score += 0.15
        # Very valuable - avoid suggesting rejected approaches

    if profile.preferred_frameworks:
        score += 0.05

    return min(score, 1.0)


def identify_critical_gaps(result: ConfidenceResult) -> list[str]:
    """Identify the most critical data gaps that would improve confidence.

    Returns gaps sorted by impact (most impactful first).
    """
    critical_keywords = [
        "time",
        "cost",
        "error rate",
        "No process steps",
        "No constraints",
    ]

    critical = []
    other = []

    for gap in result.data_gaps:
        if any(kw in gap.lower() for kw in [k.lower() for k in critical_keywords]):
            critical.append(gap)
        else:
            other.append(gap)

    return critical + other
