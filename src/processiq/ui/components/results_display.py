"""Results display component for ProcessIQ UI.

Summary-first, details expandable.

Displays analysis results in organized sections:
- Process summary (lead with insight, not data tables)
- Issues identified (with root cause hypotheses)
- Recommendations (linked to specific issues, with trade-offs)
- Core value work (what looks slow but isn't waste)
- Expandable details: patterns, data quality, reasoning trace
"""

import logging

import streamlit as st

from processiq.models import AnalysisInsight
from processiq.models.insight import Issue, NotAProblem, Recommendation
from processiq.models.process import ProcessData
from processiq.ui.components.process_visualization import render_process_visualization
from processiq.ui.state import (
    get_analysis_insight,
    get_process_data,
    get_reasoning_trace,
    get_recommendation_feedback,
    set_recommendation_feedback,
)
from processiq.ui.styles import COLORS, get_severity_color

logger = logging.getLogger(__name__)


def render_results() -> None:
    """Render the analysis results section."""
    insight = get_analysis_insight()
    process_data = get_process_data()

    if insight:
        _render_insight_results(insight, process_data)
    else:
        st.info("No analysis results available. Run the analysis first.")


# =============================================================================
# NEW: AnalysisInsight rendering (summary-first, details expandable)
# =============================================================================


def _render_insight_results(
    insight: AnalysisInsight, process_data: ProcessData | None = None
) -> None:
    """Render new LLM-based analysis insight."""
    # What I Found - lead with summary
    _render_insight_summary(insight)

    # Process visualization (between summary and opportunities)
    if process_data is not None:
        st.markdown("### Process Flow")
        render_process_visualization(process_data, insight)

    # Main opportunities (issues + recommendations together)
    _render_opportunities(insight)

    # Core value work (not problems)
    if insight.not_problems:
        _render_not_problems(insight.not_problems)

    # Expandable sections
    _render_expandable_details(insight)


def _render_insight_summary(insight: AnalysisInsight) -> None:
    """Render the insight summary - lead with what we found."""
    st.markdown("### What I Found")

    # Process summary
    if insight.process_summary:
        st.markdown(insight.process_summary)

    # Quick stats in subtle style
    col1, col2, col3 = st.columns(3)

    with col1:
        issue_count = len(insight.issues)
        high_severity = sum(1 for i in insight.issues if i.severity == "high")
        label = f"{issue_count} issue{'s' if issue_count != 1 else ''}"
        if high_severity:
            label += f" ({high_severity} significant)"
        st.caption(label)

    with col2:
        rec_count = len(insight.recommendations)
        st.caption(f"{rec_count} recommendation{'s' if rec_count != 1 else ''}")

    with col3:
        ok_count = len(insight.not_problems)
        if ok_count:
            st.caption(f"{ok_count} area{'s' if ok_count != 1 else ''} that look fine")

    st.markdown("---")


def _render_opportunities(insight: AnalysisInsight) -> None:
    """Render issues and their linked recommendations together."""
    if not insight.issues and not insight.recommendations:
        st.success("No significant issues identified in this process.")
        return

    st.markdown("### Main Opportunities")

    # Build a map of issue title -> recommendations
    issue_to_recs: dict[str, list[Recommendation]] = {}
    unlinked_recs: list[Recommendation] = []

    for rec in insight.recommendations:
        if rec.addresses_issue:
            if rec.addresses_issue not in issue_to_recs:
                issue_to_recs[rec.addresses_issue] = []
            issue_to_recs[rec.addresses_issue].append(rec)
        else:
            unlinked_recs.append(rec)

    # Render each issue with its recommendations
    for i, issue in enumerate(insight.issues):
        _render_issue_with_recommendations(
            issue=issue,
            index=i + 1,
            recommendations=issue_to_recs.get(issue.title, []),
        )

    # Render any recommendations not linked to issues
    if unlinked_recs:
        st.markdown("#### Additional Recommendations")
        for i, rec in enumerate(unlinked_recs):
            _render_standalone_recommendation(rec, i + 1)


