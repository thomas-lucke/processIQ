"""Tests for processiq.agent.edges."""

from langchain_core.messages import AIMessage

from processiq.agent.edges import (
    route_after_clarification,
    route_after_context_check,
    route_after_initial_analysis,
    route_investigation,
)
from processiq.models import AnalysisInsight, Issue


class TestRouteAfterContextCheck:
    def test_sufficient_routes_to_analyze(self):
        state = {"needs_clarification": False}
        assert route_after_context_check(state) == "analyze"

    def test_insufficient_routes_to_clarification(self):
        state = {"needs_clarification": True}
        assert route_after_context_check(state) == "request_clarification"

    def test_missing_key_defaults_to_analyze(self):
        state = {}
        assert route_after_context_check(state) == "analyze"


class TestRouteAfterClarification:
    def test_with_response_routes_to_check_context(self):
        state = {"user_response": "Some answer", "confidence_score": 0.3}
        assert route_after_clarification(state) == "check_context"

    def test_no_response_high_confidence_routes_to_analyze(self):
        state = {"user_response": None, "confidence_score": 0.5}
        assert route_after_clarification(state) == "analyze"

    def test_no_response_at_threshold_routes_to_analyze(self):
        state = {"user_response": None, "confidence_score": 0.4}
        assert route_after_clarification(state) == "analyze"

    def test_no_response_low_confidence_routes_to_check_context(self):
        state = {"user_response": None, "confidence_score": 0.3}
        assert route_after_clarification(state) == "check_context"

    def test_empty_response_treated_as_no_response(self):
        state = {"user_response": "", "confidence_score": 0.5}
        # Empty string is falsy, so treated as no response
        assert route_after_clarification(state) == "analyze"

    def test_missing_keys_defaults(self):
        state = {}
        # user_response defaults to None (falsy), confidence defaults to 0.0
        assert route_after_clarification(state) == "check_context"


# ---------------------------------------------------------------------------
# route_after_initial_analysis
# ---------------------------------------------------------------------------


def _make_insight_with_issues(n: int = 1) -> AnalysisInsight:
    issues = [
        Issue(title=f"Issue {i}", description="d", affected_steps=[], severity="medium")
        for i in range(n)
    ]
    return AnalysisInsight(
        process_summary="s",
        issues=issues,
        recommendations=[],
        patterns=[],
        not_problems=[],
    )


class TestRouteAfterInitialAnalysis:
    def test_routes_to_investigate_when_issues_found(self):
        insight = _make_insight_with_issues(2)
        state = {"analysis_insight": insight, "max_cycles_override": None}
        assert route_after_initial_analysis(state) == "investigate"

    def test_routes_to_finalize_when_no_insight(self):
        state = {"analysis_insight": None, "max_cycles_override": None}
        assert route_after_initial_analysis(state) == "finalize"

    def test_routes_to_finalize_when_no_issues(self):
        insight = _make_insight_with_issues(0)
        state = {"analysis_insight": insight, "max_cycles_override": None}
        assert route_after_initial_analysis(state) == "finalize"

    def test_zero_override_treated_as_no_override_routes_to_investigate(self):
        # max_cycles_override=0 is falsy, so it falls back to settings.agent_max_cycles.
        # 0 does NOT mean "disable investigation" — it means "use the default".
        # settings.agent_max_cycles is always >= 1, so investigation proceeds.
        insight = _make_insight_with_issues(3)
        state = {"analysis_insight": insight, "max_cycles_override": 0}
        assert route_after_initial_analysis(state) == "investigate"

    def test_max_cycles_override_one_allows_investigation(self):
        insight = _make_insight_with_issues(1)
        state = {"analysis_insight": insight, "max_cycles_override": 1}
        assert route_after_initial_analysis(state) == "investigate"


# ---------------------------------------------------------------------------
# route_investigation
# ---------------------------------------------------------------------------


class TestRouteInvestigation:
    def _ai_message_with_tools(self) -> AIMessage:
        msg = AIMessage(content="I will investigate")
        msg.tool_calls = [{"name": "get_step_details", "args": {}, "id": "tc1"}]
        return msg

    def _ai_message_no_tools(self) -> AIMessage:
        msg = AIMessage(content="Done investigating")
        msg.tool_calls = []
        return msg

    def test_routes_to_tools_when_tool_calls_and_under_limit(self):
        state = {
            "messages": [self._ai_message_with_tools()],
            "cycle_count": 0,
            "max_cycles_override": 3,
        }
        assert route_investigation(state) == "tools"

    def test_routes_to_finalize_when_no_tool_calls(self):
        state = {
            "messages": [self._ai_message_no_tools()],
            "cycle_count": 0,
            "max_cycles_override": 3,
        }
        assert route_investigation(state) == "finalize"

    def test_routes_to_finalize_when_cycle_limit_reached(self):
        state = {
            "messages": [self._ai_message_with_tools()],
            "cycle_count": 3,
            "max_cycles_override": 3,
        }
        assert route_investigation(state) == "finalize"

    def test_routes_to_finalize_when_messages_empty(self):
        state = {"messages": [], "cycle_count": 0, "max_cycles_override": 3}
        assert route_investigation(state) == "finalize"

    def test_routes_to_finalize_when_messages_missing(self):
        state = {"cycle_count": 0, "max_cycles_override": 3}
        assert route_investigation(state) == "finalize"

    def test_at_limit_minus_one_still_routes_to_tools(self):
        state = {
            "messages": [self._ai_message_with_tools()],
            "cycle_count": 2,
            "max_cycles_override": 3,
        }
        assert route_investigation(state) == "tools"
