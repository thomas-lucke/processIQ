"""Process input component for ProcessIQ UI.

Provides multiple ways to input process data:
1. Form-based step builder (add/remove steps)
2. File upload (CSV/Excel for structured data; PDF/DOCX/PPTX/etc. for unstructured)
3. Sample dataset for demos
"""

import logging
from typing import Any

import streamlit as st

from processiq.exceptions import ExtractionError, ValidationError
from processiq.ingestion import (
    load_csv_from_bytes,
    load_excel_from_bytes,
    normalize_parsed_document,
    parse_from_stream,
)
from processiq.models import ProcessData, ProcessStep
from processiq.ui.state import (
    add_draft_step,
    get_draft_steps,
    remove_draft_step,
    set_draft_steps,
    set_process_data,
)

logger = logging.getLogger(__name__)


def _create_sample_process() -> ProcessData:
    """Create sample process data for demo purposes."""
    return ProcessData(
        name="Expense Approval Process",
        description="Standard expense reimbursement workflow",
        steps=[
            ProcessStep(
                step_name="Submit Request",
                average_time_hours=0.5,
                resources_needed=1,
                error_rate_pct=5.0,
                cost_per_instance=37.50,
            ),
            ProcessStep(
                step_name="Manager Review",
                average_time_hours=1.2,
                resources_needed=1,
                error_rate_pct=8.0,
                cost_per_instance=90.00,
                depends_on=["Submit Request"],
            ),
            ProcessStep(
                step_name="Finance Verification",
                average_time_hours=0.8,
                resources_needed=1,
                error_rate_pct=3.0,
                cost_per_instance=60.00,
                depends_on=["Manager Review"],
            ),
            ProcessStep(
                step_name="Data Entry",
                average_time_hours=1.5,
                resources_needed=1,
                error_rate_pct=15.0,
                cost_per_instance=30.00,
                depends_on=["Finance Verification"],
            ),
            ProcessStep(
                step_name="Payment Processing",
                average_time_hours=0.25,
                resources_needed=1,
                error_rate_pct=2.0,
                cost_per_instance=18.75,
                depends_on=["Data Entry"],
            ),
        ],
    )


def _render_step_form(
    index: int, step_data: dict[str, Any], existing_steps: list[str]
) -> dict[str, Any] | None:
    """Render form fields for a single process step.

    Args:
        index: Step index (0-based).
        step_data: Current step data.
        existing_steps: Names of steps defined before this one (for dependencies).

    Returns:
        Updated step data, or None if step should be removed.
    """
    col1, col2 = st.columns([4, 1])

    with col1:
        st.markdown(f"**Step {index + 1}**")

    with col2:
        if st.button("Remove", key=f"remove_step_{index}", type="secondary"):
            return None

    # Step name
    step_name = st.text_input(
        "Step Name",
        value=step_data.get("step_name", ""),
        key=f"step_name_{index}",
        placeholder="e.g., Manager Review",
    )

    # Metrics in columns
    col1, col2, col3 = st.columns(3)

    with col1:
        time_hours = st.number_input(
            "Time (hours)",
            min_value=0.0,
            max_value=1000.0,
            value=float(step_data.get("average_time_hours", 1.0)),
            step=0.25,
            key=f"time_{index}",
            help="Average time to complete this step",
        )

    with col2:
        resources = st.number_input(
            "Resources",
            min_value=1,
            max_value=100,
            value=int(step_data.get("resources_needed", 1)),
            key=f"resources_{index}",
            help="Number of people/systems involved",
        )

    with col3:
        error_rate = st.number_input(
            "Problem Freq. (%)",
            min_value=0.0,
            max_value=100.0,
            value=float(step_data.get("error_rate_pct", 0.0)),
            step=1.0,
            key=f"error_{index}",
            help="How often does this step hit issues, need rework, or cause delays? (0-100%)",
        )

    col1, col2 = st.columns(2)

    with col1:
        cost = st.number_input(
            "Cost per Instance ($)",
            min_value=0.0,
            value=float(step_data.get("cost_per_instance", 0.0)),
            step=10.0,
            key=f"cost_{index}",
            help="Cost in dollars per execution",
        )

    with col2:
        # Dependencies dropdown (multi-select from previous steps)
        current_depends = step_data.get("depends_on", [])
        if isinstance(current_depends, str):
            current_depends = [
                s.strip() for s in current_depends.split(";") if s.strip()
            ]

        depends_on = st.multiselect(
            "Depends On",
            options=existing_steps,
            default=[d for d in current_depends if d in existing_steps],
            key=f"depends_{index}",
            help="Steps that must complete before this one",
        )

    return {
        "step_name": step_name,
        "average_time_hours": time_hours,
        "resources_needed": resources,
        "error_rate_pct": error_rate,
        "cost_per_instance": cost,
        "depends_on": depends_on,
    }


