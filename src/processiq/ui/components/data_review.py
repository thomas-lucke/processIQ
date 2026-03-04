"""Data review component for ProcessIQ UI.

Gate before analysis where user reviews and confirms the data.
Highlights missing fields and shows data quality indicators.
"""

import logging

import pandas as pd
import streamlit as st

from processiq.analysis import calculate_confidence
from processiq.models import ProcessData
from processiq.ui.state import (
    get_business_profile,
    get_constraints,
    get_process_data,
    is_data_confirmed,
    set_confidence_score,
    set_data_confirmed,
    set_data_gaps,
)
from processiq.ui.styles import format_hours, get_confidence_color

logger = logging.getLogger(__name__)


def render_data_review() -> bool:
    """Render the data review section.

    This is the gate before analysis. User must confirm data before proceeding.

    Returns:
        True if data is confirmed and ready for analysis, False otherwise.
    """
    process_data = get_process_data()

    if not process_data:
        st.warning("No process data available. Please enter process steps first.")
        return False

    st.markdown("### Review Your Data")
    st.markdown(
        "*Review the data below before analysis. "
        "Missing or incomplete data will reduce confidence in recommendations.*"
    )

    # Show process summary
    _render_process_summary(process_data)

    # Show steps table
    _render_steps_table(process_data)

    # Show data quality assessment
    confidence_ok = _render_data_quality(process_data)

    # Confirmation section
    st.markdown("---")

    col1, col2 = st.columns([3, 1])

    with col1:
        if not confidence_ok:
            st.warning(
                "Some data is missing. Analysis will proceed with lower confidence. "
                "You can still continue or go back to add more details."
            )

    with col2:
        confirmed = is_data_confirmed()

        if st.button(
            "Confirm Data",
            type="primary",
            disabled=confirmed,
            key="confirm_data_btn",
        ):
            set_data_confirmed(True)
            st.rerun()

    return is_data_confirmed()


def _render_process_summary(process_data: ProcessData) -> None:
    """Render a summary of the process."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Process", process_data.name)

    with col2:
        st.metric("Steps", len(process_data.steps))

    with col3:
        st.metric("Total Time", format_hours(process_data.total_time_hours) or "0h")

    with col4:
        st.metric("Total Cost", f"${process_data.total_cost:,.0f}")


def _render_steps_table(process_data: ProcessData) -> None:
    """Render the process steps as a table."""
    # Build DataFrame for display
    rows = []
    for step in process_data.steps:
        row = {
            "Step": step.step_name,
            "Time (h)": step.average_time_hours,
            "People": step.resources_needed,
            "Problem Freq. (%)": step.error_rate_pct,
            "Cost ($)": step.cost_per_instance,
            "Depends On": ", ".join(step.depends_on) if step.depends_on else "-",
        }
        rows.append(row)

    df = pd.DataFrame(rows)

    # Highlight missing/default values
    def highlight_missing(val: object, col_name: str) -> str:
        """Style cells with default/missing values."""
        if col_name == "Problem Freq. (%)" and val == 0:
            return "background-color: #fef3c7"  # Amber-100
        if col_name == "Cost ($)" and val == 0:
            return "background-color: #fef3c7"
        return ""

    # Apply styling (axis=0 applies column-wise; x.name is the column name)
    styled_df = df.style.apply(
        lambda x: [highlight_missing(v, str(x.name)) for v in x],
        axis=0,
    )

    st.dataframe(
        styled_df,
        width="stretch",
        hide_index=True,
    )

    # Legend
    st.caption(
        "Highlighted cells indicate default values that may reduce analysis confidence."
    )


def _render_data_quality(process_data: ProcessData) -> bool:
    """Render data quality assessment.

    Returns:
        True if confidence is acceptable (>= 60%), False otherwise.
    """
    constraints = get_constraints()
    profile = get_business_profile()

    # Calculate confidence
    confidence_result = calculate_confidence(
        process=process_data,
        constraints=constraints,
        profile=profile,
    )

    # Store in session state
    set_confidence_score(confidence_result.score)
    set_data_gaps(confidence_result.data_gaps)

    st.markdown("#### Data Quality Assessment")

    col1, col2 = st.columns([1, 2])

    with col1:
        # Confidence score with color
        color = get_confidence_color(confidence_result.score)
        st.markdown(
            f"""
            <div style="padding: 1rem; background: {color}15; border-left: 3px solid {color}; border-radius: 0.25rem;">
                <div style="color: #64748b; font-size: 0.875rem;">Data Confidence</div>
                <div style="color: {color}; font-size: 2rem; font-weight: 600;">{confidence_result.score * 100:.0f}%</div>
                <div style="color: #64748b; font-size: 0.75rem;">{confidence_result.level.replace('_', ' ').title()}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col2:
        # Data gaps
        if confidence_result.data_gaps:
            st.markdown("**Missing or incomplete data:**")
            for gap in confidence_result.data_gaps[:5]:  # Limit to 5
                st.markdown(f"- {gap}")
            if len(confidence_result.data_gaps) > 5:
                st.markdown(f"- ... and {len(confidence_result.data_gaps) - 5} more")
        else:
            st.success("All recommended data fields are populated.")

    # Breakdown
    with st.expander("Confidence Score Breakdown", expanded=False):
        breakdown = confidence_result.breakdown

        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("**Process Data**")
            st.progress(breakdown.get("process_completeness", 0))
            st.caption(f"{breakdown.get('process_completeness', 0) * 100:.0f}%")

        with col2:
            st.markdown("**Constraints**")
            st.progress(breakdown.get("constraints_completeness", 0))
            st.caption(f"{breakdown.get('constraints_completeness', 0) * 100:.0f}%")

        with col3:
            st.markdown("**Business Context**")
            st.progress(breakdown.get("profile_completeness", 0))
            st.caption(f"{breakdown.get('profile_completeness', 0) * 100:.0f}%")

    return confidence_result.is_sufficient
