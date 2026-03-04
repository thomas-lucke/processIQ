"""Process visualization for ProcessIQ.

Two-layer design (keep strictly separate):
  Layer 1: build_graph_schema() — renderer-agnostic. Permanent contract.
           Produces a GraphSchema Pydantic model consumed by both the Plotly
           renderer now and the React Flow component in Task 2.5.
  Layer 2: build_process_figure() — Plotly renderer. Temporary.
           Will be deleted when the React Flow frontend replaces Streamlit.
"""

import logging
from collections import defaultdict, deque
from typing import Any, Literal

import plotly.graph_objects as go
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


def compute_layered_layout(
    steps: list[str],
    dependencies: dict[str, list[str]],  # step_name -> list of predecessor step names
) -> dict[str, tuple[float, float]]:
    """Assign (x, y) coordinates using topological level assignment (Sugiyama-style).

    Algorithm:
    1. Kahn's topological sort — assign each node to its longest-path level (x).
    2. Space nodes within each level evenly, centered on y=0.

    x = level index (left to right), y = position within level (top to bottom).
    Falls back to linear sequence if no dependency data (all steps at consecutive levels).

    Returns dict[step_name, (x, y)].
    """
    if not steps:
        return {}

    # Filter dependencies to only include steps that are in the step list
    valid_steps = set(steps)
    filtered_deps: dict[str, list[str]] = {}
    for step in steps:
        preds = [p for p in dependencies.get(step, []) if p in valid_steps]
        filtered_deps[step] = preds

    # Build adjacency structures for Kahn's algorithm
    in_degree: dict[str, int] = {s: 0 for s in steps}
    successors: dict[str, list[str]] = defaultdict(list)

    for step, preds in filtered_deps.items():
        in_degree[step] = len(preds)
        for pred in preds:
            successors[pred].append(step)

    # Level assignment: longest-path (critical path) level
    # Start with all nodes that have no predecessors
    level: dict[str, int] = {}
    queue: deque[str] = deque()

    for step in steps:
        if in_degree[step] == 0:
            level[step] = 0
            queue.append(step)

    # If no nodes with zero in-degree (cycle), fall back to linear
    if not queue:
        logger.warning(
            "visualization: cycle detected in dependencies, falling back to linear layout"
        )
        return {step: (float(i), 0.0) for i, step in enumerate(steps)}

    # Process in topological order
    processed_count = 0
    while queue:
        current = queue.popleft()
        processed_count += 1

        for succ in successors[current]:
            in_degree[succ] -= 1
            level[succ] = max(level.get(succ, 0), level[current] + 1)
            if in_degree[succ] == 0:
                queue.append(succ)

    # If not all nodes processed (cycle), assign remaining nodes sequentially
    if processed_count < len(steps):
        logger.warning(
            "visualization: %d steps not reachable in topological sort, assigning linearly",
            len(steps) - processed_count,
        )
        max_level = max(level.values()) if level else 0
        for i, step in enumerate(steps):
            if step not in level:
                level[step] = max_level + i + 1

    # Group steps by level
    levels: dict[int, list[str]] = defaultdict(list)
    for step in steps:
        levels[level[step]].append(step)

    # Preserve original step order within each level
    step_order = {step: i for i, step in enumerate(steps)}
    for lv in levels:
        levels[lv].sort(key=lambda s: step_order.get(s, 0))

    # Assign (x, y) coordinates
    # x = level, y = position within level centered around 0
    positions: dict[str, tuple[float, float]] = {}
    for lv, level_steps in levels.items():
        count = len(level_steps)
        for rank, step in enumerate(level_steps):
            y = rank - (count - 1) / 2.0
            positions[step] = (float(lv), y)

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


# ---------------------------------------------------------------------------
# Layer 2: Renderer (Streamlit/Plotly — temporary)
# NOTE: This layer will be deleted when the React Flow frontend replaces Streamlit.
# ---------------------------------------------------------------------------

# Color map aligned with Task 2.5 React Flow colors
_SEVERITY_COLORS: dict[str, str] = {
    "high": "#ef4444",  # red
    "medium": "#f97316",  # amber/orange
    "core_value": "#22c55e",  # green
    "recommendation_affected": "#3b82f6",  # blue
    "normal": "#6b7280",  # gray
}

_NODE_SPACING_X = 220  # pixels between columns
_NODE_SPACING_Y = 130  # pixels between rows within a column
_MIN_NODE_SIZE = 30  # minimum node marker size
_MAX_NODE_SIZE = 60  # maximum node marker size


