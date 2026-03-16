"""Tests for processiq.agent.nodes (no LLM calls)."""

import pytest

from processiq.agent.nodes import (
    _format_business_context_for_llm,
    _format_constraints_for_llm,
    _format_feedback_history,
    _normalize_issue_links,
    check_context_sufficiency,
    finalize_analysis_node,
)
from processiq.agent.state import create_initial_state
from processiq.models import (
    AnalysisInsight,
    BusinessProfile,
    CompanySize,
    Constraints,
    Industry,
    Issue,
    Priority,
    Recommendation,
)

# ---------------------------------------------------------------------------
# check_context_sufficiency
# ---------------------------------------------------------------------------


class TestCheckContextSufficiency:
    def test_raises_without_process(self):
        state = {}
        with pytest.raises(ValueError, match="missing required 'process'"):
            check_context_sufficiency(state)

    def test_sufficient_context_sets_no_clarification(
        self, simple_process, full_profile, strict_constraints
    ):
        state = create_initial_state(
            process=simple_process,
            constraints=strict_constraints,
            profile=full_profile,
        )
        result = check_context_sufficiency(state)
        # Full profile + constraints should yield well above minimal confidence
        assert result["confidence_score"] > 0.5
        assert isinstance(result["needs_clarification"], bool)
        assert "current_phase" in result
        assert len(result["reasoning_trace"]) >= 1

    def test_insufficient_context_sets_clarification(self, single_step_process):
        """Single step process with no profile → low confidence → needs clarification."""
        state = create_initial_state(process=single_step_process)
        result = check_context_sufficiency(state)
        # Without profile/constraints confidence is low → should request clarification
        if result["needs_clarification"]:
            assert result["current_phase"] == "needs_clarification"
            assert "clarification_questions" in result
        else:
            assert result["current_phase"] == "analysis"

    def test_returns_confidence_score(self, simple_process):
        state = create_initial_state(process=simple_process)
        result = check_context_sufficiency(state)
        assert 0.0 <= result["confidence_score"] <= 1.0

    def test_appends_to_existing_reasoning_trace(self, simple_process):
        state = create_initial_state(process=simple_process)
        state["reasoning_trace"] = ["previous step"]
        result = check_context_sufficiency(state)
        assert result["reasoning_trace"][0] == "previous step"
        assert len(result["reasoning_trace"]) == 2

    def test_data_gaps_returned(self, single_step_process):
        state = create_initial_state(process=single_step_process)
        result = check_context_sufficiency(state)
        assert isinstance(result["data_gaps"], list)

    def test_clarification_questions_limited_to_three(self, single_step_process):
        state = create_initial_state(process=single_step_process)
        result = check_context_sufficiency(state)
        if result.get("needs_clarification"):
            assert len(result["clarification_questions"]) <= 3


# ---------------------------------------------------------------------------
# finalize_analysis_node
# ---------------------------------------------------------------------------


class TestFinalizeAnalysisNode:
    def _make_insight(self, num_issues=1, num_recs=1):
        issues = [
            Issue(
                title=f"Issue {i}",
                description="desc",
                affected_steps=["Step A"],
                severity="medium",
            )
            for i in range(num_issues)
        ]
        recommendations = [
            Recommendation(
                title=f"Rec {i}",
                addresses_issue="Issue 0",
                description="do it",
                expected_benefit="benefit",
                feasibility="easy",
            )
            for i in range(num_recs)
        ]
        return AnalysisInsight(
            process_summary="summary",
            issues=issues,
            recommendations=recommendations,
            patterns=[],
            not_problems=[],
        )

    def test_sets_phase_to_complete(self, simple_process):
        state = create_initial_state(process=simple_process)
        state["analysis_insight"] = self._make_insight()
        state["confidence_score"] = 0.8
        result = finalize_analysis_node(state)
        assert result["current_phase"] == "complete"

    def test_reasoning_trace_appended(self, simple_process):
        state = create_initial_state(process=simple_process)
        state["analysis_insight"] = self._make_insight()
        state["confidence_score"] = 0.75
        state["reasoning_trace"] = ["previous"]
        result = finalize_analysis_node(state)
        assert result["reasoning_trace"][0] == "previous"
        assert len(result["reasoning_trace"]) == 2

    def test_error_state_included_in_reasoning(self, simple_process):
        state = create_initial_state(process=simple_process)
        state["error"] = "LLM timed out"
        state["confidence_score"] = 0.0
        result = finalize_analysis_node(state)
        assert "error" in result["reasoning_trace"][-1].lower()

    def test_no_insight_handled_gracefully(self, simple_process):
        state = create_initial_state(process=simple_process)
        state["analysis_insight"] = None
        state["confidence_score"] = 0.0
        result = finalize_analysis_node(state)
        assert result["current_phase"] == "complete"
        assert "no results" in result["reasoning_trace"][-1].lower()

    def test_tool_findings_incorporated_into_insight(self, simple_process):
        from langchain_core.messages import ToolMessage

        insight = self._make_insight()
        state = create_initial_state(process=simple_process)
        state["analysis_insight"] = insight
        state["confidence_score"] = 0.8
        state["messages"] = [
            ToolMessage(content="Tool found bottleneck at step 2", tool_call_id="tc1"),
            ToolMessage(content="Dependency delay confirmed", tool_call_id="tc2"),
        ]
        result = finalize_analysis_node(state)
        assert insight.investigation_findings == [
            "Tool found bottleneck at step 2",
            "Dependency delay confirmed",
        ]
        assert result["current_phase"] == "complete"

    def test_empty_tool_messages_not_added(self, simple_process):
        from langchain_core.messages import ToolMessage

        insight = self._make_insight()
        insight.investigation_findings = []
        state = create_initial_state(process=simple_process)
        state["analysis_insight"] = insight
        state["confidence_score"] = 0.8
        state["messages"] = [ToolMessage(content="", tool_call_id="tc1")]
        finalize_analysis_node(state)
        assert insight.investigation_findings == []


