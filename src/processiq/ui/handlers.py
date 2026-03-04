"""Input handlers for ProcessIQ UI.

Contains all logic for handling user inputs: text, file uploads, button clicks.
"""

import logging
import re
from typing import Any

from processiq.agent.interface import (
    AgentResponse,
    analyze_process,
    extract_from_file,
    extract_from_text,
)
from processiq.models.process import ProcessData
from processiq.ui.components import (
    create_agent_message,
    create_analysis_message,
    create_data_card_message,
    create_error_message,
    create_file_message,
    create_status_message,
    create_user_message,
)
from processiq.ui.state import (
    ChatState,
    add_clarification_context,
    add_message,
    clear_clarification_context,
    clear_input_pending,
    get_analysis_mode,
    get_business_profile,
    get_chat_state,
    get_clarification_context,
    get_constraints,
    get_llm_provider,
    get_max_cycles_override,
    get_messages,
    get_or_create_thread_id,
    get_pending_input,
    get_process_data,
    get_recommendation_feedback,
    get_user_id,
    is_analysis_pending,
    is_file_already_processed,
    is_input_pending,
    set_analysis_insight,
    set_analysis_pending,
    set_chat_state,
    set_confidence,
    set_constraints,
    set_input_pending,
    set_last_uploaded_file,
    set_process_data,
    set_thread_id,
)

logger = logging.getLogger(__name__)


def handle_user_input(user_input: str) -> None:
    """Handle text input from user.

    For states that require LLM processing (WELCOME, GATHERING), this function
    defers the actual processing to the next render cycle. This allows the UI
    to show the user's message immediately with a progress indicator.
    """
    if not user_input.strip():
        return

    # Add user message immediately (will be visible after rerun)
    add_message(create_user_message(user_input))

    current_state = get_chat_state()

    if current_state == ChatState.WELCOME:
        # First message - defer extraction to show user message first
        set_chat_state(ChatState.GATHERING)
        set_input_pending(user_input, ChatState.GATHERING)
        # st.rerun() will be called by render_input_area()

    elif current_state == ChatState.GATHERING:
        # Continue gathering - defer to show user message first
        set_input_pending(user_input, ChatState.GATHERING)
        # st.rerun() will be called by render_input_area()

    elif current_state == ChatState.CONFIRMING:
        # User providing feedback on extracted data
        # Check if this needs LLM processing (i.e., not a simple confirm/deny)
        if _needs_llm_for_confirmation(user_input):
            set_input_pending(user_input, ChatState.CONFIRMING)
        else:
            _handle_confirmation_input(user_input)

    elif current_state == ChatState.CLARIFYING:
        # User answering clarification questions
        _handle_clarification_response(user_input)

    elif current_state in (ChatState.RESULTS, ChatState.CONTINUING):
        # Follow-up question or re-analysis request
        set_chat_state(ChatState.CONTINUING)
        _handle_continuing_input(user_input)


def _needs_llm_for_confirmation(user_input: str) -> bool:
    """Check if confirmation input needs LLM processing.

    Simple confirmations (yes/no) don't need LLM.
    Specific changes (e.g., "change X to Y") need LLM to parse and apply.
    """
    lower_input = user_input.lower().strip()

    # Only these EXACT or very short responses are handled without LLM
    # Anything with more substance should go to LLM for proper parsing
    simple_confirmations = [
        "yes",
        "correct",
        "confirm",
        "looks good",
        "analyze",
        "ok",
        "okay",
    ]
    simple_rejections = ["no", "wrong", "nope"]
    simple_additions = [
        "add more",
        "more info",
        "wait",
        "also",
        "i have more",
        "one more",
        "another",
    ]

    # Check for simple confirmation
    if any(
        lower_input == phrase or lower_input == phrase + "."
        for phrase in simple_confirmations
    ):
        return False

    # Check for simple rejection (but only if it's short - longer input needs LLM)
    if len(lower_input) < 20 and any(
        phrase in lower_input for phrase in simple_rejections
    ):
        # Short rejection without specifics
        return False

    # Check for "add more" type phrases
    # Everything else (including "change X to Y") needs LLM
    return not any(phrase in lower_input for phrase in simple_additions)