def _nodes_to_plotly_traces(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    visible: bool,
) -> list[Any]:
    """Convert GraphNode list to Plotly scatter traces (nodes + edges).

    Returns a list of traces: one edge trace, one node trace.
    """
    # Build position lookup
    pos: dict[str, tuple[float, float]] = {
        n.step_name: (n.x * _NODE_SPACING_X, -n.y * _NODE_SPACING_Y) for n in nodes
    }

    # Edge trace — draw lines with arrows via annotations (Plotly limitation)
    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    for edge in edges:
        if edge.source in pos and edge.target in pos:
            sx, sy = pos[edge.source]
            tx, ty = pos[edge.target]
            edge_x += [sx, tx, None]
            edge_y += [sy, ty, None]

    edge_trace = go.Scatter(
        x=edge_x,
        y=edge_y,
        mode="lines",
        line={"width": 1.5, "color": "#94a3b8"},
        hoverinfo="none",
        visible=visible,
        showlegend=False,
    )

    # Node trace
    node_x = [pos[n.step_name][0] for n in nodes]
    node_y = [pos[n.step_name][1] for n in nodes]
    node_colors = [_SEVERITY_COLORS.get(n.severity, "#6b7280") for n in nodes]
    node_sizes = [
        min(_MAX_NODE_SIZE, max(_MIN_NODE_SIZE, int(n.time_pct * 0.8 + _MIN_NODE_SIZE)))
        for n in nodes
    ]
    node_labels = [n.step_name for n in nodes]
    node_hover = [n.hover_text for n in nodes]

    node_trace = go.Scatter(
        x=node_x,
        y=node_y,
        mode="markers+text",
        marker={
            "size": node_sizes,
            "color": node_colors,
            "line": {"width": 2, "color": "#ffffff"},
            "opacity": 0.9,
        },
        text=node_labels,
        textposition="bottom center",
        textfont={"size": 10, "color": "#1e293b"},
        hovertext=node_hover,
        hoverinfo="text",
        visible=visible,
        showlegend=False,
    )

    return [edge_trace, node_trace]


def build_process_figure(schema: GraphSchema, show_after: bool = False) -> go.Figure:
    """Convert GraphSchema to a Plotly figure.

    NOTE: This function is temporary. It will be deleted when the React Flow
    frontend replaces the Streamlit UI (Task 2.5).

    Includes a Before/After toggle button via Plotly updatemenus.
    The toggle changes which node set is visible — no Streamlit rerun needed.
    """
    has_rec = any(n.severity == "recommendation_affected" for n in schema.after_nodes)

    # Build all traces: [before_edges, before_nodes, after_edges, after_nodes]
    before_traces = _nodes_to_plotly_traces(
        schema.before_nodes, schema.edges, visible=not show_after
    )
    after_traces = _nodes_to_plotly_traces(
        schema.after_nodes, schema.edges, visible=show_after
    )
    all_traces = before_traces + after_traces

    fig = go.Figure(data=all_traces)

    # updatemenus buttons toggle visibility
    # [before_edges, before_nodes, after_edges, after_nodes] -> indices 0,1,2,3
    if has_rec:
        fig.update_layout(
            updatemenus=[
                {
                    "type": "buttons",
                    "direction": "left",
                    "x": 0.0,
                    "y": 1.12,
                    "xanchor": "left",
                    "showactive": True,
                    "buttons": [
                        {
                            "label": "Current state",
                            "method": "update",
                            "args": [{"visible": [True, True, False, False]}],
                        },
                        {
                            "label": "After top recommendation",
                            "method": "update",
                            "args": [{"visible": [False, False, True, True]}],
                        },
                    ],
                }
            ]
        )

    # Legend annotation
    legend_items = [
        ("High issue", _SEVERITY_COLORS["high"]),
        ("Medium issue", _SEVERITY_COLORS["medium"]),
        ("Core value", _SEVERITY_COLORS["core_value"]),
        ("Normal", _SEVERITY_COLORS["normal"]),
    ]
    if has_rec:
        legend_items.insert(
            2,
            ("Affected by recommendation", _SEVERITY_COLORS["recommendation_affected"]),
        )

    legend_html = "  ".join(
        f'<span style="color:{color}">&#9679;</span> {label}'
        for label, color in legend_items
    )

    fig.update_layout(
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
        paper_bgcolor="white",
        plot_bgcolor="#f8fafc",
        xaxis={
            "showgrid": False,
            "zeroline": False,
            "showticklabels": False,
        },
        yaxis={
            "showgrid": False,
            "zeroline": False,
            "showticklabels": False,
        },
        font={"family": "Inter, system-ui, sans-serif", "size": 12},
        annotations=[
            {
                "text": legend_html,
                "xref": "paper",
                "yref": "paper",
                "x": 1.0,
                "y": 1.12,
                "xanchor": "right",
                "showarrow": False,
                "font": {"size": 11},
            }
        ],
        height=400,
    )

    return fig