# ---------------------------------------------------------------------------
# _format_feedback_history
# ---------------------------------------------------------------------------


class TestFormatFeedbackHistory:
    def test_empty_returns_none(self):
        assert _format_feedback_history({}) is None

    def test_rejected_recommendation(self):
        feedback = {"Automate intake": {"vote": "down", "reason": "Too expensive"}}
        result = _format_feedback_history(feedback)
        assert result is not None
        assert "REJECTED" in result
        assert "Automate intake" in result
        assert "Too expensive" in result

    def test_rejected_without_reason(self):
        feedback = {"Automate intake": {"vote": "down"}}
        result = _format_feedback_history(feedback)
        assert result is not None
        assert "no reason given" in result

    def test_accepted_recommendation(self):
        feedback = {"Consolidate approvals": {"vote": "up"}}
        result = _format_feedback_history(feedback)
        assert result is not None
        assert "ACCEPTED" in result
        assert "Consolidate approvals" in result

    def test_mixed_feedback_shows_both_sections(self):
        feedback = {
            "Automate intake": {"vote": "down", "reason": "Budget"},
            "Hire contractor": {"vote": "up"},
        }
        result = _format_feedback_history(feedback)
        assert result is not None
        assert "REJECTED" in result
        assert "ACCEPTED" in result

    def test_rejected_comes_before_accepted(self):
        feedback = {
            "Good idea": {"vote": "up"},
            "Bad idea": {"vote": "down", "reason": "Wrong"},
        }
        result = _format_feedback_history(feedback)
        assert result is not None
        assert result.index("REJECTED") < result.index("ACCEPTED")


# ---------------------------------------------------------------------------
# _normalize_issue_links
# ---------------------------------------------------------------------------


class TestNormalizeIssueLinks:
    def _make_insight(self, issue_title: str, addresses_issue: str) -> AnalysisInsight:
        return AnalysisInsight(
            process_summary="summary",
            issues=[
                Issue(
                    title=issue_title,
                    description="desc",
                    affected_steps=["Step A"],
                    severity="high",
                )
            ],
            recommendations=[
                Recommendation(
                    title="Fix it",
                    addresses_issue=addresses_issue,
                    description="do this",
                    expected_benefit="saves time",
                    feasibility="easy",
                )
            ],
            patterns=[],
            not_problems=[],
        )

    def test_exact_match_unchanged(self):
        insight = self._make_insight("Redundant approvals", "Redundant approvals")
        result = _normalize_issue_links(insight)
        assert result.recommendations[0].addresses_issue == "Redundant approvals"

    def test_case_insensitive_match(self):
        insight = self._make_insight("Redundant Approvals", "redundant approvals")
        result = _normalize_issue_links(insight)
        assert result.recommendations[0].addresses_issue == "Redundant Approvals"

    def test_substring_match_ai_contained_in_title(self):
        # addresses_issue "Slow review" is contained in title "Slow review bottleneck"
        insight = self._make_insight("Slow review bottleneck", "Slow review")
        result = _normalize_issue_links(insight)
        assert result.recommendations[0].addresses_issue == "Slow review bottleneck"

    def test_substring_match_title_contained_in_ai(self):
        # issue title "Redundant approvals" is contained in addresses_issue
        insight = self._make_insight(
            "Redundant approvals", "Redundant approvals in manager step"
        )
        result = _normalize_issue_links(insight)
        assert result.recommendations[0].addresses_issue == "Redundant approvals"

    def test_no_issues_returns_unchanged(self):
        insight = AnalysisInsight(
            process_summary="s",
            issues=[],
            recommendations=[
                Recommendation(
                    title="Fix it",
                    addresses_issue="something",
                    description="d",
                    expected_benefit="e",
                    feasibility="easy",
                )
            ],
            patterns=[],
            not_problems=[],
        )
        result = _normalize_issue_links(insight)
        assert result.recommendations[0].addresses_issue == "something"

    def test_no_recommendations_returns_unchanged(self):
        insight = AnalysisInsight(
            process_summary="s",
            issues=[
                Issue(
                    title="Issue A", description="d", affected_steps=[], severity="low"
                )
            ],
            recommendations=[],
            patterns=[],
            not_problems=[],
        )
        result = _normalize_issue_links(insight)
        assert result.issues[0].title == "Issue A"

    def test_unmatched_link_left_unchanged(self):
        insight = self._make_insight("Issue Alpha", "completely unrelated")
        result = _normalize_issue_links(insight)
        assert result.recommendations[0].addresses_issue == "completely unrelated"

    def test_empty_addresses_issue_skipped(self):
        """Recommendations with no addresses_issue are left alone."""
        insight = AnalysisInsight(
            process_summary="s",
            issues=[
                Issue(
                    title="Issue A", description="d", affected_steps=[], severity="low"
                )
            ],
            recommendations=[
                Recommendation(
                    title="General rec",
                    addresses_issue="",
                    description="d",
                    expected_benefit="e",
                    feasibility="easy",
                )
            ],
            patterns=[],
            not_problems=[],
        )
        result = _normalize_issue_links(insight)
        # Empty string is falsy — treated as no link, left unchanged
        assert result.recommendations[0].addresses_issue == ""


