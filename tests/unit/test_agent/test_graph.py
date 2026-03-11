"""Tests for processiq.agent.graph."""

from processiq.agent.graph import build_graph, compile_graph


class TestBuildGraph:
    def test_has_expected_nodes(self):
        graph = build_graph()
        nodes = set(graph.nodes.keys()) - {"__start__", "__end__"}
        expected = {
            "check_context",
            "initial_analysis",
            "investigate",
            "tools",
            "finalize",
            "request_clarification",
        }
        assert nodes == expected

    def test_no_old_nodes(self):
        graph = build_graph()
        nodes = set(graph.nodes.keys())
        old_nodes = {
            "detect_bottlenecks",
            "generate_suggestions",
            "validate_constraints",
            "calculate_roi",
            "generate_alternatives",
        }
        assert nodes.isdisjoint(old_nodes)


class TestCompileGraph:
    def test_returns_runnable(self):
        app = compile_graph()
        assert app is not None

    def test_caches_result(self):
        app1 = compile_graph()
        app2 = compile_graph()
        assert app1 is app2