# File size limits (in bytes)
_FILE_SIZE_WARNING_BYTES = 10 * 1024 * 1024  # 10 MB
_FILE_SIZE_LIMIT_BYTES = 50 * 1024 * 1024  # 50 MB


def handle_file_upload(uploaded_file: Any) -> bool:
    """Handle file upload from user.

    Args:
        uploaded_file: Streamlit UploadedFile object

    Returns:
        True if file was processed, False if skipped (already processed)
    """
    if uploaded_file is None:
        return False

    # Check if this file was already processed (prevents infinite rerun loop)
    file_name = uploaded_file.name
    file_size = uploaded_file.size

    if is_file_already_processed(file_name, file_size):
        logger.debug("File already processed, skipping: %s", file_name)
        return False

    # Check file size limits
    if file_size > _FILE_SIZE_LIMIT_BYTES:
        add_message(create_file_message(file_name))
        add_message(
            create_error_message(
                f"File is too large ({file_size / (1024*1024):.1f} MB). "
                f"Maximum file size is {_FILE_SIZE_LIMIT_BYTES / (1024*1024):.0f} MB. "
                "Please upload a smaller file or describe your process in text."
            )
        )
        set_last_uploaded_file(file_name, file_size)  # Prevent re-processing
        return True  # Return True to trigger rerun and show error

    if file_size > _FILE_SIZE_WARNING_BYTES:
        add_message(
            create_status_message(
                f"Large file detected ({file_size / (1024*1024):.1f} MB). Processing may be slower."
            )
        )

    # Mark file as processed BEFORE processing (prevents loop even if processing fails)
    set_last_uploaded_file(file_name, file_size)

    # Add file notification
    add_message(create_file_message(file_name))

    # Add status message
    add_message(create_status_message(f"Processing {file_name}..."))

    # Extract from file (pass existing data for smart name matching)
    existing = get_process_data()
    response = extract_from_file(
        file_bytes=uploaded_file.getvalue(),
        filename=file_name,
        analysis_mode=get_analysis_mode(),
        constraints=get_constraints(),
        profile=get_business_profile(),
        llm_provider=get_llm_provider(),
        current_process_data=existing,
    )

    # Merge with existing data if present (file complements rather than replaces)
    if existing and response.has_data and response.process_data is not None:
        merged = existing.merge_with(response.process_data)
        response.process_data = merged
        new_count = len(response.process_data.steps) - len(existing.steps)
        updated_count = len(existing.steps)
        parts = []
        if updated_count:
            parts.append(f"updated {updated_count} existing steps")
        if new_count > 0:
            parts.append(f"added {new_count} new steps")
        merge_desc = " and ".join(parts) if parts else "merged data"
        add_message(
            create_status_message(
                f"Merged {file_name} with existing data: {merge_desc}."
            )
        )

    _handle_extraction_response(response)

    # Clear the file from the uploader widget by incrementing the key counter.
    # This forces Streamlit to create a new widget on the next rerun.
    import streamlit as st

    st.session_state.file_upload_key_counter = (
        st.session_state.get("file_upload_key_counter", 0) + 1
    )

    return True


def handle_confirm_button() -> None:
    """Handle confirm button click."""
    _run_analysis()