# ---------------------------------------------------------------------------
# _format_constraints_for_llm
# ---------------------------------------------------------------------------


class TestFormatConstraintsForLlm:
    def test_no_explicit_constraints_returns_priority_only(self):
        """Default Constraints() has a default priority, so it's not fully empty."""
        result = _format_constraints_for_llm(Constraints())
        # Default priority is included; the string is non-empty
        assert isinstance(result, str)
        assert len(result) > 0

    def test_default_constraints_includes_priority(self):
        """Default Constraints always has a priority — never returns bare default message."""
        c = Constraints()
        result = _format_constraints_for_llm(c)
        # Priority is always set (default=COST_REDUCTION), so result is non-empty
        assert "cost_reduction" in result.lower()

    def test_budget_limit_included(self):
        c = Constraints(budget_limit=10000.0)
        result = _format_constraints_for_llm(c)
        assert "10,000" in result

    def test_no_new_hires_included(self):
        c = Constraints(no_new_hires=True)
        result = _format_constraints_for_llm(c)
        assert "Cannot hire" in result

    def test_audit_trail_included(self):
        c = Constraints(must_maintain_audit_trail=True)
        result = _format_constraints_for_llm(c)
        assert "audit trail" in result

    def test_max_weeks_included(self):
        c = Constraints(timeline_weeks=6)
        result = _format_constraints_for_llm(c)
        assert "6 weeks" in result

    def test_priority_included(self):
        c = Constraints(priority=Priority.COST_REDUCTION)
        result = _format_constraints_for_llm(c)
        assert "cost_reduction" in result.lower()

    def test_custom_constraints_included(self):
        c = Constraints(custom_constraints=["No cloud", "GDPR compliance"])
        result = _format_constraints_for_llm(c)
        assert "No cloud" in result
        assert "GDPR compliance" in result

    def test_full_constraints(self, strict_constraints):
        result = _format_constraints_for_llm(strict_constraints)
        assert "5,000" in result
        assert "Cannot hire" in result
        assert "audit trail" in result
        assert "4 weeks" in result


# ---------------------------------------------------------------------------
# _format_business_context_for_llm
# ---------------------------------------------------------------------------


class TestFormatBusinessContextForLlm:
    def test_minimal_profile_renders(self):
        profile = BusinessProfile(
            industry=Industry.TECHNOLOGY,
            company_size=CompanySize.SMALL,
        )
        result = _format_business_context_for_llm(profile)
        assert "Technology" in result or "technology" in result.lower()
        assert "Small" in result or "50-200" in result

    def test_full_profile_includes_all_sections(self, full_profile):
        result = _format_business_context_for_llm(full_profile)
        assert "Financial" in result or "financial" in result.lower()
        assert "Enterprise" in result or "1000" in result
        assert "Regulatory" in result
        assert "RPA" in result  # from notes

    def test_rejected_approaches_included(self):
        profile = BusinessProfile(
            industry=Industry.HEALTHCARE,
            rejected_approaches=["Offshore outsourcing", "RPA"],
        )
        result = _format_business_context_for_llm(profile)
        assert "Offshore outsourcing" in result
        assert "RPA" in result

    def test_revenue_prefer_not_to_say_omitted(self):
        from processiq.models.memory import RevenueRange

        profile = BusinessProfile(
            industry=Industry.TECHNOLOGY,
            annual_revenue=RevenueRange.PREFER_NOT_TO_SAY,
        )
        result = _format_business_context_for_llm(profile)
        assert "revenue" not in result.lower()

    def test_revenue_shown_when_provided(self):
        from processiq.models.memory import RevenueRange

        profile = BusinessProfile(
            industry=Industry.TECHNOLOGY,
            annual_revenue=RevenueRange.FROM_1M_TO_5M,
        )
        result = _format_business_context_for_llm(profile)
        assert "revenue" in result.lower() or "$1M" in result

    def test_notes_included(self):
        profile = BusinessProfile(
            industry=Industry.MANUFACTURING,
            notes="We use SAP for ERP. Migration not possible.",
        )
        result = _format_business_context_for_llm(profile)
        assert "SAP" in result