def _render_issue_with_recommendations(
    issue: Issue,
    index: int,
    recommendations: list[Recommendation],
) -> None:
    """Render an issue card with its linked recommendations."""
    severity_color = get_severity_color(issue.severity)

    # Issue container with colored left border
    st.markdown(
        f"""
        <div style="
            border-left: 4px solid {severity_color};
            padding-left: 1rem;
            margin-bottom: 1.5rem;
        ">
            <div style="
                display: flex;
                justify-content: space-between;
                align-items: flex-start;
                margin-bottom: 0.5rem;
            ">
                <h4 style="margin: 0; font-size: 1.1rem; color: {COLORS['text']};">
                    {index}. {issue.title}
                </h4>
                <span style="
                    display: inline-block;
                    padding: 0.125rem 0.5rem;
                    background: {severity_color}15;
                    color: {severity_color};
                    border-radius: 0.25rem;
                    font-size: 0.75rem;
                    font-weight: 500;
                    text-transform: uppercase;
                ">{issue.severity}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Description
    st.markdown(issue.description)

    # Affected steps
    if issue.affected_steps:
        st.caption(f"Affects: {', '.join(issue.affected_steps)}")

    # Root cause hypothesis (if meaningful)
    if issue.root_cause_hypothesis:
        with st.expander("Why this might be happening", expanded=False):
            st.markdown(issue.root_cause_hypothesis)
            if issue.evidence:
                st.markdown("**Evidence:**")
                for ev in issue.evidence:
                    st.markdown(f"- {ev}")

    # Linked recommendations
    if recommendations:
        st.markdown("**Suggested actions:**")
        for rec in recommendations:
            _render_recommendation_compact(rec)

    st.markdown("")  # Spacing


def _render_recommendation_compact(rec: Recommendation) -> None:
    """Render a recommendation in compact form (within an issue)."""
    # Feasibility indicator
    feasibility_icons = {
        "easy": "Low effort",
        "moderate": "Moderate effort",
        "complex": "High effort",
    }
    feasibility_text = feasibility_icons.get(rec.feasibility, rec.feasibility)

    st.markdown(f"**{rec.title}** ({feasibility_text})")
    st.markdown(rec.description)

    # Expected benefit + ROI
    if rec.expected_benefit:
        st.markdown(f"Expected benefit: {rec.expected_benefit}")

    if rec.estimated_roi:
        st.markdown(
            f"""<div style="
                font-size: 0.85rem;
                padding: 0.4rem 0.75rem;
                background: {COLORS['success']}10;
                border-left: 2px solid {COLORS['success']};
                border-radius: 0 0.25rem 0.25rem 0;
                margin: 0.25rem 0 0.5rem 0;
                color: {COLORS['text']};
            ">
                <strong>Estimated ROI:</strong> {rec.estimated_roi}
                <span style="font-size: 0.75rem; color: {COLORS['text_muted']};">
                    (rough estimate)
                </span>
            </div>""",
            unsafe_allow_html=True,
        )

    # Progressive disclosure: plain explanation (Layer 2)
    if rec.plain_explanation:
        with st.expander("What this means in practice", expanded=False):
            st.markdown(rec.plain_explanation)

    # Progressive disclosure: concrete next steps (Layer 3)
    if rec.concrete_next_steps:
        with st.expander("How to get started", expanded=False):
            for i, step in enumerate(rec.concrete_next_steps, 1):
                st.markdown(f"{i}. {step}")

    # Trade-offs / risks
    if rec.risks:
        with st.expander("Trade-offs and risks", expanded=False):
            for risk in rec.risks:
                st.markdown(f"- {risk}")

    # Prerequisites
    if rec.prerequisites:
        with st.expander("Prerequisites", expanded=False):
            for prereq in rec.prerequisites:
                st.markdown(f"- {prereq}")

    _render_feedback_buttons(rec.title)


def _render_feedback_buttons(rec_title: str) -> None:
    """Render compact thumbs up/down feedback buttons for a recommendation."""
    feedback = get_recommendation_feedback()
    existing = feedback.get(rec_title)

    # Stable widget key from title
    safe_key = "".join(c if c.isalnum() else "_" for c in rec_title)[:40]

    if existing and existing["vote"] == "up":
        st.caption("Marked as helpful")
        return

    if existing and existing["vote"] == "down":
        reason = existing.get("reason")
        if reason:
            st.caption(f"Not useful: {reason}")
        else:
            # Allow adding a reason after voting down
            reason_input = st.text_input(
                "Why not?",
                key=f"reason_{safe_key}",
                placeholder="Optional: why doesn't this work for you?",
                label_visibility="collapsed",
            )
            if reason_input:
                set_recommendation_feedback(rec_title, "down", reason_input)
                st.rerun()
            else:
                st.caption("Marked as not useful")
        return

    # No feedback yet — show vote buttons with tooltip
    cols = st.columns([2, 2, 0.4, 7.4])
    with cols[0]:
        if st.button(
            "Helpful",
            key=f"up_{safe_key}",
            type="secondary",
            use_container_width=True,
        ):
            set_recommendation_feedback(rec_title, "up")
            st.rerun()
    with cols[1]:
        if st.button(
            "Not useful",
            key=f"down_{safe_key}",
            type="secondary",
            use_container_width=True,
        ):
            set_recommendation_feedback(rec_title, "down")
            st.rerun()
    with cols[2]:
        st.markdown(
            '<span title="Your feedback helps the AI learn which '
            "recommendations are relevant to your situation. When you "
            "re-run the analysis, rated recommendations are adjusted "
            'accordingly." style="cursor: help; font-size: 0.85rem; '
            f'color: {COLORS["text_muted"]}; vertical-align: middle;">'
            "&#9432;</span>",
            unsafe_allow_html=True,
        )


def _render_standalone_recommendation(rec: Recommendation, index: int) -> None:
    """Render a recommendation that isn't linked to a specific issue."""
    st.markdown(f"**{index}. {rec.title}**")
    st.caption(f"Feasibility: {rec.feasibility}")
    st.markdown(rec.description)

    if rec.expected_benefit:
        st.markdown(f"Expected benefit: {rec.expected_benefit}")

    if rec.estimated_roi:
        st.markdown(
            f"""<div style="
                font-size: 0.85rem;
                padding: 0.4rem 0.75rem;
                background: {COLORS['success']}10;
                border-left: 2px solid {COLORS['success']};
                border-radius: 0 0.25rem 0.25rem 0;
                margin: 0.25rem 0 0.5rem 0;
                color: {COLORS['text']};
            ">
                <strong>Estimated ROI:</strong> {rec.estimated_roi}
                <span style="font-size: 0.75rem; color: {COLORS['text_muted']};">
                    (rough estimate)
                </span>
            </div>""",
            unsafe_allow_html=True,
        )

    # Progressive disclosure: plain explanation (Layer 2)
    if rec.plain_explanation:
        with st.expander("What this means in practice", expanded=False):
            st.markdown(rec.plain_explanation)

    # Progressive disclosure: concrete next steps (Layer 3)
    if rec.concrete_next_steps:
        with st.expander("How to get started", expanded=False):
            for i, step in enumerate(rec.concrete_next_steps, 1):
                st.markdown(f"{i}. {step}")

    if rec.risks:
        with st.expander("Trade-offs", expanded=False):
            for risk in rec.risks:
                st.markdown(f"- {risk}")

    _render_feedback_buttons(rec.title)
    st.markdown("---")


def _render_not_problems(not_problems: list[NotAProblem]) -> None:
    """Render the 'not problems' section - core value work that looks slow."""
    st.markdown("### Core Value Work")
    st.markdown(
        "_These steps may look like bottlenecks, but they're where real value is created:_"
    )

    for np in not_problems:
        st.markdown(
            f"""
            <div style="
                background: {COLORS['background_alt']};
                border-left: 4px solid {COLORS['success']};
                padding: 0.75rem 1rem;
                margin-bottom: 0.75rem;
                border-radius: 0 0.25rem 0.25rem 0;
            ">
                <strong>{np.step_name}</strong>
                <p style="margin: 0.5rem 0 0 0; color: {COLORS['text']};">
                    {np.why_not_a_problem}
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Why it might look problematic
        if np.appears_problematic_because:
            st.caption(f"Why it might look slow: {np.appears_problematic_because}")

    st.markdown("---")


def _render_expandable_details(insight: AnalysisInsight) -> None:
    """Render expandable sections for patterns, data quality, etc."""
    # Patterns detected
    if insight.patterns:
        with st.expander("Patterns Detected", expanded=False):
            for pattern in insight.patterns:
                st.markdown(f"- {pattern}")

    # Investigation details (populated by agentic tool loop when enabled)
    if insight.investigation_findings:
        with st.expander("Investigation Details", expanded=False):
            st.markdown("_Additional findings from the automated investigation loop:_")
            for finding in insight.investigation_findings:
                st.markdown(f"- {finding}")

    # Follow-up questions (if LLM had any)
    if insight.follow_up_questions:
        with st.expander("Questions to Consider", expanded=False):
            st.markdown("_Answering these would help refine the analysis:_")
            for q in insight.follow_up_questions:
                st.markdown(f"- {q}")

    # Confidence notes / caveats
    if insight.confidence_notes:
        with st.expander("Analysis Caveats", expanded=False):
            st.markdown(insight.confidence_notes)

    # Reasoning trace
    _render_reasoning_trace()


def _render_reasoning_trace() -> None:
    """Render the reasoning trace section (collapsed by default)."""
    trace = get_reasoning_trace()

    if not trace:
        return

    with st.expander("Reasoning Trace (Agent Decisions)", expanded=False):
        st.markdown(
            "*This trace shows the agent's decision-making process for audit and review:*"
        )

        for i, entry in enumerate(trace):
            st.markdown(f"{i + 1}. {entry}")

        # Copy button for portfolio reviewers
        trace_text = "\n".join([f"{i + 1}. {entry}" for i, entry in enumerate(trace)])
        st.text_area(
            "Copy trace:",
            value=trace_text,
            height=100,
            key="trace_copy",
            label_visibility="collapsed",
        )