def handle_estimate_button() -> None:
    """Handle 'Estimate Missing' button click.

    Calls extract_from_text() with a synthetic message asking the LLM to
    fill in missing values using the existing ESTIMATE path in extraction.j2.
    The current process data is passed as conversation context so the LLM
    knows what values already exist.

    After the LLM returns, a guard ensures that user-provided (non-zero)
    values are never overwritten — only zero/missing fields are updated.
    """
    process_data = get_process_data()
    if not process_data:
        add_message(create_error_message("No process data to estimate from."))
        return

    # Snapshot before estimation for comparison
    def _step_snapshot(steps: list[Any]) -> list[tuple[Any, ...]]:
        return [
            (
                s.step_name,
                s.average_time_hours,
                s.cost_per_instance,
                s.error_rate_pct,
                s.resources_needed,
            )
            for s in steps
        ]

    old_snapshot = _step_snapshot(process_data.steps)

    # Remember which fields already had user-provided values
    original_values: dict[str, dict[str, float]] = {}
    for step in process_data.steps:
        original_values[step.step_name] = {
            "average_time_hours": step.average_time_hours,
            "cost_per_instance": step.cost_per_instance,
            "error_rate_pct": step.error_rate_pct,
        }

    add_message(create_status_message("Estimating missing values..."))

    response = extract_from_text(
        user_message="Please estimate ONLY the missing values (fields that are 0 or blank). "
        "Do NOT change any values that are already filled in. "
        "Fill in missing costs, error rates, and timing with reasonable industry estimates.",
        analysis_mode=get_analysis_mode(),
        current_process_data=process_data,
        ui_messages=get_messages(),
        constraints=get_constraints(),
        profile=get_business_profile(),
        llm_provider=get_llm_provider(),
    )

    # Guard: restore any user-provided values the LLM may have overwritten
    if response.process_data is not None:
        _protect_existing_values(response.process_data, original_values)

    _handle_extraction_response(response)

    # Check if data actually changed
    new_data = get_process_data()
    if new_data and _step_snapshot(new_data.steps) == old_snapshot:
        add_message(
            create_agent_message(
                "All values that can be reliably estimated are already filled in. "
                "You can adjust any values directly in the table, or proceed to analysis."
            )
        )


def _protect_existing_values(
    new_data: ProcessData,
    original_values: dict[str, dict[str, float]],
) -> None:
    """Restore user-provided values the LLM may have changed during estimation.

    Only zero/missing fields should be filled by estimation. If a field had a
    non-zero user value before estimation and the LLM changed it, revert it.
    """
    protected_fields = ("average_time_hours", "cost_per_instance", "error_rate_pct")

    for step in new_data.steps:
        orig = original_values.get(step.step_name)
        if orig is None:
            continue

        for field_name in protected_fields:
            orig_val = orig[field_name]
            if orig_val != 0 and getattr(step, field_name) != orig_val:
                logger.warning(
                    "Estimation changed '%s.%s' from %.2f to %.2f — reverting",
                    step.step_name,
                    field_name,
                    orig_val,
                    getattr(step, field_name),
                )
                setattr(step, field_name, orig_val)


def _process_text_input(text: str) -> None:
    """Process text input through LLM extraction.

    Passes current process data and UI messages to enable:
    - Edit requests like "change step 3 time to 2 hours"
    - Conversational context for better extraction
    """
    add_message(create_status_message("Analyzing your description..."))

    # Get current state for conversation context
    current_process = get_process_data()
    ui_messages = get_messages()

    response = extract_from_text(
        user_message=text,
        analysis_mode=get_analysis_mode(),
        current_process_data=current_process,
        ui_messages=ui_messages,
        constraints=get_constraints(),
        profile=get_business_profile(),
        llm_provider=get_llm_provider(),
    )

    _handle_extraction_response(response)


def _handle_extraction_response(response: AgentResponse) -> None:
    """Handle response from extraction."""
    if response.is_error:
        add_message(create_error_message(response.message))
        return

    if response.has_data and response.process_data is not None:
        # Store extracted data
        set_process_data(response.process_data)
        set_confidence(response.confidence)
        set_thread_id(response.thread_id)

        # Add data card message
        add_message(
            create_data_card_message(
                process_data=response.process_data,
                content=response.message,
                confidence=response.confidence.score if response.confidence else None,
                improvement_suggestions=response.improvement_suggestions,
                suggested_questions=response.suggested_questions,
                draft_insight=response.draft_insight,
            )
        )

        set_chat_state(ChatState.CONFIRMING)
    else:
        # No data extracted - ask for more info
        add_message(create_agent_message(response.message))


