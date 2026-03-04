"""Process metrics calculation for LLM-based analysis.

This module calculates FACTS that the LLM can interpret, not judgments.
The LLM decides what's a problem; these functions provide the data.

Key principle: Algorithms calculate percentages, counts, and relationships.
LLM interprets whether those numbers indicate waste or value.
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum

from processiq.models import ProcessData

logger = logging.getLogger(__name__)

# Pre-compiled regex patterns for step type inference.
# Compiled once at import time instead of per-call.
_REVIEW_PATTERNS = [
    re.compile(p)
    for p in [
        r"\breview",
        r"\bapproval\b",
        r"\bapprove",
        r"\bcheck\b",
        r"\bvalidat",
        r"\bverif",
        r"\binspect",
        r"\bqc\b",
        r"\bqa\b",
    ]
]
_EXTERNAL_PATTERNS = [
    re.compile(p)
    for p in [
        r"\bclient\b",
        r"\bcustomer\b",
        r"\bvendor\b",
        r"\bexternal\b",
        r"\bfeedback\b",
        r"\bhappy\b",
    ]
]
_HANDOFF_PATTERNS = [
    re.compile(p)
    for p in [
        r"\bsend\b",
        r"\bsubmit\b",
        r"\bshare\b",
        r"\btransfer\b",
        r"\bforward\b",
        r"\bdeliver\b",
        r"\bhandoff\b",
        r"\bhand off\b",
    ]
]
_CREATIVE_PATTERNS = [
    re.compile(p)
    for p in [
        r"\bdesign\b",
        r"\bcreate\b",
        r"\bdevelop\b",
        r"\bwrite\b",
        r"\bbuild\b",
        r"\bsolution\b",
        r"\bwork on\b",
        r"\bimplement\b",
    ]
]
_ADMIN_PATTERNS = [
    re.compile(p)
    for p in [
        r"\binvoice\b",
        r"\bdocument\b",
        r"\brecord\b",
        r"\bfile\b",
        r"\blog\b",
        r"\breport\b",
    ]
]
_PROCESSING_PATTERNS = [
    re.compile(p)
    for p in [
        r"\bprocess\b",
        r"\bprepare\b",
        r"\banalyze\b",
        r"\bcollect\b",
        r"\bgather\b",
        r"\btask\b",
    ]
]


class StepType(str, Enum):
    """Inferred step type based on name/characteristics.

    These are hints for the LLM, not definitive classifications.
    """

    REVIEW = "review"  # Approval, review, check, validation
    HANDOFF = "handoff"  # Transfer, send, share, submit
    PROCESSING = "processing"  # Create, build, prepare, process
    EXTERNAL = "external"  # Client, customer, vendor, external party
    CREATIVE = "creative"  # Design, write, develop, create solution
    ADMINISTRATIVE = "administrative"  # Invoice, document, record
    UNKNOWN = "unknown"


@dataclass
class StepMetrics:
    """Calculated metrics for a single step.

    All fields are FACTS derived from data, not judgments.
    """

    step_name: str
    step_index: int

    # Time metrics
    time_hours: float
    time_pct: float  # % of total process time

    # Cost metrics
    cost: float
    cost_pct: float  # % of total process cost

    # Other metrics
    error_rate_pct: float
    resources: int

    # Dependency metrics
    downstream_count: int  # How many steps depend on this (directly or transitively)
    upstream_count: int  # How many steps this depends on
    is_parallel_candidate: bool  # True if has no downstream dependencies

    # Inferred type (hint for LLM)
    step_type: StepType

    # Flags for LLM attention
    is_longest: bool  # Is this the longest step?
    is_most_expensive: bool  # Is this the most expensive step?
    is_highest_error: bool  # Does this have highest error rate?


@dataclass
class PatternMetrics:
    """Aggregate patterns detected in the process.

    These are counts and ratios that might indicate issues.
    The LLM decides if they're actually problems.
    """

    review_step_count: int
    handoff_count: int
    external_touchpoints: int  # Steps involving clients/vendors
    creative_step_count: int

    # Ratios
    review_pct_of_steps: float  # % of steps that are reviews
    time_in_reviews_pct: float  # % of time spent in review steps
    time_in_creative_pct: float  # % of time in creative work

    # Dependency patterns
    sequential_chain_length: int  # Longest chain of sequential dependencies
    parallel_opportunities: int  # Steps that could potentially run in parallel


@dataclass
class ProcessMetrics:
    """Complete metrics for a process, ready for LLM analysis.

    Separates FACTS (what the data shows) from JUDGMENTS (what it means).
    """

    process_name: str

    # Aggregate metrics
    total_time_hours: float
    total_cost: float
    step_count: int

    # Per-step metrics
    steps: list[StepMetrics]

    # Pattern metrics
    patterns: PatternMetrics

    # Data quality indicators
    has_all_times: bool
    has_all_costs: bool
    has_error_rates: bool
    has_dependencies: bool


def calculate_process_metrics(process: ProcessData) -> ProcessMetrics:
    """Calculate all metrics for a process.

    This is the main entry point for the new analysis pipeline.

    Args:
        process: The process data to analyze.

    Returns:
        ProcessMetrics with calculated facts for LLM analysis.
    """
    logger.info("Calculating metrics for process: %s", process.name)

    if not process.steps:
        logger.warning("Empty process, returning minimal metrics")
        return _create_empty_metrics(process.name)

    # Calculate totals
    total_time = process.total_time_hours
    total_cost = process.total_cost

    # Build dependency maps
    downstream_map = _build_downstream_map(process)
    upstream_map = _build_upstream_map(process)

    # Find maxes for comparison flags
    max_time = max(s.average_time_hours for s in process.steps)
    max_cost = max(s.cost_per_instance for s in process.steps)
    max_error = (
        max(s.error_rate_pct for s in process.steps)
        if any(s.error_rate_pct > 0 for s in process.steps)
        else 0
    )

    # Calculate per-step metrics
    step_metrics: list[StepMetrics] = []
    for idx, step in enumerate(process.steps):
        downstream_count = len(downstream_map.get(step.step_name, []))
        upstream_count = len(upstream_map.get(step.step_name, []))

        metrics = StepMetrics(
            step_name=step.step_name,
            step_index=idx,
            time_hours=step.average_time_hours,
            time_pct=(step.average_time_hours / total_time * 100)
            if total_time > 0
            else 0,
            cost=step.cost_per_instance,
            cost_pct=(step.cost_per_instance / total_cost * 100)
            if total_cost > 0
            else 0,
            error_rate_pct=step.error_rate_pct,
            resources=step.resources_needed,
            downstream_count=downstream_count,
            upstream_count=upstream_count,
            is_parallel_candidate=downstream_count == 0,
            step_type=_infer_step_type(step.step_name),
            is_longest=step.average_time_hours == max_time and max_time > 0,
            is_most_expensive=step.cost_per_instance == max_cost and max_cost > 0,
            is_highest_error=step.error_rate_pct == max_error and max_error > 0,
        )
        step_metrics.append(metrics)

    # Calculate pattern metrics
    patterns = _calculate_pattern_metrics(step_metrics, process)

    # Data quality checks
    has_all_times = all(s.average_time_hours > 0 for s in process.steps)
    has_all_costs = all(s.cost_per_instance > 0 for s in process.steps)
    has_error_rates = any(s.error_rate_pct > 0 for s in process.steps)
    has_dependencies = any(len(s.depends_on) > 0 for s in process.steps)

    logger.info(
        "Metrics calculated: %d steps, %.1fh total, $%.2f total, %d reviews, %d external",
        len(step_metrics),
        total_time,
        total_cost,
        patterns.review_step_count,
        patterns.external_touchpoints,
    )

    return ProcessMetrics(
        process_name=process.name,
        total_time_hours=total_time,
        total_cost=total_cost,
        step_count=len(process.steps),
        steps=step_metrics,
        patterns=patterns,
        has_all_times=has_all_times,
        has_all_costs=has_all_costs,
        has_error_rates=has_error_rates,
        has_dependencies=has_dependencies,
    )


def _build_downstream_map(process: ProcessData) -> dict[str, list[str]]:
    """Build map of step -> steps that depend on it (transitively)."""
    # Direct dependencies: step -> list of steps that directly depend on it
    direct: dict[str, list[str]] = {step.step_name: [] for step in process.steps}

    for step in process.steps:
        for dep in step.depends_on:
            if dep in direct:
                direct[dep].append(step.step_name)

    # Expand to transitive closure
    result: dict[str, list[str]] = {}
    for step_name in direct:
        result[step_name] = _get_transitive(step_name, direct, set())

    return result


def _build_upstream_map(process: ProcessData) -> dict[str, list[str]]:
    """Build map of step -> steps it depends on (transitively)."""
    # Direct: step -> what it depends on directly
    direct: dict[str, list[str]] = {}
    for step in process.steps:
        direct[step.step_name] = list(step.depends_on)

    # Expand to transitive closure
    result: dict[str, list[str]] = {}
    for step_name in direct:
        visited: set[str] = set()
        result[step_name] = _get_transitive_upstream(step_name, direct, visited)

    return result


def _get_transitive(
    step_name: str,
    direct: dict[str, list[str]],
    visited: set[str],
) -> list[str]:
    """Get all downstream steps recursively.

    Uses shared visited set (not copied) to correctly handle
    reconvergent paths and prevent exponential blowup.
    """
    if step_name in visited:
        return []
    visited.add(step_name)

    result: list[str] = []
    for child in direct.get(step_name, []):
        if child not in result:
            result.append(child)
        for grandchild in _get_transitive(child, direct, visited):
            if grandchild not in result:
                result.append(grandchild)

    return result


def _get_transitive_upstream(
    step_name: str,
    direct: dict[str, list[str]],
    visited: set[str],
) -> list[str]:
    """Get all upstream steps recursively.

    Uses shared visited set (not copied) to correctly handle
    reconvergent paths and prevent exponential blowup.
    """
    if step_name in visited:
        return []
    visited.add(step_name)

    result: list[str] = []
    for parent in direct.get(step_name, []):
        if parent not in result:
            result.append(parent)
        for grandparent in _get_transitive_upstream(parent, direct, visited):
            if grandparent not in result:
                result.append(grandparent)

    return result


def _infer_step_type(step_name: str) -> StepType:
    """Infer step type from name using pre-compiled regex patterns.

    This is a HINT for the LLM, not a definitive classification.
    The LLM should use this as context but can override.
    """
    name_lower = step_name.lower()

    # Check in priority order
    for pattern in _REVIEW_PATTERNS:
        if pattern.search(name_lower):
            return StepType.REVIEW

    for pattern in _EXTERNAL_PATTERNS:
        if pattern.search(name_lower):
            return StepType.EXTERNAL

    for pattern in _HANDOFF_PATTERNS:
        if pattern.search(name_lower):
            return StepType.HANDOFF

    for pattern in _CREATIVE_PATTERNS:
        if pattern.search(name_lower):
            return StepType.CREATIVE

    for pattern in _ADMIN_PATTERNS:
        if pattern.search(name_lower):
            return StepType.ADMINISTRATIVE

    for pattern in _PROCESSING_PATTERNS:
        if pattern.search(name_lower):
            return StepType.PROCESSING

    return StepType.UNKNOWN


def _calculate_pattern_metrics(
    step_metrics: list[StepMetrics],
    process: ProcessData,
) -> PatternMetrics:
    """Calculate aggregate pattern metrics."""
    # Count step types
    review_count = sum(1 for s in step_metrics if s.step_type == StepType.REVIEW)
    handoff_count = sum(1 for s in step_metrics if s.step_type == StepType.HANDOFF)
    external_count = sum(1 for s in step_metrics if s.step_type == StepType.EXTERNAL)
    creative_count = sum(1 for s in step_metrics if s.step_type == StepType.CREATIVE)

    # Time percentages by type
    total_time = sum(s.time_hours for s in step_metrics)
    review_time = sum(
        s.time_hours for s in step_metrics if s.step_type == StepType.REVIEW
    )
    creative_time = sum(
        s.time_hours for s in step_metrics if s.step_type == StepType.CREATIVE
    )

    # Calculate longest sequential chain
    chain_length = _calculate_longest_chain(process)

    # Count parallel opportunities (steps with no downstream)
    parallel_ops = sum(1 for s in step_metrics if s.is_parallel_candidate)

    return PatternMetrics(
        review_step_count=review_count,
        handoff_count=handoff_count,
        external_touchpoints=external_count,
        creative_step_count=creative_count,
        review_pct_of_steps=(review_count / len(step_metrics) * 100)
        if step_metrics
        else 0,
        time_in_reviews_pct=(review_time / total_time * 100) if total_time > 0 else 0,
        time_in_creative_pct=(creative_time / total_time * 100)
        if total_time > 0
        else 0,
        sequential_chain_length=chain_length,
        parallel_opportunities=parallel_ops,
    )


def _calculate_longest_chain(process: ProcessData) -> int:
    """Calculate the longest chain of sequential dependencies."""
    if not process.steps:
        return 0

    # Build adjacency list
    adj: dict[str, list[str]] = {step.step_name: [] for step in process.steps}
    for step in process.steps:
        for dep in step.depends_on:
            if dep in adj:
                adj[dep].append(step.step_name)

    # Find longest path using DFS with cycle detection
    memo: dict[str, int] = {}
    visiting: set[str] = set()

    def dfs(node: str) -> int:
        if node in memo:
            return memo[node]
        if node in visiting:
            # Back-edge: cycle detected, treat as length 0 to break the loop
            return 0

        visiting.add(node)
        max_child = 0
        for child in adj.get(node, []):
            max_child = max(max_child, dfs(child))
        visiting.discard(node)

        memo[node] = 1 + max_child
        return memo[node]

    return max(dfs(step.step_name) for step in process.steps) if process.steps else 0


def _create_empty_metrics(name: str) -> ProcessMetrics:
    """Create empty metrics for an empty process."""
    return ProcessMetrics(
        process_name=name,
        total_time_hours=0,
        total_cost=0,
        step_count=0,
        steps=[],
        patterns=PatternMetrics(
            review_step_count=0,
            handoff_count=0,
            external_touchpoints=0,
            creative_step_count=0,
            review_pct_of_steps=0,
            time_in_reviews_pct=0,
            time_in_creative_pct=0,
            sequential_chain_length=0,
            parallel_opportunities=0,
        ),
        has_all_times=False,
        has_all_costs=False,
        has_error_rates=False,
        has_dependencies=False,
    )


def format_metrics_for_llm(metrics: ProcessMetrics) -> str:
    """Format metrics as a structured text for LLM consumption.

    This creates a clear, parseable format that the LLM can reason about.
    """
    lines = [
        f"# Process: {metrics.process_name}",
        "",
        "## Summary",
        f"- Total steps: {metrics.step_count}",
        f"- Total time: {metrics.total_time_hours:.1f} hours",
        f"- Total cost: ${metrics.total_cost:.2f}",
        "",
        "## Step Details",
        "",
        "| # | Step | Time | Time% | Cost | Cost% | Errors | Resources | Type | Downstream |",
        "|---|------|------|-------|------|-------|--------|-----------|------|------------|",
    ]

    for s in metrics.steps:
        flags = []
        if s.is_longest:
            flags.append("longest")
        if s.is_most_expensive:
            flags.append("costly")
        if s.is_highest_error:
            flags.append("error-prone")
        flag_str = f" ({', '.join(flags)})" if flags else ""

        lines.append(
            f"| {s.step_index + 1} | {s.step_name}{flag_str} | "
            f"{s.time_hours:.1f}h | {s.time_pct:.0f}% | "
            f"${s.cost:.0f} | {s.cost_pct:.0f}% | "
            f"{s.error_rate_pct:.0f}% | {s.resources} | "
            f"{s.step_type.value} | {s.downstream_count} |"
        )

    lines.extend(
        [
            "",
            "## Patterns Detected",
            f"- Review steps: {metrics.patterns.review_step_count} ({metrics.patterns.review_pct_of_steps:.0f}% of steps)",
            f"- Time in reviews: {metrics.patterns.time_in_reviews_pct:.0f}%",
            f"- External touchpoints: {metrics.patterns.external_touchpoints}",
            f"- Creative work steps: {metrics.patterns.creative_step_count} ({metrics.patterns.time_in_creative_pct:.0f}% of time)",
            f"- Longest sequential chain: {metrics.patterns.sequential_chain_length} steps",
            f"- Parallel opportunities: {metrics.patterns.parallel_opportunities} steps",
            "",
            "## Data Quality",
            f"- Has all timing data: {'Yes' if metrics.has_all_times else 'No'}",
            f"- Has all cost data: {'Yes' if metrics.has_all_costs else 'No'}",
            f"- Has error rates: {'Yes' if metrics.has_error_rates else 'No'}",
            f"- Has dependency info: {'Yes' if metrics.has_dependencies else 'No'}",
        ]
    )

    return "\n".join(lines)
