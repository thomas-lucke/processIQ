"""Tests for processiq.analysis.visualization.

Covers compute_layered_layout() and build_graph_schema() with
deterministic sample data — no LLM calls.
"""

import pytest

from processiq.analysis.visualization import (
    GraphSchema,
    build_graph_schema,
    compute_layered_layout,
)
from processiq.models import (
    AnalysisInsight,
    Issue,
    NotAProblem,
    ProcessData,
    ProcessStep,
)

# ---------------------------------------------------------------------------
# compute_layered_layout
# ---------------------------------------------------------------------------


class TestComputeLayeredLayout:
    def test_empty_steps_returns_empty_dict(self):
        assert compute_layered_layout([], {}) == {}

    def test_single_step_returns_origin(self):
        positions = compute_layered_layout(["A"], {})
        assert "A" in positions
        assert positions["A"] == (0.0, 0.0)

    def test_linear_chain_is_horizontal(self):
        steps = ["A", "B", "C"]
        deps = {"A": [], "B": ["A"], "C": ["B"]}
        positions = compute_layered_layout(steps, deps)

        # All steps on y=0 (horizontal layout)
        for name in steps:
            assert positions[name][1] == 0.0

        # Steps in ascending x order
        assert positions["A"][0] < positions["B"][0] < positions["C"][0]

    def test_parallel_steps_get_different_y(self):
        # A → B, A → C (B and C are parallel)
        steps = ["A", "B", "C"]
        deps = {"A": [], "B": ["A"], "C": ["A"]}
        positions = compute_layered_layout(steps, deps)

        # B and C should be at the same x level but different y
        assert positions["B"][0] == positions["C"][0]
        assert positions["B"][1] != positions["C"][1]

    def test_no_dependencies_all_at_level_zero(self):
        steps = ["A", "B", "C"]
        positions = compute_layered_layout(steps, {})
        # No deps → all roots → all at level 0 → branching layout
        # All share the same x coordinate
        x_values = {positions[s][0] for s in steps}
        assert x_values == {0.0}

    def test_invalid_dependencies_ignored(self):
        # "B" lists "Z" as a dep but "Z" is not in the steps list
        steps = ["A", "B"]
        deps = {"A": [], "B": ["Z"]}
        positions = compute_layered_layout(steps, deps)
        assert set(positions.keys()) == {"A", "B"}

    def test_all_steps_get_a_position(self):
        steps = ["A", "B", "C", "D"]
        deps = {"A": [], "B": ["A"], "C": ["A"], "D": ["B", "C"]}
        positions = compute_layered_layout(steps, deps)
        assert set(positions.keys()) == set(steps)


# ---------------------------------------------------------------------------
# build_graph_schema — basic structure
# ---------------------------------------------------------------------------


class TestBuildGraphSchemaStructure:
    def test_returns_graph_schema(self, simple_process):
        result = build_graph_schema(simple_process)
        assert isinstance(result, GraphSchema)

    def test_node_count_matches_step_count(self, simple_process):
        result = build_graph_schema(simple_process)
        assert len(result.before_nodes) == len(simple_process.steps)
        assert len(result.after_nodes) == len(simple_process.steps)

    def test_edges_reflect_dependencies(self):
        process = ProcessData(
            name="Two Step",
            steps=[
                ProcessStep(
                    step_name="Start", average_time_hours=1.0, resources_needed=1
                ),
                ProcessStep(
                    step_name="End",
                    average_time_hours=1.0,
                    resources_needed=1,
                    depends_on=["Start"],
                ),
            ],
        )
        result = build_graph_schema(process)
        assert len(result.edges) == 1
        assert result.edges[0].source == "Start"
        assert result.edges[0].target == "End"

    def test_no_edges_when_no_dependencies(self, simple_process):
        process = ProcessData(
            name="Flat",
            steps=[
                ProcessStep(step_name="A", average_time_hours=1.0, resources_needed=1),
                ProcessStep(step_name="B", average_time_hours=1.0, resources_needed=1),
            ],
        )
        result = build_graph_schema(process)
        assert result.edges == []

    def test_before_and_after_nodes_same_count(self, creative_agency_process):
        result = build_graph_schema(creative_agency_process)
        assert len(result.before_nodes) == len(result.after_nodes)

    def test_positions_are_consistent_before_and_after(self, simple_process):
        result = build_graph_schema(simple_process)
        for b, a in zip(result.before_nodes, result.after_nodes, strict=False):
            assert b.step_name == a.step_name
            assert b.x == a.x
            assert b.y == a.y


