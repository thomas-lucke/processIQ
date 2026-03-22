"""Context building utilities for LLM calls.

This module bridges UI messages and process data to LLM context.
It enables conversational edits like "change step 3 time to 2 hours"
by providing the LLM with current state and recent conversation history.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from processiq.models import ProcessData

logger = logging.getLogger(__name__)

# Limits to prevent token overflow
MAX_TABLE_ROWS = 50
MAX_MESSAGE_CHARS = 4000
MAX_HISTORY_MESSAGES = 3
MIN_SUBSTANTIVE_LENGTH = 10


def serialize_process_data(process_data: ProcessData) -> str:
    """Serialize ProcessData to a compact text format for LLM context.

    Uses a simple table format that's easy for the LLM to parse and reference.
    Limits output to MAX_TABLE_ROWS to prevent token overflow.

    Args:
        process_data: The current process data to serialize.

    Returns:
        Compact text representation of the process data.

    Example output:
        Process: Invoice Approval
        | # | Step | Time (hrs) | Cost ($) | Error % | Resources | Depends On |
        |---|------|------------|----------|---------|-----------|------------|
        | 1 | Submit invoice | 0.5 | 25.00 | 2.0 | 1 | - |
        | 2 | Manager review | 2.0 | 100.00 | 5.0 | 1 | Submit invoice |
    """
    if not process_data or not process_data.steps:
        return ""

    lines = []

    # Process name
    if process_data.name:
        lines.append(f"Process: {process_data.name}")

    # Table header
    lines.append(
        "| # | Step | Time (hrs) | Cost ($) | Error % | People | Depends On | Group |"
    )
    lines.append(
        "|---|------|------------|----------|---------|--------|------------|-------|"
    )

    # Table rows (limited to MAX_TABLE_ROWS)
    steps_to_show = process_data.steps[:MAX_TABLE_ROWS]
    for i, step in enumerate(steps_to_show, 1):
        time_str = f"{step.average_time_hours:.1f}" if step.average_time_hours else "-"
        cost_str = f"{step.cost_per_instance:.2f}" if step.cost_per_instance else "-"
        error_str = f"{step.error_rate_pct:.1f}" if step.error_rate_pct else "-"
        resources_str = str(step.resources_needed) if step.resources_needed else "-"
        deps_str = ", ".join(step.depends_on) if step.depends_on else "-"
        group_id = getattr(step, "group_id", None)
        group_type = getattr(step, "group_type", None)
        group_str = f"{group_id} ({group_type})" if group_id and group_type else "-"

        lines.append(
            f"| {i} | {step.step_name} | {time_str} | {cost_str} | {error_str} | {resources_str} | {deps_str} | {group_str} |"
        )

    if len(process_data.steps) > MAX_TABLE_ROWS:
        lines.append(
            f"| ... | ({len(process_data.steps) - MAX_TABLE_ROWS} more steps) | | | | | | |"
        )

    # Totals
    lines.append("")
    lines.append(f"Total time: {process_data.total_time_hours:.1f} hours")
    lines.append(f"Total cost: ${process_data.total_cost:.2f}")

    return "\n".join(lines)


def filter_substantive_messages(messages: list[Any]) -> list[Any]:
    """Filter messages to keep only substantive user messages.

    Filters out:
    - Non-user messages (agent, system)
    - Status messages
    - Very short messages (< MIN_SUBSTANTIVE_LENGTH chars)
    - File upload notifications

    Args:
        messages: List of ChatMessage objects from conversation history.

    Returns:
        Filtered list of substantive user messages.
    """
    substantive = []

    for msg in messages:
        # Check if it's a user message
        role = getattr(msg, "role", None)
        if role is None:
            continue

        # Convert role to string if it's an enum
        role_str = role.value if hasattr(role, "value") else str(role)
        if role_str != "user":
            continue

        # Check message type - skip file uploads and status messages
        msg_type = getattr(msg, "type", None)
        if msg_type:
            type_str = msg_type.value if hasattr(msg_type, "value") else str(msg_type)
            if type_str in ("file", "status"):
                continue

        # Check content length
        content = getattr(msg, "content", "")
        if len(content.strip()) < MIN_SUBSTANTIVE_LENGTH:
            continue

        substantive.append(msg)

    return substantive


def build_conversation_context(
    process_data: ProcessData | None,
    ui_messages: list[Any],
    max_messages: int = MAX_HISTORY_MESSAGES,
) -> str:
    """Build a context string for LLM calls from current state and history.

    Combines:
    1. Current ProcessData (if any) in a compact table format
    2. Recent substantive user messages (for edit context)

    Args:
        process_data: Current ProcessData being edited (optional).
        ui_messages: List of ChatMessage objects from conversation history.
        max_messages: Maximum number of recent messages to include.

    Returns:
        Context string to include in LLM prompts.
        Empty string if no relevant context exists.
    """
    parts = []

    # Add process data context
    if process_data and process_data.steps:
        data_context = serialize_process_data(process_data)
        if data_context:
            parts.append("## Current Process Data\n")
            parts.append(data_context)
            parts.append("")

    # Add recent user messages (excluding the current one, which is the user input)
    substantive = filter_substantive_messages(ui_messages)
    if substantive:
        # Take last N messages (excluding the very last which is the current input)
        recent = substantive[-(max_messages + 1) : -1] if len(substantive) > 1 else []

        if recent:
            parts.append("## Recent Conversation\n")
            for msg in recent:
                content = getattr(msg, "content", "")
                # Truncate very long messages
                truncated = content[:MAX_MESSAGE_CHARS]
                if len(content) > MAX_MESSAGE_CHARS:
                    truncated += "..."
                parts.append(f"User: {truncated}")
            parts.append("")

    if not parts:
        return ""

    return "\n".join(parts)
