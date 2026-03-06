"""Process visualization for ProcessIQ.

Builds the renderer-agnostic GraphSchema consumed by the React Flow frontend
via the /graph-schema API endpoint.
"""

import logging
from collections import defaultdict, deque
from typing import Literal

from pydantic import BaseModel

from processiq.models.insight import AnalysisInsight
from processiq.models.process import ProcessData

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Layer 1: Data (renderer-agnostic)
# ---------------------------------------------------------------------------

Severity = Literal["high", "medium", "core_value", "recommendation_affected", "normal"]


class GraphNode(BaseModel):
    step_name: str
    x: float
    y: float
    time_pct: float  # percentage of total process time (0-100)
    severity: Severity
    hover_text: str  # pre-formatted: "Step Name\n2.1h (34%)\nErrors: 8%\nCost: $157"


class GraphEdge(BaseModel):
    source: str  # step_name
    target: str  # step_name


class GraphSchema(BaseModel):
    before_nodes: list[GraphNode]
    after_nodes: list[GraphNode]  # same positions, severity changes for affected steps
    edges: list[GraphEdge]


_GRID_COLS = 3  # columns in the grid layout for linear processes


def compute_layered_layout(
    steps: list[str],
    dependencies: dict[str, list[str]],  # step_name -> list of predecessor step names
) -> dict[str, tuple[float, float]]:
    """Assign (x, y) coordinates.

    Layout strategy:
    - Linear processes (every topological level has exactly 1 node): grid layout.
      Steps fill left→right across _GRID_COLS columns, rows flow top→bottom.
      x = column index, y = row index (renderer negates y so row 0 is at top).
    - Branching/parallel processes: Sugiyama column layout (x = level, y = rank).

    The grid layout keeps a 13-step linear process to 5 rows x 3 cols instead
    of 13 columns — fits in a single view without scrolling.
    """
    if not steps:
        return {}

    valid_steps = set(steps)
    filtered_deps: dict[str, list[str]] = {}
    for step in steps:
        preds = [p for p in dependencies.get(step, []) if p in valid_steps]
        filtered_deps[step] = preds

    in_degree: dict[str, int] = {s: 0 for s in steps}
    successors: dict[str, list[str]] = defaultdict(list)

    for step, preds in filtered_deps.items():
        in_degree[step] = len(preds)
        for pred in preds:
            successors[pred].append(step)

    level: dict[str, int] = {}
    queue: deque[str] = deque()

    for step in steps:
        if in_degree[step] == 0:
            level[step] = 0
            queue.append(step)

    if not queue:
        logger.warning("visualization: cycle detected, falling back to grid layout")
        return _grid_positions(steps)

    processed_count = 0
    while queue:
        current = queue.popleft()
        processed_count += 1
        for succ in successors[current]:
            in_degree[succ] -= 1
            level[succ] = max(level.get(succ, 0), level[current] + 1)
            if in_degree[succ] == 0:
                queue.append(succ)

    if processed_count < len(steps):
        logger.warning(
            "visualization: %d steps unreachable in topological sort, using grid layout",
            len(steps) - processed_count,
        )
        return _grid_positions(steps)

    levels: dict[int, list[str]] = defaultdict(list)
    for step in steps:
        levels[level[step]].append(step)

    step_order = {step: i for i, step in enumerate(steps)}
    for lv in levels:
        levels[lv].sort(key=lambda s: step_order.get(s, 0))

    max_level_width = max(len(v) for v in levels.values())
    if max_level_width == 1:
        # Strictly linear — use grid layout
        ordered_steps = [levels[lv][0] for lv in sorted(levels)]
        return _grid_positions(ordered_steps)

    # Branching/parallel — standard Sugiyama column layout (x=level, y=rank)
    positions: dict[str, tuple[float, float]] = {}
    for lv, level_steps in levels.items():
        count = len(level_steps)
        for rank, step in enumerate(level_steps):
            y = rank - (count - 1) / 2.0
            positions[step] = (float(lv), y)

    return positions


def _grid_positions(steps: list[str]) -> dict[str, tuple[float, float]]:
    """Arrange steps in a top→bottom, left→right grid of _GRID_COLS columns.

    x = column index (0 to _GRID_COLS-1), y = row index (0, 1, 2, ...).
    The renderer multiplies by spacing constants and negates y so row 0 renders
    at the top of the figure.

    For 13 steps with _GRID_COLS=3:
      row 0: steps 0,1,2   row 1: steps 3,4,5   row 2: steps 6,7,8
      row 3: steps 9,10,11  row 4: step 12
    """
    positions: dict[str, tuple[float, float]] = {}
    for i, step in enumerate(steps):
        row = i // _GRID_COLS
        col = i % _GRID_COLS
        positions[step] = (float(col), float(row))
    return positions