def _handle_confirmation_input(user_input: str) -> None:
    """Handle user input during confirmation state.

    This handles ONLY simple keyword responses. Complex inputs like
    "change X to Y" are routed to LLM by _needs_llm_for_confirmation().
    """
    lower_input = user_input.lower().strip()

    # Simple confirmations → run analysis
    simple_confirmations = [
        "yes",
        "correct",
        "confirm",
        "looks good",
        "analyze",
        "ok",
        "okay",
    ]
    if any(
        lower_input == phrase or lower_input == phrase + "."
        for phrase in simple_confirmations
    ):
        _run_analysis()
        return

    # Simple rejections → ask what to change
    simple_rejections = ["no", "wrong", "nope"]
    if len(lower_input) < 20 and any(
        phrase in lower_input for phrase in simple_rejections
    ):
        add_message(
            create_agent_message(
                "What would you like to change? You can describe the changes "
                "(e.g., 'change step 3 time to 2 hours') or edit values directly in the table."
            )
        )
        return

    # "Add more" → go back to GATHERING
    simple_additions = [
        "add more",
        "more info",
        "wait",
        "also",
        "i have more",
        "one more",
        "another",
    ]
    if any(phrase in lower_input for phrase in simple_additions):
        set_chat_state(ChatState.GATHERING)
        add_message(
            create_agent_message("What else would you like to add to this process?")
        )
        return

    # Everything else → treat as additional context or edit request
    # This path is hit when _needs_llm_for_confirmation returned False
    # but input didn't match above patterns (shouldn't happen often)
    _process_text_input(user_input)


def _handle_clarification_response(user_input: str) -> None:
    """Handle user response to clarification questions.

    The user is answering questions the agent asked during analysis.
    Store the response as context and re-run analysis.
    """
    # Store the clarification response
    add_clarification_context(user_input)

    add_message(
        create_status_message("Thanks, re-running analysis with your clarification...")
    )

    # Re-run analysis with the clarification context
    _run_analysis()


def _handle_continuing_input(user_input: str) -> None:
    """Handle user input in CONTINUING state (after results shown).

    Re-analyze triggers (explicit keywords) → re-run analysis with current data.
    Everything else → route to extraction LLM with current process data as context.
      - If the LLM sees a process change, it returns updated data → CONFIRMING state.
      - If it sees a question, it returns needs_clarification with a reply → stays in CONTINUING.
    """
    from processiq.models import Constraints
    from processiq.models.constraints import Priority

    lower_input = user_input.lower()

    # Check for re-analysis requests (explicit triggers only)
    reanalyze_triggers = [
        "re-analyze",
        "reanalyze",
        "try again",
        "analyze again",
        "run again",
    ]
    if any(trigger in lower_input for trigger in reanalyze_triggers):
        # Try to parse constraint modifications
        constraints = get_constraints() or Constraints()
        modified = False

        # Look for budget constraints
        budget_match = re.search(
            r"\$?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:budget|limit)?", user_input
        )
        if budget_match:
            budget_str = budget_match.group(1).replace(",", "")
            try:
                constraints.budget_limit = float(budget_str)
                modified = True
            except ValueError:
                pass

        # Look for hiring constraints
        if any(
            phrase in lower_input
            for phrase in ["can't hire", "cannot hire", "no hiring", "without hiring"]
        ):
            constraints.cannot_hire = True
            modified = True
        elif any(
            phrase in lower_input
            for phrase in ["can hire", "with hiring", "allow hiring"]
        ):
            constraints.cannot_hire = False
            modified = True

        # Look for priority changes
        if (
            "cost" in lower_input and "priority" in lower_input
        ) or "focus on cost" in lower_input:
            constraints.priority = Priority.COST_REDUCTION
            modified = True
        elif (
            "time" in lower_input and "priority" in lower_input
        ) or "focus on time" in lower_input:
            constraints.priority = Priority.TIME_REDUCTION
            modified = True
        elif (
            "quality" in lower_input and "priority" in lower_input
        ) or "focus on quality" in lower_input:
            constraints.priority = Priority.QUALITY_IMPROVEMENT
            modified = True

        if modified:
            set_constraints(constraints)

        # Always re-run: sidebar constraints, business profile, and
        # recommendation feedback are already in session state.
        add_message(
            create_status_message(
                "Re-running analysis with current constraints and feedback..."
            )
        )
        _run_analysis()
    else:
        # Route to extraction LLM with current process data as context.
        # The extraction prompt decides: process change → returns data (→ CONFIRMING),
        # question/conversation → returns needs_clarification (→ chat reply, stays CONTINUING).
        _process_text_input(user_input)