def _validate_draft_steps(
    steps: list[dict[str, Any]],
) -> tuple[ProcessData | None, list[str]]:
    """Validate draft steps and convert to ProcessData.

    Args:
        steps: List of draft step dictionaries.

    Returns:
        Tuple of (ProcessData if valid, list of error messages).
    """
    if not steps:
        return None, ["At least one process step is required."]

    errors = []
    valid_steps = []

    for i, step in enumerate(steps):
        step_name = step.get("step_name", "").strip()
        if not step_name:
            errors.append(f"Step {i + 1}: Name is required.")
            continue

        time_hours = step.get("average_time_hours", 0)
        if time_hours <= 0:
            errors.append(f"Step {i + 1} ({step_name}): Time must be greater than 0.")
            continue

        try:
            # Convert depends_on list to proper format
            depends_on = step.get("depends_on", [])
            if isinstance(depends_on, list):
                depends_on = depends_on  # Already a list
            elif isinstance(depends_on, str):
                depends_on = [s.strip() for s in depends_on.split(";") if s.strip()]

            process_step = ProcessStep(
                step_name=step_name,
                average_time_hours=step.get("average_time_hours", 1.0),
                resources_needed=step.get("resources_needed", 1),
                error_rate_pct=step.get("error_rate_pct", 0.0),
                cost_per_instance=step.get("cost_per_instance", 0.0),
                depends_on=depends_on,
            )
            valid_steps.append(process_step)
        except Exception as e:
            errors.append(f"Step {i + 1} ({step_name}): {e}")

    if not valid_steps:
        return None, errors

    try:
        process_data = ProcessData(
            name=st.session_state.get("process_name", "My Process"),
            description=st.session_state.get("process_description", ""),
            steps=valid_steps,
        )
        return process_data, errors
    except Exception as e:
        errors.append(f"Process validation failed: {e}")
        return None, errors


def render_process_input() -> bool:
    """Render the process input section.

    Returns:
        True if valid process data is available, False otherwise.
    """
    st.markdown("### Process Definition")

    # Process metadata
    col1, col2 = st.columns([2, 1])
    with col1:
        st.text_input(
            "Process Name",
            value=st.session_state.get("process_name", ""),
            key="process_name",
            placeholder="e.g., Expense Approval Process",
        )
    with col2:
        if st.button("Load Sample Data", type="secondary"):
            sample = _create_sample_process()
            st.session_state.process_name = sample.name
            st.session_state.process_description = sample.description
            # Convert to draft steps
            draft_steps = []
            for step in sample.steps:
                draft_steps.append(
                    {
                        "step_name": step.step_name,
                        "average_time_hours": step.average_time_hours,
                        "resources_needed": step.resources_needed,
                        "error_rate_pct": step.error_rate_pct,
                        "cost_per_instance": step.cost_per_instance,
                        "depends_on": step.depends_on,
                    }
                )
            set_draft_steps(draft_steps)
            set_process_data(sample)
            st.rerun()

    st.text_area(
        "Description (optional)",
        value=st.session_state.get("process_description", ""),
        key="process_description",
        placeholder="Brief description of the process",
        height=68,
    )

    st.markdown("---")

    # Input method tabs
    tab_form, tab_upload = st.tabs(["Build Steps", "Upload File"])

    with tab_form:
        _render_form_builder()

    with tab_upload:
        _render_file_upload()

    # Check if we have valid data
    steps = get_draft_steps()
    return steps is not None and len(steps) > 0


def _render_form_builder() -> None:
    """Render the step-by-step form builder."""
    st.markdown(
        "*Add process steps one by one. Estimates are fine - missing values will reduce confidence.*"
    )

    draft_steps = get_draft_steps()

    # Initialize with one empty step if none exist
    if not draft_steps:
        draft_steps = [
            {"step_name": "", "average_time_hours": 1.0, "resources_needed": 1}
        ]
        set_draft_steps(draft_steps)

    # Collect existing step names for dependency dropdowns
    existing_step_names: list[str] = []
    updated_steps = []
    steps_to_remove = []

    for i, step_data in enumerate(draft_steps):
        with st.container():
            result = _render_step_form(i, step_data, existing_step_names)
            if result is None:
                steps_to_remove.append(i)
            else:
                updated_steps.append(result)
                if result.get("step_name"):
                    existing_step_names.append(result["step_name"])

            if i < len(draft_steps) - 1:
                st.markdown("---")

    # Handle removals
    if steps_to_remove:
        for idx in reversed(steps_to_remove):
            remove_draft_step(idx)
        st.rerun()

    # Update state with form values
    set_draft_steps(updated_steps)

    # Add step button
    st.markdown("")
    if st.button("+ Add Step", type="secondary"):
        add_draft_step(
            {
                "step_name": "",
                "average_time_hours": 1.0,
                "resources_needed": 1,
                "error_rate_pct": 0.0,
                "cost_per_instance": 0.0,
                "depends_on": [],
            }
        )
        st.rerun()

    # Validate and update ProcessData
    if updated_steps:
        process_data, errors = _validate_draft_steps(updated_steps)
        if errors:
            for error in errors:
                st.warning(error)
        if process_data:
            set_process_data(process_data)