def _matches_step(step_name: str, candidate: str) -> bool:
    """Case-insensitive substring match between a step name and an LLM-provided name.

    The LLM often abbreviates step names (e.g. "Phone Request" vs "Phone Request Intake"),
    so exact matching produces all-gray nodes. Substring matching in both directions
    handles the common cases without being too loose.
    """
    a, b = step_name.lower(), candidate.lower()
    return a == b or a in b or b in a


def _assign_severity(
    step_name: str,
    insight: AnalysisInsight | None,
    affected_steps_for_recs: set[str],
    show_after: bool,
) -> Severity:
    """Apply color precedence rules (highest wins):

    1. High-severity issue   → "high"
    2. Medium-severity issue → "medium"
    3. Recommendation affected (only when show_after=True) → "recommendation_affected"
    4. Core value / NotAProblem → "core_value"
    5. Normal (default) → "normal"
    """
    if insight is None:
        return "normal"

    # Check issues (precedence 1 and 2)
    for issue in insight.issues:
        if any(_matches_step(step_name, s) for s in issue.affected_steps):
            if issue.severity == "high":
                return "high"
            if issue.severity == "medium":
                return "medium"

    # Check recommendation-affected (precedence 3)
    if show_after and any(_matches_step(step_name, s) for s in affected_steps_for_recs):
        return "recommendation_affected"

    # Check not-a-problem / core value (precedence 4)
    for nap in insight.not_problems:
        if _matches_step(step_name, nap.step_name):
            return "core_value"

    return "normal"


def _format_hover_text(
    step_name: str,
    time_hours: float,
    time_pct: float,
    error_rate: float,
    cost: float,
    resources: int,
) -> str:
    """Format the hover tooltip text for a node."""
    lines = [
        step_name,
        f"{time_hours:.1f}h ({time_pct:.0f}% of total)",
    ]
    if error_rate > 0:
        lines.append(f"Problem freq: {error_rate:.0f}%")
    if cost > 0:
        lines.append(f"Cost: ${cost:,.0f}")
    if resources > 0:
        lines.append(f"People: {resources}")
    return "<br>".join(lines)


def build_graph_schema(
    process_data: ProcessData,
    analysis_insight: AnalysisInsight | None = None,
) -> GraphSchema:
    """Build the renderer-agnostic graph data structure.

    Calls compute_layered_layout(), assigns severity per node,
    builds before_nodes and after_nodes lists (same positions, different severity).
    No Plotly import or figure construction here.
    """
    steps = process_data.steps
    step_names = [s.step_name for s in steps]
    total_time = process_data.total_time_hours or 1.0  # avoid division by zero

    # Build dependency map: step_name -> list of predecessor step_names
    dependencies: dict[str, list[str]] = {
        s.step_name: list(s.depends_on) for s in steps
    }

    positions = compute_layered_layout(step_names, dependencies)

    # Collect steps affected by the top recommendation (for "after" view)
    affected_by_top_rec: set[str] = set()
    if analysis_insight and analysis_insight.recommendations:
        top_rec = analysis_insight.recommendations[0]
        affected_by_top_rec = set(top_rec.affected_steps)

    # Build nodes for both before and after states
    before_nodes: list[GraphNode] = []
    after_nodes: list[GraphNode] = []

    for step in steps:
        x, y = positions.get(step.step_name, (0.0, 0.0))
        time_pct = (step.average_time_hours / total_time) * 100

        hover = _format_hover_text(
            step_name=step.step_name,
            time_hours=step.average_time_hours,
            time_pct=time_pct,
            error_rate=step.error_rate_pct,
            cost=step.cost_per_instance,
            resources=step.resources_needed,
        )

        before_severity = _assign_severity(
            step_name=step.step_name,
            insight=analysis_insight,
            affected_steps_for_recs=affected_by_top_rec,
            show_after=False,
        )
        after_severity = _assign_severity(
            step_name=step.step_name,
            insight=analysis_insight,
            affected_steps_for_recs=affected_by_top_rec,
            show_after=True,
        )

        before_nodes.append(
            GraphNode(
                step_name=step.step_name,
                x=x,
                y=y,
                time_pct=time_pct,
                severity=before_severity,
                hover_text=hover,
            )
        )
        after_nodes.append(
            GraphNode(
                step_name=step.step_name,
                x=x,
                y=y,
                time_pct=time_pct,
                severity=after_severity,
                hover_text=hover,
            )
        )

    # Build edges from dependency data
    edges: list[GraphEdge] = []
    for step in steps:
        for pred in step.depends_on:
            if pred in {s.step_name for s in steps}:
                edges.append(GraphEdge(source=pred, target=step.step_name))

    logger.info(
        "visualization: built GraphSchema — %d nodes, %d edges",
        len(before_nodes),
        len(edges),
    )

    return GraphSchema(
        before_nodes=before_nodes,
        after_nodes=after_nodes,
        edges=edges,
    )