# ---------------------------------------------------------------------------
# build_graph_schema — severity assignment
# ---------------------------------------------------------------------------


class TestSeverityAssignment:
    def test_no_insight_all_normal(self, simple_process):
        result = build_graph_schema(simple_process, analysis_insight=None)
        for node in result.before_nodes:
            assert node.severity == "normal"

    def test_high_severity_issue_colors_affected_step(self):
        from processiq.models import Recommendation

        process = ProcessData(
            name="P",
            steps=[
                ProcessStep(
                    step_name="Bottleneck Step",
                    average_time_hours=2.0,
                    resources_needed=1,
                ),
                ProcessStep(
                    step_name="Normal Step", average_time_hours=1.0, resources_needed=1
                ),
            ],
        )
        insight = AnalysisInsight(
            process_summary="test",
            patterns=[],
            issues=[
                Issue(
                    title="Big bottleneck",
                    description="Very slow",
                    affected_steps=["Bottleneck Step"],
                    severity="high",
                )
            ],
            recommendations=[
                Recommendation(
                    title="Fix it",
                    addresses_issue="Big bottleneck",
                    description="Do something",
                    expected_benefit="Faster",
                    feasibility="easy",
                    affected_steps=["Bottleneck Step"],
                )
            ],
        )
        result = build_graph_schema(process, analysis_insight=insight)

        bottleneck_node = next(
            n for n in result.before_nodes if n.step_name == "Bottleneck Step"
        )
        normal_node = next(
            n for n in result.before_nodes if n.step_name == "Normal Step"
        )

        assert bottleneck_node.severity == "high"
        assert normal_node.severity == "normal"

    def test_core_value_step_colored_correctly(self):
        process = ProcessData(
            name="P",
            steps=[
                ProcessStep(
                    step_name="Core Work", average_time_hours=2.0, resources_needed=1
                ),
            ],
        )
        insight = AnalysisInsight(
            process_summary="test",
            patterns=[],
            issues=[],
            recommendations=[],
            not_problems=[
                NotAProblem(
                    step_name="Core Work", why_not_a_problem="This is the main value."
                )
            ],
        )
        result = build_graph_schema(process, analysis_insight=insight)
        node = result.before_nodes[0]
        assert node.severity == "core_value"

    def test_after_nodes_show_recommendation_affected(self):
        from processiq.models import Recommendation

        process = ProcessData(
            name="P",
            steps=[
                ProcessStep(
                    step_name="Slow Step", average_time_hours=3.0, resources_needed=1
                ),
                ProcessStep(
                    step_name="Fast Step", average_time_hours=0.5, resources_needed=1
                ),
            ],
        )
        insight = AnalysisInsight(
            process_summary="test",
            patterns=[],
            issues=[],
            recommendations=[
                Recommendation(
                    title="Speed up slow step",
                    addresses_issue="Slowness",
                    description="Automate it",
                    expected_benefit="2h saved",
                    feasibility="moderate",
                    affected_steps=["Slow Step"],
                )
            ],
        )
        result = build_graph_schema(process, analysis_insight=insight)

        # Before: no recommendation coloring
        before_slow = next(n for n in result.before_nodes if n.step_name == "Slow Step")
        assert before_slow.severity == "normal"

        # After: affected step gets recommendation_affected color
        after_slow = next(n for n in result.after_nodes if n.step_name == "Slow Step")
        assert after_slow.severity == "recommendation_affected"


# ---------------------------------------------------------------------------
# build_graph_schema — hover text
# ---------------------------------------------------------------------------


class TestHoverText:
    def test_hover_text_contains_step_name(self, simple_process):
        result = build_graph_schema(simple_process)
        for node in result.before_nodes:
            assert node.step_name in node.hover_text

    def test_hover_text_contains_time(self):
        process = ProcessData(
            name="P",
            steps=[
                ProcessStep(
                    step_name="My Step", average_time_hours=2.5, resources_needed=1
                )
            ],
        )
        result = build_graph_schema(process)
        assert "2.5h" in result.before_nodes[0].hover_text

    def test_time_pct_is_100_for_single_step(self):
        process = ProcessData(
            name="P",
            steps=[
                ProcessStep(
                    step_name="Only Step", average_time_hours=3.0, resources_needed=1
                )
            ],
        )
        result = build_graph_schema(process)
        assert result.before_nodes[0].time_pct == pytest.approx(100.0)
