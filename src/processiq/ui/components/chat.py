"""Chat component for ProcessIQ UI.

Handles conversation display, message rendering, and user input.
Uses Streamlit's native chat components with custom styling.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import pandas as pd
import streamlit as st

from processiq.models import AnalysisInsight, ProcessData, ProcessStep
from processiq.ui.state import set_process_data
from processiq.ui.styles import (
    COLORS,
    confidence_badge,
    format_hours,
    get_severity_color,
)

logger = logging.getLogger(__name__)


class MessageRole(str, Enum):
    """Who sent the message."""

    USER = "user"
    AGENT = "assistant"  # Streamlit uses "assistant" not "agent"
    SYSTEM = "system"


class MessageType(str, Enum):
    """Type of message content."""

    TEXT = "text"
    FILE = "file"
    DATA_CARD = "data_card"
    ANALYSIS = "analysis"
    CLARIFICATION = "clarification"
    STATUS = "status"
    ERROR = "error"


@dataclass
class ChatMessage:
    """A single message in the conversation."""

    role: MessageRole
    type: MessageType
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

    # Optional structured data
    data: Any = None  # ProcessData, etc.
    analysis_insight: AnalysisInsight | None = None
    file_name: str | None = None
    questions: list[dict[str, Any]] | None = None
    is_editable: bool = False
    confidence: float | None = None
    improvement_suggestions: str | None = None  # LLM suggestions for improving input
    suggested_questions: list[str] | None = None  # Targeted follow-up suggestions
    draft_insight: AnalysisInsight | None = None  # Draft analysis preview


def create_user_message(content: str) -> ChatMessage:
    """Create a user text message."""
    return ChatMessage(
        role=MessageRole.USER,
        type=MessageType.TEXT,
        content=content,
    )


def create_agent_message(content: str) -> ChatMessage:
    """Create an agent text message."""
    return ChatMessage(
        role=MessageRole.AGENT,
        type=MessageType.TEXT,
        content=content,
    )


def create_file_message(file_name: str) -> ChatMessage:
    """Create a file upload notification message."""
    return ChatMessage(
        role=MessageRole.USER,
        type=MessageType.FILE,
        content=f"Uploaded: {file_name}",
        file_name=file_name,
    )


def create_status_message(content: str) -> ChatMessage:
    """Create a status update message."""
    return ChatMessage(
        role=MessageRole.SYSTEM,
        type=MessageType.STATUS,
        content=content,
    )


def create_error_message(content: str) -> ChatMessage:
    """Create an error message."""
    return ChatMessage(
        role=MessageRole.SYSTEM,
        type=MessageType.ERROR,
        content=content,
    )


def create_data_card_message(
    process_data: ProcessData,
    content: str = "Review the extracted process data:",
    is_editable: bool = True,
    confidence: float | None = None,
    improvement_suggestions: str | None = None,
    suggested_questions: list[str] | None = None,
    draft_insight: "AnalysisInsight | None" = None,
) -> ChatMessage:
    """Create a data card message for process review."""
    return ChatMessage(
        role=MessageRole.AGENT,
        type=MessageType.DATA_CARD,
        content=content,
        data=process_data,
        is_editable=is_editable,
        confidence=confidence,
        improvement_suggestions=improvement_suggestions,
        suggested_questions=suggested_questions,
        draft_insight=draft_insight,
    )


def create_analysis_message(
    analysis_insight: AnalysisInsight | None = None,
    content: str = "Analysis complete.",
) -> ChatMessage:
    """Create an analysis results message.

    Args:
        analysis_insight: LLM-based analysis insight.
        content: Summary message to display.
    """
    return ChatMessage(
        role=MessageRole.AGENT,
        type=MessageType.ANALYSIS,
        content=content,
        analysis_insight=analysis_insight,
    )


def create_clarification_message(
    content: str,
    questions: list[dict[str, Any]],
) -> ChatMessage:
    """Create a clarification request message."""
    return ChatMessage(
        role=MessageRole.AGENT,
        type=MessageType.CLARIFICATION,
        content=content,
        questions=questions,
    )


def _compute_step_numbers(steps: list[ProcessStep]) -> list[str]:
    """Compute display step numbers with group and type labels.

    Sequential steps:              "1", "2", "3"
    Alternative group (either/or): "1a (OR)", "1b (OR)"
    Parallel group (simultaneous): "5a (AND)", "5b (AND)"
    Conditional step:              "6 (if)"
    Loop step:                     "7 (↩)"
    Combined:                      "4a (OR, if)"
    """
    numbers: list[str] = []
    base_num = 1
    seen_groups: dict[str, tuple[int, int]] = {}

    for step in steps:
        gid = getattr(step, "group_id", None)
        gtype = getattr(step, "group_type", None)
        stype = getattr(step, "step_type", "normal")

        type_tag = ""
        if stype == "conditional":
            type_tag = "if"
        elif stype == "loop":
            type_tag = "↩"

        if gid:
            if gid in seen_groups:
                grp_base, letter_idx = seen_groups[gid]
                letter = chr(ord("a") + letter_idx)
                seen_groups[gid] = (grp_base, letter_idx + 1)
            else:
                grp_base = base_num
                letter = "a"
                seen_groups[gid] = (grp_base, 1)
                base_num += 1

            group_label = "OR" if gtype == "alternative" else "AND"
            tags = ", ".join(filter(None, [group_label, type_tag]))
            numbers.append(f"{grp_base}{letter} ({tags})")
        else:
            label = f"{base_num} ({type_tag})" if type_tag else str(base_num)
            numbers.append(label)
            base_num += 1

    return numbers


def _render_text_message(message: ChatMessage) -> None:
    """Render a plain text message."""
    st.markdown(message.content)


def _render_file_message(message: ChatMessage) -> None:
    """Render a file upload notification."""
    st.markdown(
        f"""
        <div style="
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 0.75rem;
            background: {COLORS['background_alt']};
            border: 1px solid {COLORS['border']};
            border-radius: 0.375rem;
            font-size: 0.875rem;
        ">
            <span style="color: {COLORS['text_muted']};">File:</span>
            <span style="font-weight: 500;">{message.file_name}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_status_message(message: ChatMessage) -> None:
    """Render a status update."""
    st.markdown(
        f"""
        <div style="
            color: {COLORS['text_muted']};
            font-size: 0.875rem;
            font-style: italic;
            padding: 0.25rem 0;
        ">
            {message.content}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_error_message(message: ChatMessage) -> None:
    """Render an error message."""
    st.error(message.content)


def _render_data_card(message: ChatMessage) -> None:
    """Render a process data card for review/editing."""
    st.markdown(message.content)

    if message.confidence is not None:
        confidence_badge(message.confidence, "Data Completeness")
        st.markdown("")  # Spacing

    # Show improvement suggestions if available (LLM-generated guidance)
    if message.improvement_suggestions:
        st.markdown(
            f"""
            <div style="
                padding: 0.75rem 1rem;
                background: {COLORS['background_alt']};
                border-left: 3px solid {COLORS['primary']};
                border-radius: 0 0.375rem 0.375rem 0;
                margin-bottom: 1rem;
                font-size: 0.9rem;
                line-height: 1.5;
            ">
                <div style="
                    font-weight: 500;
                    color: {COLORS['primary']};
                    margin-bottom: 0.25rem;
                    font-size: 0.8rem;
                    text-transform: uppercase;
                    letter-spacing: 0.025em;
                ">What would help</div>
                <div style="color: {COLORS['text']};">
                    {message.improvement_suggestions}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    process_data: ProcessData | None = message.data
    if not process_data:
        st.warning("No process data available.")
        return

    # Build table data with numeric values and step numbering
    rows = []
    has_estimates = False
    step_notes: list[tuple[str, str, str]] = []  # (step_num, step_name, note)
    step_numbers = _compute_step_numbers(process_data.steps)

    for idx, step in enumerate(process_data.steps):
        estimated = set(getattr(step, "estimated_fields", []))
        notes = getattr(step, "notes", "") or ""

        # Show None (blank cell) for fields that are zero AND marked as estimated
        # This makes it visually obvious what data is missing
        time_val = (
            None
            if step.average_time_hours == 0 and "average_time_hours" in estimated
            else step.average_time_hours
        )
        cost_val = (
            None
            if step.cost_per_instance == 0 and "cost_per_instance" in estimated
            else step.cost_per_instance
        )
        freq_val = (
            None
            if step.error_rate_pct == 0 and "error_rate_pct" in estimated
            else step.error_rate_pct
        )

        # Only mark with * if the LLM actually generated non-zero values for estimated fields,
        # not when it just defaulted them to 0 (i.e., the user didn't provide the data at all)
        estimated_field_values = {
            "average_time_hours": step.average_time_hours,
            "cost_per_instance": step.cost_per_instance,
            "error_rate_pct": step.error_rate_pct,
        }
        step_has_estimates = any(
            estimated_field_values.get(f, 0) != 0 for f in estimated
        )

        if step_has_estimates:
            has_estimates = True

        # Build step name label — append markers for estimated values and notes
        step_label = step.step_name
        if step_has_estimates:
            step_label += " *"
        if notes.strip():
            step_label += " ⓘ"
            step_notes.append((step_numbers[idx], step.step_name, notes.strip()))

        rows.append(
            {
                "Step #": step_numbers[idx],
                "Step Name": step_label,
                "Time (hrs)": time_val,
                "Cost ($)": cost_val,
                "Problem Freq.": freq_val,
                "People": step.resources_needed,
                "Depends On": ", ".join(step.depends_on) if step.depends_on else "",
            }
        )

    df = pd.DataFrame(rows)
    is_editable = message.is_editable

    edited_df = st.data_editor(
        df,
        width="stretch",
        hide_index=True,
        disabled=not is_editable,
        key=f"data_card_{message.timestamp.timestamp()}",
        column_config={
            "Step #": st.column_config.TextColumn(
                "Step #",
                help="Step number. (OR) = alternative paths, (AND) = simultaneous, (if) = conditional, (↩) = rework loop",
                width="small",
                disabled=True,
            ),
            "Step Name": st.column_config.TextColumn(
                "Step Name",
                help="Process step name",
                width="medium",
            ),
            "Time (hrs)": st.column_config.NumberColumn(
                "Time (hrs)",
                help="Average time per execution in hours. Enter a decimal (e.g. 1.5 = 1h 30m)",
                min_value=0.0,
                format="%.2f h",
            ),
            "Cost ($)": st.column_config.NumberColumn(
                "Cost ($)",
                help="Total cost per execution — labor, computing, materials, etc.",
                min_value=0.0,
                format="$%.2f",
            ),
            "Problem Freq.": st.column_config.NumberColumn(
                "Problem Freq.",
                help="How often this step needs rework or causes delays (0-100%)",
                min_value=0.0,
                max_value=100.0,
                format="%.1f%%",
            ),
            "People": st.column_config.NumberColumn(
                "People",
                help="Number of people involved. 0 = fully automated, no human touch.",
                min_value=0,
                step=1,
            ),
            "Depends On": st.column_config.TextColumn(
                "Depends On",
                help="Steps that must complete before this one (comma-separated)",
                width="medium",
            ),
        },
    )

    # Handle edits — update process data in session state
    if is_editable and not df.equals(edited_df):
        _apply_table_edits(process_data, edited_df, message)

    if is_editable:
        st.caption(
            "You can edit values directly in the table, or describe changes in the chat."
        )

    # Show estimated values warning
    if has_estimates:
        st.markdown(
            f"""
            <div style="
                font-size: 0.8rem;
                color: {COLORS['text_muted']};
                margin-top: 0.5rem;
                padding: 0.5rem 0.75rem;
                background: {COLORS['warning']}10;
                border-left: 2px solid {COLORS['warning']};
                border-radius: 0 0.25rem 0.25rem 0;
            ">
                <strong>* AI-estimated values.</strong>
                Steps marked with * contain values generated by AI based on
                typical industry patterns. These estimates provide guidance only
                &mdash; review and adjust them before analysis, as unverified
                estimates can lead to misleading results.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Show AI notes for steps with assumptions, conditionals, or loops
    if step_notes:
        with st.expander(f"ⓘ AI notes on {len(step_notes)} step(s)", expanded=False):
            st.caption(
                "Assumptions, conditional logic, or ambiguities flagged by the AI during extraction."
            )
            for step_num, step_name, note in step_notes:
                st.markdown(f"**{step_num} — {step_name}**")
                st.markdown(f"{note}")

    # Show totals (use message.data which may have been updated by edits)
    current_data: ProcessData = message.data
    col1, col2 = st.columns(2)
    with col1:
        total_fmt = format_hours(current_data.total_time_hours) or "0h"
        st.metric("Total Time", total_fmt)
    with col2:
        st.metric("Total Cost", f"${current_data.total_cost:.2f}")

    # Show draft analysis preview (Task 3.3)
    if message.draft_insight:
        _render_draft_analysis(message.draft_insight)

    # Show targeted follow-up suggestions (skip first "Does this look correct?")
    extra_questions = (message.suggested_questions or [])[1:]
    if extra_questions:
        st.markdown(
            f"""<div style="
                font-size: 0.8rem;
                color: {COLORS['text_muted']};
                margin-top: 0.75rem;
                margin-bottom: 0.5rem;
            ">You could also tell me:</div>""",
            unsafe_allow_html=True,
        )
        chips_html = "".join(
            f"""<span style="
                display: inline-block;
                padding: 0.375rem 0.75rem;
                background: {COLORS['background_alt']};
                border: 1px solid {COLORS['border']};
                border-radius: 1rem;
                font-size: 0.8rem;
                margin: 0.25rem 0.25rem 0.25rem 0;
                color: {COLORS['text']};
            ">{q}</span>"""
            for q in extra_questions
        )
        st.markdown(chips_html, unsafe_allow_html=True)


def _apply_table_edits(
    original: ProcessData,
    edited_df: "pd.DataFrame",
    message: ChatMessage,
) -> None:
    """Apply table edits to process data and update session state."""
    try:
        new_steps = []
        for _, row in edited_df.iterrows():
            step_name = str(row["Step Name"]).strip()
            if not step_name:
                continue

            # Strip display markers appended for readability (added in order: " *" then " ⓘ")
            clean_name = step_name.removesuffix(" ⓘ").removesuffix(" *")

            depends_on_str = str(row.get("Depends On", "") or "")
            depends_on = [s.strip() for s in depends_on_str.split(",") if s.strip()]

            # Find original step to preserve estimated_fields
            orig_step = next(
                (s for s in original.steps if s.step_name == clean_name), None
            )

            time_val = row.get("Time (hrs)", 0)
            cost_val = row.get("Cost ($)", 0)
            error_val = row.get("Problem Freq.", 0)
            resources_val = row.get("People", 0)

            new_time = 0.0 if pd.isna(time_val) else float(time_val)
            new_cost = 0.0 if pd.isna(cost_val) else float(cost_val)
            new_error = 0.0 if pd.isna(error_val) else float(error_val)

            # Remove fields from estimated_fields if the user changed the value
            # (user-edited values are no longer AI-estimated)
            estimated = (
                list(getattr(orig_step, "estimated_fields", [])) if orig_step else []
            )
            if orig_step and estimated:
                field_map = {
                    "average_time_hours": (new_time, orig_step.average_time_hours),
                    "cost_per_instance": (new_cost, orig_step.cost_per_instance),
                    "error_rate_pct": (new_error, orig_step.error_rate_pct),
                }
                for field, (new_v, old_v) in field_map.items():
                    if field in estimated and new_v != old_v:
                        estimated.remove(field)

            new_steps.append(
                ProcessStep(
                    step_name=clean_name,
                    average_time_hours=new_time,
                    cost_per_instance=new_cost,
                    error_rate_pct=new_error,
                    resources_needed=0
                    if pd.isna(resources_val)
                    else int(resources_val),
                    depends_on=depends_on,
                    estimated_fields=estimated,
                    group_id=getattr(orig_step, "group_id", None)
                    if orig_step
                    else None,
                    group_type=getattr(orig_step, "group_type", None)
                    if orig_step
                    else None,
                )
            )

        if new_steps:
            updated = ProcessData(
                name=original.name,
                description=original.description,
                steps=new_steps,
            )
            set_process_data(updated)
            message.data = updated  # Update message for correct totals
            logger.debug(
                "Process data updated via table edit (%d steps)", len(new_steps)
            )
    except Exception as e:
        logger.warning("Failed to apply table edits: %s", e)


def _render_draft_analysis(insight: AnalysisInsight) -> None:
    """Render a collapsible draft analysis preview below the data card.

    Gives users immediate value by showing what analysis would look like
    with current data. Labeled clearly as a draft.
    """
    st.markdown("")  # Spacing

    with st.expander("Draft Analysis (based on current data)", expanded=False):
        st.markdown(
            f"""<div style="
                padding: 0.5rem 0;
                font-size: 0.85rem;
                color: {COLORS['text_muted']};
                border-bottom: 1px solid {COLORS['border']};
                margin-bottom: 0.75rem;
            ">This is a preview based on available data. Refine the data above for better results.</div>""",
            unsafe_allow_html=True,
        )

        # Process summary
        if insight.process_summary:
            st.markdown(insight.process_summary)

        # Issues (compact)
        if insight.issues:
            st.markdown(f"**Issues found ({len(insight.issues)}):**")
            for issue in insight.issues:
                severity_color = get_severity_color(issue.severity)
                desc_preview = issue.description[:150]
                if len(issue.description) > 150:
                    desc_preview += "..."
                st.markdown(
                    f"""<div style="
                        border-left: 3px solid {severity_color};
                        padding: 0.5rem 0.75rem;
                        margin-bottom: 0.5rem;
                        background: {COLORS['background_alt']};
                        border-radius: 0 0.25rem 0.25rem 0;
                        font-size: 0.9rem;
                    ">
                        <strong>{issue.title}</strong>
                        <span style="
                            font-size: 0.75rem;
                            color: {severity_color};
                            margin-left: 0.5rem;
                        ">{issue.severity}</span>
                        <br/><span style="color: {COLORS['text_muted']};">{desc_preview}</span>
                    </div>""",
                    unsafe_allow_html=True,
                )

        # Recommendations (compact)
        if insight.recommendations:
            st.markdown(f"**Recommendations ({len(insight.recommendations)}):**")
            for rec in insight.recommendations:
                st.markdown(f"- **{rec.title}** -- {rec.expected_benefit}")

        # Not-problems (one line each)
        if insight.not_problems:
            st.markdown("**Core value (not issues):**")
            for np_item in insight.not_problems:
                st.markdown(f"- {np_item.step_name}: {np_item.why_not_a_problem}")

        # Caveats
        if insight.confidence_notes:
            st.caption(insight.confidence_notes)


def _render_analysis_results(message: ChatMessage) -> None:
    """Render analysis results message in chat.

    Shows the summary text. Full results are rendered separately
    by results_display.render_results() in views.py.
    """
    st.markdown(message.content)


def _render_clarification(message: ChatMessage) -> None:
    """Render clarification questions."""
    st.markdown(message.content)

    if not message.questions:
        return

    # Questions are rendered but handled by the parent component
    # This just displays them; actual input handling is in the main app
    for q in message.questions:
        st.markdown(
            f"""
            <div style="
                padding: 0.5rem 0.75rem;
                background: {COLORS['background_alt']};
                border: 1px solid {COLORS['border']};
                border-radius: 0.375rem;
                margin-bottom: 0.5rem;
            ">
                {q.get('text', q.get('question', ''))}
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_message(message: ChatMessage) -> None:
    """Render a single chat message based on its type."""
    # System messages render outside the chat bubble
    if message.role == MessageRole.SYSTEM:
        if message.type == MessageType.STATUS:
            _render_status_message(message)
        elif message.type == MessageType.ERROR:
            _render_error_message(message)
        return

    # User and agent messages use Streamlit's chat_message
    with st.chat_message(message.role.value):
        if message.type == MessageType.TEXT:
            _render_text_message(message)
        elif message.type == MessageType.FILE:
            _render_file_message(message)
        elif message.type == MessageType.DATA_CARD:
            _render_data_card(message)
        elif message.type == MessageType.ANALYSIS:
            _render_analysis_results(message)
        elif message.type == MessageType.CLARIFICATION:
            _render_clarification(message)
        else:
            # Fallback to text
            _render_text_message(message)


def render_chat_history(messages: list[ChatMessage]) -> None:
    """Render the full chat history."""
    for message in messages:
        render_message(message)


def render_chat_input(
    placeholder: str = "Describe your process or ask a question...",
    key: str = "chat_input",
) -> str | None:
    """Render the chat input box and return user input."""
    result = st.chat_input(placeholder, key=key)
    return str(result) if result is not None else None


def render_file_uploader(
    label: str = "Or drop a file here",
    accepted_types: list[str] | None = None,
    key: str = "file_upload",
) -> Any:
    """Render a file uploader.

    Args:
        label: Label text for the uploader.
        accepted_types: List of accepted file extensions.
        key: Unique key for the widget.

    Returns:
        Uploaded file object or None.
    """
    if accepted_types is None:
        accepted_types = ["csv", "xlsx", "xls"]

    return st.file_uploader(
        label,
        type=accepted_types,
        key=key,
        label_visibility="collapsed",
    )


def render_typing_indicator() -> None:
    """Render a typing/processing indicator."""
    st.markdown(
        f"""
        <div style="
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: {COLORS['text_muted']};
            font-size: 0.875rem;
            padding: 0.5rem 0;
        ">
            <div style="
                width: 0.5rem;
                height: 0.5rem;
                background: {COLORS['primary']};
                border-radius: 50%;
                animation: pulse 1.5s infinite;
            "></div>
            Processing...
        </div>
        <style>
            @keyframes pulse {{
                0%, 100% {{ opacity: 0.4; }}
                50% {{ opacity: 1; }}
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_welcome_message() -> None:
    """Render the initial welcome message with a prominent capability overview."""
    # Prominent intro block — shown once on the empty welcome screen
    st.markdown(
        f"""
        <div style="
            background: {COLORS['background_alt']};
            border: 1px solid {COLORS['border']};
            border-radius: 0.5rem;
            padding: 1.5rem 2rem;
            margin-bottom: 1.5rem;
        ">
            <p style="
                font-size: 1rem;
                color: {COLORS['text']};
                margin: 0 0 1rem 0;
                font-weight: 500;
            ">What can ProcessIQ do for you?</p>
            <div style="display: flex; gap: 1.5rem; flex-wrap: wrap;">
                <div style="flex: 1; min-width: 160px;">
                    <p style="font-weight: 600; color: {COLORS['text']}; margin: 0 0 0.25rem 0;">
                        Find bottlenecks
                    </p>
                    <p style="color: {COLORS['text_muted']}; margin: 0; font-size: 0.875rem;">
                        Identify which steps slow down or cost the most across your workflow.
                    </p>
                </div>
                <div style="flex: 1; min-width: 160px;">
                    <p style="font-weight: 600; color: {COLORS['text']}; margin: 0 0 0.25rem 0;">
                        Estimate ROI
                    </p>
                    <p style="color: {COLORS['text_muted']}; margin: 0; font-size: 0.875rem;">
                        See projected time and cost savings before committing to any change.
                    </p>
                </div>
                <div style="flex: 1; min-width: 160px;">
                    <p style="font-weight: 600; color: {COLORS['text']}; margin: 0 0 0.25rem 0;">
                        Actionable recommendations
                    </p>
                    <p style="color: {COLORS['text_muted']}; margin: 0; font-size: 0.875rem;">
                        Prioritized suggestions that respect your budget, timeline, and constraints.
                    </p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Chat bubble — the actual conversation starter
    with st.chat_message("assistant"):
        st.markdown(
            "Tell me about a process you'd like to improve, or drop a file describing it."
        )


def render_confirm_buttons(
    on_confirm: str = "confirm_data",
    on_estimate: str = "estimate_missing",
    show_estimate: bool = False,
    disable_confirm: bool = False,
) -> tuple[bool, bool]:
    """Render confirm/estimate buttons for data review.

    Args:
        on_confirm: Key for confirm button.
        on_estimate: Key for estimate button.
        show_estimate: Whether to show the "Estimate Missing" button.
        disable_confirm: Whether to disable the confirm button (e.g., insufficient data).

    Returns:
        Tuple of (confirmed, wants_estimate).
    """
    estimate_clicked = False

    if show_estimate:
        _, col_est, col_confirm = st.columns([2, 1, 1])
        with col_est:
            estimate_clicked = st.button(
                "Estimate Missing",
                key=on_estimate,
                width="stretch",
                help="Let the AI fill in missing values (costs, error rates, timing) "
                "based on typical industry patterns. Estimated values are marked "
                "with * and should be reviewed before analysis.",
            )
    else:
        _, col_confirm = st.columns([3, 1])

    with col_confirm:
        confirm_clicked = st.button(
            "Confirm & Analyze",
            key=on_confirm,
            type="primary",
            width="stretch",
            disabled=disable_confirm,
            help="Add timing data to at least some steps before analyzing"
            if disable_confirm
            else None,
        )

    return confirm_clicked, estimate_clicked