_STRUCTURED_EXTENSIONS = (".csv", ".xlsx", ".xls")
_DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".doc", ".pptx", ".ppt", ".html", ".htm")
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tiff", ".bmp")
_ALL_UPLOAD_TYPES = [
    "csv",
    "xlsx",
    "xls",
    "pdf",
    "docx",
    "doc",
    "pptx",
    "ppt",
    "html",
    "htm",
    "png",
    "jpg",
    "jpeg",
]


def _render_file_upload() -> None:
    """Render the file upload section.

    Accepts two categories of files:
    - Structured (CSV/Excel): columns are mapped directly to ProcessStep fields.
    - Unstructured (PDF, DOCX, PPTX, images, HTML): parsed with Docling, then
      extracted to process steps via LLM.
    """
    st.markdown(
        "*Upload a file containing your process. "
        "**Structured files** (CSV/Excel): must have columns step_name, average_time_hours, resources_needed, "
        "and optionally error_rate_pct, cost_per_instance, depends_on. "
        "**Unstructured files** (PDF, Word, PowerPoint, images): meeting notes, process descriptions, "
        "diagrams — the AI will extract the steps.*"
    )

    uploaded_file = st.file_uploader(
        "Choose a file",
        type=_ALL_UPLOAD_TYPES,
        key="process_file_upload",
    )

    if uploaded_file is None:
        return

    file_name = uploaded_file.name.lower()
    process_name = (
        st.session_state.get("process_name") or uploaded_file.name.rsplit(".", 1)[0]
    )

    try:
        if file_name.endswith(_STRUCTURED_EXTENSIONS):
            _handle_structured_upload(uploaded_file, file_name, process_name)
        else:
            _handle_document_upload(uploaded_file, process_name)

    except (ExtractionError, ValidationError) as e:
        st.error(
            f"Failed to load file: {e.user_message if hasattr(e, 'user_message') else str(e)}"
        )
        logger.warning("File upload failed: %s", e)
    except Exception as e:
        st.error(f"Unexpected error loading file: {e}")
        logger.exception("Unexpected error in file upload")


def _handle_structured_upload(
    uploaded_file: Any, file_name: str, process_name: str
) -> None:
    """Load a CSV or Excel file directly into ProcessData."""
    file_bytes = uploaded_file.getvalue()

    if file_name.endswith(".csv"):
        process_data = load_csv_from_bytes(file_bytes, process_name=process_name)
    else:
        process_data = load_excel_from_bytes(file_bytes, process_name=process_name)

    _apply_process_data(process_data, uploaded_file.name)


def _handle_document_upload(uploaded_file: Any, process_name: str) -> None:
    """Parse an unstructured document and extract process steps via LLM."""
    with st.spinner(f"Reading {uploaded_file.name}..."):
        parsed = parse_from_stream(uploaded_file, uploaded_file.name)

    if not parsed.success:
        st.error(f"Could not read file: {parsed.error}")
        return

    page_info = f" ({parsed.page_count} pages)" if parsed.page_count else ""
    st.info(
        f"Parsed {uploaded_file.name}{page_info}. "
        f"Extracted {len(parsed.text)} characters across {len(parsed.chunks)} content blocks. "
        "Extracting process steps with AI..."
    )

    with st.spinner("Extracting process steps..."):
        process_data, response = normalize_parsed_document(parsed)

    if response.response_type == "needs_clarification" or process_data is None:
        clarification = response.clarification
        if clarification:
            st.warning(
                f"The document was parsed but the AI needs more context to extract steps.\n\n"
                f"{clarification.message}\n\n"
                "Try describing the process in the chat, or provide the steps manually using "
                "the 'Build Steps' tab."
            )
        else:
            st.warning(
                "The document was parsed but contained insufficient process information. "
                "Try the 'Build Steps' tab to enter steps manually."
            )
        logger.info(
            "Document upload for '%s' requires clarification: %s",
            uploaded_file.name,
            clarification.detected_intent if clarification else "unknown",
        )
        return

    _apply_process_data(process_data, uploaded_file.name)


def _apply_process_data(process_data: ProcessData, source_filename: str) -> None:
    """Store extracted ProcessData into session state and show confirmation."""
    draft_steps = [
        {
            "step_name": step.step_name,
            "average_time_hours": step.average_time_hours,
            "resources_needed": step.resources_needed,
            "error_rate_pct": step.error_rate_pct,
            "cost_per_instance": step.cost_per_instance,
            "depends_on": step.depends_on,
        }
        for step in process_data.steps
    ]

    set_draft_steps(draft_steps)
    set_process_data(process_data)
    st.session_state.process_name = process_data.name

    st.success(f"Loaded {len(process_data.steps)} steps from {source_filename}")
    logger.info(
        "Loaded %d steps from uploaded file: %s",
        len(process_data.steps),
        source_filename,
    )