def _run_analysis() -> None:
    """Trigger analysis on confirmed data.

    This sets the state to ANALYZING and flags that analysis should run
    on the next render cycle. This allows the UI to show the ANALYZING
    state before blocking on the actual analysis.
    """
    process_data = get_process_data()
    if not process_data:
        add_message(create_error_message("No process data to analyze."))
        return

    set_chat_state(ChatState.ANALYZING)
    add_message(create_status_message("Running analysis..."))
    set_analysis_pending(True)


def execute_pending_input() -> bool:
    """Execute deferred input processing.

    Called from views.py during render cycle. Returns True if processing
    was executed and UI should rerun, False otherwise.
    """
    if not is_input_pending():
        return False

    text, state = get_pending_input()
    if not text:
        clear_input_pending()
        return False

    # Clear flag first to prevent re-triggering
    clear_input_pending()

    logger.debug("Executing pending input for state: %s", state)

    if state == ChatState.GATHERING:
        _process_text_input(text)
    elif state == ChatState.CONFIRMING:
        # Additional context during confirmation - treat as more info
        _process_text_input(text)
    else:
        logger.warning("Unexpected pending input state: %s", state)
        return False

    return True


def execute_pending_analysis() -> bool:
    """Execute analysis if one is pending.

    Called from views.py during render cycle. Returns True if analysis
    was executed and UI should rerun, False otherwise.
    """
    from processiq.models import BusinessProfile

    if not is_analysis_pending():
        return False

    # Clear flag first to prevent re-triggering
    set_analysis_pending(False)

    process_data = get_process_data()
    if not process_data:
        add_message(create_error_message("No process data to analyze."))
        set_chat_state(ChatState.CONFIRMING)
        return True

    # Get or create business profile, including any clarification context
    profile = get_business_profile()
    clarification_context = get_clarification_context()

    if clarification_context:
        # Add clarification context to the profile notes
        if profile:
            # Create a copy with updated notes
            profile_dict = profile.model_dump()
            existing_notes = profile_dict.get("notes", "")
            if existing_notes:
                profile_dict["notes"] = (
                    f"{existing_notes}\n\nUser clarification:\n{clarification_context}"
                )
            else:
                profile_dict["notes"] = f"User clarification:\n{clarification_context}"
            profile = BusinessProfile(**profile_dict)
        else:
            # Create minimal profile just for the clarification
            from processiq.models.memory import CompanySize, Industry

            profile = BusinessProfile(
                industry=Industry.OTHER,
                company_size=CompanySize.SMALL,
                notes=f"User clarification:\n{clarification_context}",
            )

    # Run analysis with user_id and thread_id for persistence
    thread_id = get_or_create_thread_id()
    response = analyze_process(
        process=process_data,
        constraints=get_constraints(),
        profile=profile,
        thread_id=thread_id,
        user_id=get_user_id(),
        analysis_mode=get_analysis_mode(),
        llm_provider=get_llm_provider(),
        feedback_history=get_recommendation_feedback(),
        max_cycles_override=get_max_cycles_override(),
    )

    # Store thread_id from response if updated
    if response.thread_id:
        set_thread_id(response.thread_id)

    if response.is_error:
        add_message(create_error_message(response.message))
        set_chat_state(ChatState.CONFIRMING)
        return True

    if response.needs_input:
        # Agent needs clarification
        set_chat_state(ChatState.CLARIFYING)
        add_message(create_agent_message(response.message))
        return True

    if response.has_analysis:
        # Store LLM-based insight
        if response.analysis_insight is not None:
            set_analysis_insight(response.analysis_insight)

        add_message(
            create_analysis_message(
                analysis_insight=response.analysis_insight,
                content=response.message,
            )
        )
        set_chat_state(ChatState.RESULTS)
        # Clear clarification context after successful analysis
        clear_clarification_context()
    else:
        add_message(create_error_message("Analysis produced no results."))
        set_chat_state(ChatState.CONFIRMING)

    return True
