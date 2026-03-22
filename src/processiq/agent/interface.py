"""Clean interface for UI to interact with agent.

This module decouples the Next.js/FastAPI layer from LangGraph internals.
The API layer should import from this module, not from graph.py or state.py directly.

Design principles:
- AgentResponse is the single return type for all operations
- Functions handle errors and return user-friendly messages
- LangGraph state management is hidden from the caller
- Thread ID enables conversation continuity with SqliteSaver persistence
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from processiq.agent.context import build_conversation_context
from processiq.agent.graph import compile_graph
from processiq.agent.state import create_initial_state
from processiq.analysis.confidence import ConfidenceResult, calculate_confidence
from processiq.config import settings
from processiq.exceptions import ExtractionError, ProcessIQError
from processiq.ingestion import (
    ClarificationNeeded,
    ExtractionResult,
    load_csv_from_bytes,
    load_excel_from_bytes,
    normalize_parsed_document,
    normalize_with_llm,
)
from processiq.models import (
    AnalysisInsight,
    AnalysisMemory,
    BusinessProfile,
    CompanySize,
    Constraints,
    Industry,
    ProcessData,
)
from processiq.persistence import get_checkpointer, get_thread_id
from processiq.persistence.analysis_store import (
    detect_patterns,
    get_recent_rejections,
    save_session,
)
from processiq.persistence.profile_store import load_profile, save_profile
from processiq.persistence.vector_store import embed_analysis, find_similar_analyses

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS: set[str] = set()
if settings.document_ingestion_enabled:
    from processiq.ingestion.docling_parser import (
        SUPPORTED_EXTENSIONS,
        parse_document,
    )

# Full set of extensions accepted by /extract-file (tabular + document)
ALL_SUPPORTED_EXTENSIONS: set[str] = {".csv", ".xlsx", ".xls"} | SUPPORTED_EXTENSIONS


@dataclass
class AgentResponse:
    """Response from agent to the API layer.

    This is the single return type for all interface functions.
    The caller should check which fields are populated to determine what to return.
    """

    # Text response to show the user
    message: str

    # Data extraction results (populated by extract_from_* functions)
    process_data: ProcessData | None = None
    extraction_result: ExtractionResult | None = None  # LLM extraction details

    # Analysis results (populated by analyze_process)
    analysis_insight: AnalysisInsight | None = None
    confidence: ConfidenceResult | None = None

    # Conversation state
    thread_id: str | None = None  # For conversation continuity
    needs_input: bool = False  # Agent is waiting for user response
    suggested_questions: list[str] = field(default_factory=list)

    # Clarification context (when needs_input=True and no process_data)
    clarification_context: ClarificationNeeded | None = None

    # Post-extraction improvement suggestions (when llm_explanations_enabled=True)
    # This is a user-friendly message about what would improve analysis accuracy
    improvement_suggestions: str | None = None

    # Debugging/transparency
    reasoning_trace: list[str] = field(default_factory=list)

    # Error state
    is_error: bool = False
    error_code: str | None = None  # Machine-readable error type

    @property
    def has_data(self) -> bool:
        """Check if response contains extracted process data."""
        return self.process_data is not None

    @property
    def has_analysis(self) -> bool:
        """Check if response contains analysis results."""
        return self.analysis_insight is not None

    @property
    def needs_clarification(self) -> bool:
        """Check if response is asking for clarification (smart interviewer mode)."""
        return self.needs_input and self.clarification_context is not None

    @property
    def extraction_warnings(self) -> list[str]:
        """Get extraction warnings if any."""
        if self.extraction_result:
            return self.extraction_result.warnings
        return []


def _generate_improvement_suggestions(
    process_data: ProcessData,
    confidence: ConfidenceResult,
    analysis_mode: str | None = None,
    llm_provider: str | None = None,
    business_context: str | None = None,
) -> str | None:
    """Generate user-friendly suggestions for improving extraction quality.

    Uses LLM to create encouraging, helpful suggestions about what additional
    information would improve analysis accuracy. Only called when
    llm_explanations_enabled=True.

    Args:
        process_data: The extracted process data.
        confidence: The calculated confidence result with data gaps.
        analysis_mode: Optional analysis mode preset.
        llm_provider: Optional LLM provider override.

    Returns:
        A short, friendly paragraph with improvement suggestions, or None
        if LLM is disabled or fails.
    """
    if not settings.llm_explanations_enabled:
        logger.debug("LLM explanations disabled, skipping improvement suggestions")
        return None

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from processiq.config import TASK_EXPLANATION
        from processiq.llm import get_chat_model
        from processiq.prompts import (
            get_improvement_suggestions_prompt,
            get_system_prompt,
        )

        # Count what data we have
        steps_with_time = sum(1 for s in process_data.steps if s.average_time_hours)
        steps_with_cost = sum(1 for s in process_data.steps if s.cost_per_instance)
        steps_with_errors = sum(1 for s in process_data.steps if s.error_rate_pct)
        steps_with_deps = sum(1 for s in process_data.steps if s.depends_on)

        model = get_chat_model(
            task=TASK_EXPLANATION,
            analysis_mode=analysis_mode,
            provider=llm_provider,
        )

        system_msg = get_system_prompt()
        user_msg = get_improvement_suggestions_prompt(
            process_name=process_data.name,
            step_count=len(process_data.steps),
            steps_with_time=steps_with_time,
            steps_with_cost=steps_with_cost,
            steps_with_errors=steps_with_errors,
            steps_with_dependencies=steps_with_deps,
            data_gaps=confidence.data_gaps,
            business_context=business_context,
            confidence_score=confidence.score,
        )

        logger.debug("Generating improvement suggestions for: %s", process_data.name)
        response = model.invoke(
            [
                SystemMessage(content=system_msg),
                HumanMessage(content=user_msg),
            ]
        )

        from processiq.llm import extract_text_content

        suggestions = extract_text_content(response)

        logger.info("Generated improvement suggestions (%d chars)", len(suggestions))
        return suggestions.strip()

    except Exception as e:
        logger.warning("Failed to generate improvement suggestions: %s", e)
        return None


def analyze_process(
    process: ProcessData,
    constraints: Constraints | None = None,
    profile: BusinessProfile | None = None,
    thread_id: str | None = None,
    user_id: str | None = None,
    analysis_mode: str | None = None,
    llm_provider: Literal["anthropic", "openai", "ollama"] | None = None,
    feedback_history: dict[str, dict[str, object]] | None = None,
    max_cycles_override: int | None = None,
) -> AgentResponse:
    """Run full analysis on confirmed process data.

    This is the main entry point for analysis. The process data should
    already be confirmed by the user before calling this function.

    Args:
        process: Validated process data with steps.
        constraints: Optional business constraints for filtering suggestions.
        profile: Optional business profile for context-aware recommendations.
        thread_id: Optional thread ID for conversation continuity.
        user_id: Optional user ID for persistence. If provided with no thread_id,
                 a new thread will be created for this user.
        analysis_mode: Optional analysis mode preset (cost_optimized, balanced, deep_analysis).
        llm_provider: Optional LLM provider override (openai, anthropic, ollama).
        max_cycles_override: Optional override for the investigation cycle limit.
                             None = use settings.agent_max_cycles.

    Returns:
        AgentResponse with analysis_insight populated on success,
        or is_error=True with message on failure.
    """
    # Generate thread_id if not provided (for conversation continuity)
    if thread_id is None:
        thread_id = get_thread_id(user_id) if user_id else str(uuid.uuid4())

    logger.info(
        "Starting analysis for process: %s (thread=%s)", process.name, thread_id
    )

    try:
        # Calculate confidence before analysis
        confidence = calculate_confidence(process, constraints, profile)

        # --- Persistent memory: retrieve context before analysis ---
        similar_past: list[dict[str, Any]] = []
        persistent_rejections: list[tuple[str, str]] = []
        cross_session_patterns: list[str] = []
        is_first_time_user = False

        if user_id:
            # Check if this is a first-time user before merging profile
            is_first_time_user = load_profile(user_id) is None
            # Merge saved profile with request profile (saved fields as defaults)
            profile = _merge_profile(user_id, profile)

            # Retrieve similar past analyses from ChromaDB
            similar_analyses = find_similar_analyses(
                process_data=process,
                profile=profile,
                user_id=user_id,
            )
            # Only inject past analyses above similarity threshold — below 0.4
            # the match is likely coincidental and adds noise rather than signal.
            _similarity_threshold = 0.4
            relevant_analyses = [
                sa
                for sa in similar_analyses
                if sa.similarity_score >= _similarity_threshold
            ]
            if relevant_analyses:
                logger.info(
                    "%d of %d retrieved analyses passed similarity threshold (%.1f)",
                    len(relevant_analyses),
                    len(similar_analyses),
                    _similarity_threshold,
                )
            if relevant_analyses:
                similar_past = [
                    {
                        "process_name": sa.process_name,
                        "timestamp": sa.timestamp.strftime("%Y-%m-%d"),
                        "similarity_score": round(sa.similarity_score, 2),
                        "bottlenecks": sa.bottlenecks,
                        "recommendations": sa.recommendations,
                        "rejected_recs": sa.rejected_recs,
                        "rejection_reasons": sa.rejection_reasons,
                    }
                    for sa in relevant_analyses
                ]
                logger.info(
                    "Retrieved %d similar past analyses for context", len(similar_past)
                )

            # Get persistent rejections across sessions
            persistent_rejections = get_recent_rejections(user_id, limit=20)
            if persistent_rejections:
                logger.info(
                    "Loaded %d persistent rejections", len(persistent_rejections)
                )

            # Detect cross-session patterns
            cross_session_patterns = detect_patterns(user_id)
            if cross_session_patterns:
                logger.info(
                    "Detected %d cross-session patterns", len(cross_session_patterns)
                )

        # Create initial state (with memory context)
        state = create_initial_state(
            process=process,
            constraints=constraints,
            profile=profile,
            analysis_mode=analysis_mode,
            llm_provider=llm_provider,
            feedback_history=feedback_history,
            max_cycles_override=max_cycles_override,
            similar_past_analyses=similar_past,
            persistent_rejections=persistent_rejections,
            cross_session_patterns=cross_session_patterns,
        )

        # Get checkpointer for persistence (if enabled)
        checkpointer = get_checkpointer()

        # Compile and run graph
        logger.debug(
            "Compiling analysis graph (persistence=%s)", checkpointer is not None
        )
        app = compile_graph(checkpointer=checkpointer)

        # Always use a fresh thread ID for the analysis graph to prevent
        # message accumulation from prior runs via the add_messages reducer.
        # The user-facing thread_id is kept for conversation continuity but
        # is NOT passed to the graph.
        analysis_thread_id = str(uuid.uuid4())
        config: dict[str, Any] = {"configurable": {"thread_id": analysis_thread_id}}

        logger.debug("Invoking analysis graph (analysis_thread=%s)", analysis_thread_id)
        result = app.invoke(state, config=config)

        # Extract results from state
        analysis_insight = result.get("analysis_insight")
        reasoning_trace = result.get("reasoning_trace", [])
        needs_clarification = result.get("needs_clarification", False)
        clarification_questions = result.get("clarification_questions", [])
        state_error = result.get("error", "")

        # Handle clarification requests
        if needs_clarification and clarification_questions:
            logger.info(
                "Analysis needs clarification: %d questions",
                len(clarification_questions),
            )
            return AgentResponse(
                message="I need a bit more information to provide better recommendations.",
                process_data=process,
                confidence=confidence,
                thread_id=thread_id,
                needs_input=True,
                suggested_questions=clarification_questions,
                reasoning_trace=reasoning_trace,
            )

        # Check for LLM-based insight
        if analysis_insight:
            # --- Source attribution: mark which past analyses informed this one ---
            if similar_past:
                analysis_insight.context_sources = [
                    f"Past analysis: '{sa['process_name']}' ({sa['timestamp']})"
                    for sa in similar_past
                ]

            logger.info(
                "LLM analysis complete: %d issues, %d recommendations",
                len(analysis_insight.issues),
                len(analysis_insight.recommendations),
            )

            # --- Persist analysis session and embed in ChromaDB ---
            if user_id:
                _persist_analysis(
                    user_id=user_id,
                    process=process,
                    profile=profile,
                    insight=analysis_insight,
                    thread_id=thread_id,
                )

            summary = _generate_insight_summary(analysis_insight)
            if is_first_time_user and not similar_past:
                summary += (
                    "\n\n*This is your first analysis. As you analyze more processes, "
                    "ProcessIQ will learn your preferences and give more calibrated "
                    "recommendations.*"
                )
            return AgentResponse(
                message=summary,
                process_data=process,
                analysis_insight=analysis_insight,
                confidence=confidence,
                thread_id=thread_id,
                reasoning_trace=reasoning_trace,
            )

        # Analysis completed but no results
        logger.warning("Analysis completed but produced no results")
        if state_error == "timeout":
            message = (
                "The local model (Ollama) did not respond within the time limit. "
                "This is a performance limitation of running large models on CPU — "
                "the analysis schema is too complex for qwen3:8b to complete in time. "
                "Try switching to OpenAI or Anthropic in the sidebar, or pull a smaller "
                "Ollama model such as llama3.2:3b."
            )
        else:
            message = (
                "Analysis completed but could not generate recommendations. "
                "Please try again or switch to a different LLM provider."
            )
        return AgentResponse(
            message=message,
            process_data=process,
            confidence=confidence,
            thread_id=thread_id,
            reasoning_trace=reasoning_trace,
            is_error=True,
            error_code="no_results",
        )

    except ProcessIQError as e:
        logger.error("Analysis failed with ProcessIQError: %s", e)
        return AgentResponse(
            message=e.user_message or str(e),
            thread_id=thread_id,
            is_error=True,
            error_code=type(e).__name__,
        )
    except Exception as e:
        logger.exception("Analysis failed with unexpected error: %s", e)
        return AgentResponse(
            message=f"Analysis failed unexpectedly: {e}",
            thread_id=thread_id,
            is_error=True,
            error_code="unexpected_error",
        )


def extract_from_text(
    user_message: str,
    analysis_mode: str | None = None,
    additional_context: str = "",
    current_process_data: ProcessData | None = None,
    ui_messages: list[Any] | None = None,
    constraints: Constraints | None = None,
    profile: BusinessProfile | None = None,
    llm_provider: Literal["anthropic", "openai", "ollama"] | None = None,
) -> AgentResponse:
    """Extract ProcessData from natural language description.

    Implements the 'smart interviewer' pattern:
    - If user provides sufficient detail, extracts structured process data
    - If user provides vague input (e.g., just a process name), asks clarifying questions
    - If current_process_data is provided and user requests edits, applies them

    Args:
        user_message: User's text description of their process.
        analysis_mode: Analysis mode preset (cost_optimized, balanced, deep_analysis).
        additional_context: Optional business context to improve extraction.
        current_process_data: Optional existing ProcessData for edit requests.
            When provided, enables edits like "change step 3 time to 2 hours".
        ui_messages: Optional list of UI ChatMessage objects for conversation context.
            Recent user messages help the LLM understand edit requests.
        constraints: Optional business constraints (for confidence calculation).
        profile: Optional business profile (for confidence calculation).

    Returns:
        AgentResponse with either:
        - process_data populated (successful extraction, user should confirm)
        - clarification_context populated (needs more info, user should answer questions)
    """
    logger.info("Extracting process data from text (analysis_mode=%s)", analysis_mode)

    if not user_message.strip():
        return AgentResponse(
            message="Please describe your process. Include step names, "
            "how long each step takes, and any dependencies between steps.",
            needs_input=True,
            is_error=True,
            error_code="empty_input",
        )

    # Build conversation context for edit support
    conversation_context = build_conversation_context(
        process_data=current_process_data,
        ui_messages=ui_messages or [],
    )

    if conversation_context:
        logger.debug(
            "Built conversation context (%d chars) for extraction",
            len(conversation_context),
        )

    try:
        process_data, response = normalize_with_llm(
            content=user_message,
            additional_context=additional_context,
            analysis_mode=analysis_mode,
            provider=llm_provider,
            conversation_context=conversation_context,
            has_process=current_process_data is not None,
        )

        # Handle clarification requests (smart interviewer mode)
        if response.response_type == "needs_clarification" and response.clarification:
            clarification = response.clarification
            logger.info(
                "LLM needs clarification for '%s': %d questions",
                clarification.detected_intent,
                len(clarification.clarifying_questions),
            )

            # Build a friendly message
            message = _generate_clarification_message(clarification)

            return AgentResponse(
                message=message,
                needs_input=True,
                suggested_questions=clarification.clarifying_questions,
                clarification_context=clarification,
            )

        # Handle successful extraction
        if process_data is None:
            # This can happen if input describes problems but not process steps,
            # or if the LLM couldn't determine the structure. Provide helpful guidance.
            logger.warning("Extraction returned no data and no clarification request")
            return AgentResponse(
                message=_generate_extraction_guidance(user_message),
                needs_input=True,
                is_error=False,  # Not really an error - just need more info
                error_code="needs_more_detail",
            )

        # Get extraction result from response
        extraction_result = response.extraction

        # Calculate confidence on extracted data (include sidebar context if available)
        confidence = calculate_confidence(
            process_data, constraints=constraints, profile=profile
        )

        # Generate improvement suggestions
        from processiq.agent.nodes import _format_business_context_for_llm

        improvement_suggestions = _generate_improvement_suggestions(
            process_data,
            confidence,
            analysis_mode=analysis_mode,
            llm_provider=llm_provider,
            business_context=_format_business_context_for_llm(profile)
            if profile
            else None,
        )

        # Build response message
        message = _generate_extraction_summary(process_data, extraction_result)

        logger.info("Extracted %d steps from text", len(process_data.steps))

        return AgentResponse(
            message=message,
            process_data=process_data,
            extraction_result=extraction_result,
            confidence=confidence,
            improvement_suggestions=improvement_suggestions,
            needs_input=True,  # User should confirm extraction
            suggested_questions=_generate_targeted_questions(process_data, confidence),
        )

    except ExtractionError as e:
        logger.error("Text extraction failed: %s", e)
        return AgentResponse(
            message=e.user_message
            or "Failed to extract process data from your description.",
            is_error=True,
            error_code="extraction_failed",
        )
    except Exception as e:
        logger.exception("Text extraction failed unexpectedly: %s", e)
        return AgentResponse(
            message=f"Failed to process your description: {e}",
            is_error=True,
            error_code="unexpected_error",
        )


def _file_bytes_to_text(file_bytes: bytes, suffix: str) -> str:
    """Convert file bytes to LLM-readable text.

    For binary formats (xlsx, xls), reads via pandas and converts to CSV.
    For text formats, decodes as UTF-8.
    """
    if suffix in (".xlsx", ".xls"):
        try:
            df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
            return df.to_csv(index=False)
        except Exception:
            logger.warning("Failed to read %s via pandas for LLM fallback", suffix)
            return file_bytes.decode("utf-8", errors="replace")
    return file_bytes.decode("utf-8", errors="replace")


def extract_from_file(
    file_bytes: bytes,
    filename: str,
    analysis_mode: str | None = None,
    constraints: Constraints | None = None,
    profile: BusinessProfile | None = None,
    llm_provider: Literal["anthropic", "openai", "ollama"] | None = None,
    current_process_data: ProcessData | None = None,
) -> AgentResponse:
    """Extract ProcessData from uploaded file.

    Supports CSV and Excel files. For messy files, uses LLM normalization.
    The extracted data should be shown to the user for confirmation.

    Args:
        file_bytes: Raw file content.
        filename: Original filename (used for format detection).
        analysis_mode: Analysis mode preset (cost_optimized, balanced, deep_analysis).
        constraints: Optional business constraints (for confidence calculation).
        profile: Optional business profile (for confidence calculation).
        llm_provider: Optional LLM provider override.
        current_process_data: Optional existing process data. When provided, the
            LLM is instructed to match uploaded data to existing step names so that
            merge_with() can correctly merge by name instead of creating duplicates.

    Returns:
        AgentResponse with process_data populated on success,
        or clarification_context if LLM needs more information.
    """
    logger.info("Extracting process data from file: %s", filename)

    if not file_bytes:
        return AgentResponse(
            message="No file content received. Please try uploading again.",
            is_error=True,
            error_code="empty_file",
        )

    suffix = Path(filename).suffix.lower()
    process_data: ProcessData | None = None
    extraction_result: ExtractionResult | None = None
    clarification: ClarificationNeeded | None = None
    used_llm = False

    # Build merge-aware context when existing process data is available.
    # This tells the LLM to reuse existing step names so merge_with() can
    # match them instead of creating duplicates with different names.
    merge_context = _build_file_merge_context(current_process_data, filename)

    # Reject unsupported formats early
    all_supported = {".csv", ".xlsx", ".xls"} | SUPPORTED_EXTENSIONS
    if suffix not in all_supported:
        supported_list = ", ".join(sorted(all_supported))
        return AgentResponse(
            message=f"Unsupported file format: {suffix}. "
            f"Supported formats: {supported_list}",
            is_error=True,
            error_code="unsupported_format",
        )

    # When existing process data exists, skip structured loaders and go
    # straight to LLM normalization. The LLM needs the merge context to
    # map file step names (e.g., "Phone Request Intake") to existing names
    # (e.g., "Receive Order via Phone"). Structured loaders can't do this.
    needs_llm_merge = current_process_data is not None and current_process_data.steps

    try:
        if needs_llm_merge:
            # Force LLM path for semantic name matching / supplement detection.
            # Pass has_process=True so the router picks extract_update, which
            # instructs the LLM to merge or ask for clarification rather than
            # treating the file as a brand-new process description.
            logger.info(
                "Existing process data found (%d steps), using LLM for file merge",
                len(current_process_data.steps) if current_process_data else 0,
            )
            content = _file_bytes_to_text(file_bytes, suffix)
            conversation_context = build_conversation_context(
                process_data=current_process_data,
                ui_messages=[],
            )
            process_data, response = normalize_with_llm(
                content=content,
                additional_context=merge_context,
                analysis_mode=analysis_mode,
                provider=llm_provider,
                conversation_context=conversation_context,
                has_process=True,
            )
            used_llm = True

            if response.response_type == "needs_clarification":
                clarification = response.clarification
                extraction_result = None
            else:
                extraction_result = response.extraction

        # No existing data — try structured loaders first (fast path)
        elif suffix == ".csv":
            process_data = load_csv_from_bytes(
                file_bytes, process_name=Path(filename).stem
            )
        elif suffix in (".xlsx", ".xls"):
            process_data = load_excel_from_bytes(
                file_bytes, process_name=Path(filename).stem
            )
        else:
            # Use Docling for PDFs, images, DOCX, etc.
            if not settings.document_ingestion_enabled:
                raise ProcessIQError(
                    f"File type '{suffix}' is not supported. Please upload a CSV or Excel file."
                )
            logger.info("Using Docling parser for %s file", suffix)
            parsed_doc = parse_document(file_bytes, filename)
            process_data, response = normalize_parsed_document(
                parsed_doc,
                analysis_mode=analysis_mode,
                provider=llm_provider,
            )
            used_llm = True

            # Handle clarification requests from LLM
            if response.response_type == "needs_clarification":
                clarification = response.clarification
                extraction_result = None
            else:
                extraction_result = response.extraction

        # Check if we got usable data
        if process_data is None or not process_data.steps:
            # Try LLM normalization as fallback
            logger.info(
                "Structured loading produced no steps, trying LLM normalization"
            )
            content = _file_bytes_to_text(file_bytes, suffix)
            process_data, response = normalize_with_llm(
                content=content,
                additional_context=merge_context,
                analysis_mode=analysis_mode,
                provider=llm_provider,
            )
            used_llm = True

            # Handle clarification requests
            if response.response_type == "needs_clarification":
                clarification = response.clarification
                extraction_result = None
            else:
                extraction_result = response.extraction

    except ExtractionError as e:
        logger.error("File extraction failed: %s", e)
        return AgentResponse(
            message=e.user_message or f"Failed to extract data from {filename}.",
            is_error=True,
            error_code="extraction_failed",
        )
    except Exception as e:
        logger.warning("Structured loading failed, trying LLM normalization: %s", e)
        try:
            content = _file_bytes_to_text(file_bytes, suffix)
            process_data, response = normalize_with_llm(
                content=content,
                additional_context=merge_context,
                analysis_mode=analysis_mode,
                provider=llm_provider,
            )
            used_llm = True

            # Handle clarification requests
            if response.response_type == "needs_clarification":
                clarification = response.clarification
                extraction_result = None
            else:
                extraction_result = response.extraction
        except Exception as llm_error:
            logger.exception("LLM normalization also failed: %s", llm_error)
            return AgentResponse(
                message=f"Failed to process {filename}. The file format may not be supported "
                "or the content may not represent a process.",
                is_error=True,
                error_code="extraction_failed",
            )

    # Handle clarification requests from LLM
    if clarification is not None:
        message = _generate_clarification_message(clarification)
        message = f"I loaded {filename}, but {message}"
        return AgentResponse(
            message=message,
            needs_input=True,
            suggested_questions=clarification.clarifying_questions,
            clarification_context=clarification,
        )

    if process_data is None or not process_data.steps:
        return AgentResponse(
            message=f"Could not find any process steps in {filename}. "
            "Please ensure the file contains step names and timing information.",
            is_error=True,
            error_code="no_steps_found",
        )

    # Calculate confidence (include sidebar context if available)
    confidence = calculate_confidence(
        process_data, constraints=constraints, profile=profile
    )

    # Generate improvement suggestions
    improvement_suggestions = _generate_improvement_suggestions(
        process_data,
        confidence,
        analysis_mode=analysis_mode,
        llm_provider=llm_provider,
    )

    # Build response message
    if extraction_result:
        message = _generate_extraction_summary(process_data, extraction_result)
    else:
        message = f"Loaded {len(process_data.steps)} steps from {filename}."
        if used_llm:
            message += " (normalized using AI)"

    logger.info("Extracted %d steps from file: %s", len(process_data.steps), filename)

    return AgentResponse(
        message=message,
        process_data=process_data,
        extraction_result=extraction_result,
        confidence=confidence,
        improvement_suggestions=improvement_suggestions,
        needs_input=True,  # User should confirm extraction
        suggested_questions=_generate_targeted_questions(process_data, confidence),
    )


_REANALYSIS_SIGNALS = [
    "re-analyze",
    "reanalyze",
    "re analyze",
    "run analysis",
    "run the analysis",
    "fresh analysis",
    "new analysis",
    "analyze again",
    "redo the analysis",
]


def _wants_reanalysis(message: str) -> bool:
    """Return True if the message is explicitly requesting a fresh analysis run."""
    lower = message.lower()
    return any(signal in lower for signal in _REANALYSIS_SIGNALS)


def _answer_followup(
    user_message: str,
    insight: AnalysisInsight,
    constraints: Any | None,
    profile: Any | None,
    thread_id: str,
    analysis_mode: str | None = None,
) -> "AgentResponse":
    """Answer a follow-up question about a completed analysis using followup.j2.

    Called from continue_conversation when process data AND analysis_insight
    are both present in the saved state. Routes the user message to the
    followup prompt instead of re-running the full analysis.

    Args:
        user_message: The user's follow-up question or remark.
        insight: The AnalysisInsight from the completed analysis.
        constraints: Optional Constraints from saved state.
        profile: Optional BusinessProfile from saved state.
        thread_id: The conversation thread ID.
        analysis_mode: Optional analysis mode preset.

    Returns:
        AgentResponse with a conversational reply (no process_data, no full analysis).
    """
    logger.info(
        "Routing to followup prompt for thread=%s, message=%s",
        thread_id,
        user_message[:60],
    )

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from processiq.agent.nodes import (
            _format_business_context_for_llm,
            _format_constraints_for_llm,
        )
        from processiq.config import TASK_EXPLANATION
        from processiq.llm import extract_text_content, get_chat_model
        from processiq.prompts import get_followup_prompt, get_system_prompt

        constraints_summary = (
            _format_constraints_for_llm(constraints) if constraints else None
        )
        business_context = (
            _format_business_context_for_llm(profile) if profile else None
        )

        model = get_chat_model(task=TASK_EXPLANATION, analysis_mode=analysis_mode)

        followup_prompt = get_followup_prompt(
            user_question=user_message,
            insight=insight,
            constraints_summary=constraints_summary,
            business_context=business_context,
            history=[],
        )

        response = model.invoke(
            [
                SystemMessage(content=get_system_prompt(profile=profile)),
                HumanMessage(content=followup_prompt),
            ]
        )

        answer = extract_text_content(response).strip()
        logger.info("Followup answer generated (%d chars)", len(answer))

        return AgentResponse(
            message=answer,
            thread_id=thread_id,
            needs_input=True,
        )

    except Exception as e:
        logger.error("Failed to generate followup answer: %s", e)
        return AgentResponse(
            message="I wasn't able to answer that. Please try rephrasing your question.",
            thread_id=thread_id,
            needs_input=True,
            is_error=True,
            error_code="followup_error",
        )


def continue_conversation(
    thread_id: str,
    user_message: str,
    file_bytes: bytes | None = None,
    filename: str | None = None,
    analysis_mode: str | None = None,
) -> AgentResponse:
    """Continue an existing conversation thread.

    This function enables multi-turn conversations where the agent
    can ask follow-up questions and refine the analysis.

    With SqliteSaver persistence enabled, this function can:
    - Resume from saved conversation state
    - Continue analysis with additional user input
    - Process follow-up questions in context

    Args:
        thread_id: Existing thread ID from a previous response.
        user_message: User's response to the agent.
        file_bytes: Optional file upload.
        filename: Original filename if file provided.
        analysis_mode: Analysis mode preset for LLM calls.

    Returns:
        AgentResponse continuing the conversation.
    """
    logger.info("Continuing conversation: thread=%s", thread_id)

    # Handle file uploads first (they provide new data)
    if file_bytes and filename:
        return extract_from_file(file_bytes, filename, analysis_mode=analysis_mode)

    # Handle empty input
    if not user_message.strip():
        return AgentResponse(
            message="I didn't receive any input. Please describe your process or upload a file.",
            thread_id=thread_id,
            needs_input=True,
            is_error=True,
            error_code="empty_input",
        )

    # Try to get checkpointer for state retrieval
    checkpointer = get_checkpointer()
    if checkpointer is None:
        # Persistence disabled - fall back to extraction
        logger.debug("Persistence disabled, falling back to text extraction")
        return extract_from_text(user_message, analysis_mode=analysis_mode)

    try:
        # Get the latest state for this thread
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        checkpoint = checkpointer.get(config)

        if checkpoint is None:
            # No previous state - treat as new conversation
            logger.info("No checkpoint found for thread %s, starting fresh", thread_id)
            return extract_from_text(
                user_message,
                analysis_mode=analysis_mode,
                additional_context=f"Thread ID: {thread_id}",
            )

        # We have previous state - extract the saved data
        saved_state = checkpoint.get("channel_values", {})
        logger.debug("Retrieved saved state with keys: %s", list(saved_state.keys()))

        # Check if we have process data from previous interaction
        process_data = saved_state.get("process")
        analysis_insight = saved_state.get("analysis_insight")

        if process_data and analysis_insight:
            # Analysis is already done.
            # Route to followup unless the user is explicitly asking for a fresh run.
            constraints = saved_state.get("constraints")
            profile = saved_state.get("profile")

            if _wants_reanalysis(user_message):
                logger.info(
                    "Re-analysis requested for thread=%s, re-running analysis",
                    thread_id,
                )
                # Merge re-analysis note into profile context so the agent
                # knows why it is running again
                if profile is None:
                    profile = BusinessProfile(
                        industry=Industry.OTHER,
                        company_size=CompanySize.SMALL,
                        notes=user_message,
                    )
                elif profile.notes:
                    profile = BusinessProfile(
                        **{
                            **profile.model_dump(),
                            "notes": f"{profile.notes}\n{user_message}",
                        }
                    )
                else:
                    profile = BusinessProfile(
                        **{**profile.model_dump(), "notes": user_message}
                    )
                return analyze_process(
                    process=process_data,
                    constraints=constraints,
                    profile=profile,
                    thread_id=thread_id,
                )

            # Regular follow-up question or remark — answer conversationally
            logger.info(
                "Post-analysis follow-up for thread=%s, message: %s",
                thread_id,
                user_message[:50],
            )
            return _answer_followup(
                user_message=user_message,
                insight=analysis_insight,
                constraints=constraints,
                profile=profile,
                thread_id=thread_id,
                analysis_mode=analysis_mode,
            )

        if process_data:
            # Process loaded but no analysis yet — user is providing context.
            # Add user message to profile notes and re-run analysis.
            logger.info(
                "Continuing with saved process data (no analysis yet), user message: %s",
                user_message[:50],
            )

            constraints = saved_state.get("constraints")
            profile = saved_state.get("profile")

            # Merge user message into profile notes for context
            if profile is None:
                profile = BusinessProfile(
                    industry=Industry.OTHER,
                    company_size=CompanySize.SMALL,
                    notes=user_message,
                )
            elif profile.notes:
                profile = BusinessProfile(
                    **{
                        **profile.model_dump(),
                        "notes": f"{profile.notes}\n{user_message}",
                    }
                )
            else:
                profile = BusinessProfile(
                    **{**profile.model_dump(), "notes": user_message}
                )

            # Re-run analysis with updated context
            return analyze_process(
                process=process_data,
                constraints=constraints,
                profile=profile,
                thread_id=thread_id,
            )

        # No process data yet - user is still describing their process
        return extract_from_text(
            user_message,
            analysis_mode=analysis_mode,
            additional_context=f"Continuing conversation {thread_id}",
        )

    except Exception as e:
        logger.warning("Error retrieving checkpoint, falling back to extraction: %s", e)
        return extract_from_text(user_message, analysis_mode=analysis_mode)


def get_thread_state(thread_id: str) -> dict[str, Any] | None:
    """Get the saved state for a conversation thread.

    Args:
        thread_id: The thread ID to look up.

    Returns:
        Saved state dict if found, None if not found or persistence disabled.
    """
    checkpointer = get_checkpointer()
    if checkpointer is None:
        return None

    try:
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        checkpoint = checkpointer.get(config)
        if checkpoint:
            return dict(checkpoint.get("channel_values", {}))
        return None
    except Exception as e:
        logger.warning("Error getting thread state: %s", e)
        return None


def has_saved_state(thread_id: str) -> bool:
    """Check if a thread has saved state.

    Args:
        thread_id: The thread ID to check.

    Returns:
        True if thread has saved state, False otherwise.
    """
    return get_thread_state(thread_id) is not None


# Helper functions


def _build_file_merge_context(
    current_process_data: ProcessData | None,
    filename: str,
) -> str:
    """Build additional_context for file extraction that enables smart merging.

    When existing process data exists, instructs the LLM to reuse existing step
    names where the uploaded file data refers to the same step under a different
    name. This lets merge_with() match by name instead of creating duplicates.

    Args:
        current_process_data: Existing process data (may be None).
        filename: The uploaded filename.

    Returns:
        Additional context string for the LLM extraction call.
    """
    base = f"This data was loaded from a file named {filename}."

    if not current_process_data or not current_process_data.steps:
        return base

    step_names = [s.step_name for s in current_process_data.steps]
    names_list = "\n".join(f"  - {name}" for name in step_names)

    return (
        f"{base}\n\n"
        f"IMPORTANT — Existing process steps already extracted from a previous input:\n"
        f"{names_list}\n\n"
        f"The file may refer to the same steps under different names (e.g., "
        f"'Phone Request Intake' in the file is the same as 'Receive Order via Phone' "
        f"from the previous input).\n\n"
        f"Rules for step naming:\n"
        f"1. If a step in the file clearly maps to an existing step above, "
        f"use the EXISTING step name exactly as written above.\n"
        f"2. Only create a NEW step name if the file describes an activity "
        f"that has no match in the existing steps.\n"
        f"3. When in doubt, prefer matching to an existing step over creating a new one."
    )


def _generate_insight_summary(insight: AnalysisInsight) -> str:
    """Generate a brief summary message for LLM-based analysis insight."""
    parts = []

    # Count issues by severity
    if insight.issues:
        high_issues = sum(1 for i in insight.issues if i.severity == "high")
        if high_issues:
            parts.append(
                f"{high_issues} significant issue{'s' if high_issues > 1 else ''}"
            )
        else:
            parts.append(
                f"{len(insight.issues)} issue{'s' if len(insight.issues) > 1 else ''}"
            )

    if insight.recommendations:
        parts.append(
            f"{len(insight.recommendations)} recommendation{'s' if len(insight.recommendations) > 1 else ''}"
        )

    if insight.not_problems:
        parts.append(
            f"{len(insight.not_problems)} area{'s' if len(insight.not_problems) > 1 else ''} that look fine"
        )

    if parts:
        return f"Analysis complete. Found {', '.join(parts)}."
    return "Analysis complete."


def _generate_extraction_summary(
    process_data: ProcessData,
    extraction_result: ExtractionResult | None,
) -> str:
    """Generate a brief summary message for extraction results."""
    message = f"I extracted {len(process_data.steps)} steps from your description"

    if process_data.name and process_data.name != "Extracted Process":
        message = f"I identified this as '{process_data.name}' with {len(process_data.steps)} steps"

    # Add warning count if any
    if extraction_result and extraction_result.warnings:
        message += f" ({len(extraction_result.warnings)} warning{'s' if len(extraction_result.warnings) > 1 else ''})"

    message += ". Please review the data below."
    return message


def _generate_clarification_message(clarification: ClarificationNeeded) -> str:
    """Get the LLM's natural conversational response.

    The LLM now writes a natural 'message' field directly, so we just use that
    instead of reconstructing from parts.
    """
    # Use the LLM-generated message if available
    if hasattr(clarification, "message") and clarification.message:
        return clarification.message.strip()

    # Fallback for older responses without the message field
    parts = []
    if clarification.detected_intent:
        parts.append(
            f"I'd like to help you analyze your {clarification.detected_intent}."
        )
    parts.append(clarification.why_more_info_needed)
    if clarification.clarifying_questions:
        parts.append(
            "Could you tell me: "
            + " ".join(clarification.clarifying_questions[:2])
            + "?"
        )
    return " ".join(parts)


def _generate_targeted_questions(
    process_data: ProcessData,
    confidence: ConfidenceResult,
) -> list[str]:
    """Generate specific follow-up questions based on data gaps.

    Builds targeted questions algorithmically from ConfidenceResult.data_gaps.
    No LLM call needed -- deterministic mapping from gap type to question.

    Args:
        process_data: The extracted process data.
        confidence: Confidence result with data_gaps list.

    Returns:
        List of 2-5 targeted questions. Falls back to generic questions
        if no specific gaps are identified.
    """
    questions: list[str] = []

    for gap in confidence.data_gaps:
        gap_lower = gap.lower()

        if "time for" in gap_lower:
            step_name = _extract_step_name_from_gap(gap)
            if step_name:
                questions.append(
                    f"How long does '{step_name}' typically take? Even a rough estimate helps."
                )

        elif "cost for" in gap_lower:
            step_name = _extract_step_name_from_gap(gap)
            if step_name:
                questions.append(
                    f"What does '{step_name}' cost per instance? Include labor and tools."
                )

        elif "error rate for" in gap_lower:
            step_name = _extract_step_name_from_gap(gap)
            if step_name:
                questions.append(
                    f"How often does '{step_name}' need rework or fail? Even 'rarely' vs 'often' helps."
                )

        elif "no dependencies" in gap_lower:
            questions.append(
                "Which steps depend on others being done first? "
                "This helps identify where delays cascade."
            )

        elif "no constraints" in gap_lower:
            questions.append(
                "Are there any budget limits, hiring freezes, or timeline constraints I should know about?"
            )

        elif "no business profile" in gap_lower:
            questions.append(
                "What industry are you in? This helps me tailor recommendations."
            )

    # Deduplicate and limit
    seen: set[str] = set()
    unique: list[str] = []
    for q in questions:
        if q not in seen:
            seen.add(q)
            unique.append(q)
        if len(unique) >= 4:
            break

    if unique:
        return ["Does this look correct?", *unique]

    # Fallback to generic questions
    return [
        "Does this look correct?",
        "Would you like to add any missing steps?",
        "Are there any constraints I should know about?",
    ]


def _extract_step_name_from_gap(gap: str) -> str | None:
    """Extract step name from a data gap string like \"cost for 'Manager Review'\"."""
    match = re.search(r"for ['\"](.+?)['\"]", gap)
    return match.group(1) if match else None


def _merge_profile(
    user_id: str, request_profile: BusinessProfile | None
) -> BusinessProfile:
    """Merge a saved profile with the request profile.

    Saved fields act as defaults — anything explicitly set in the request wins.
    This lets the user override their profile per-request without losing saved data.
    """
    saved = load_profile(user_id)
    if saved is None:
        return request_profile or BusinessProfile()
    if request_profile is None:
        return saved

    # Request fields override saved fields when explicitly set
    merged_data = saved.model_dump()
    request_data = request_profile.model_dump(exclude_defaults=True)
    merged_data.update(request_data)
    return BusinessProfile(**merged_data)


def _persist_analysis(
    user_id: str,
    process: ProcessData,
    profile: BusinessProfile | None,
    insight: AnalysisInsight,
    thread_id: str,
) -> None:
    """Save analysis session to SQLite and embed in ChromaDB.

    Called after a successful analysis. Never raises — persistence is best-effort.
    """
    try:
        memory = AnalysisMemory(
            id=thread_id,
            user_id=user_id,
            process_name=process.name,
            process_description=process.description or "",
            industry=profile.industry.value if profile and profile.industry else "",
            step_names=[s.step_name for s in process.steps],
            bottlenecks_found=[i.title for i in insight.issues],
            suggestions_offered=[r.title for r in insight.recommendations],
            recommendations_full=[
                r.model_dump(
                    include={
                        "title",
                        "description",
                        "expected_benefit",
                        "estimated_roi",
                    }
                )
                for r in insight.recommendations
            ],
            process_summary=insight.process_summary,
            issue_descriptions=[i.description for i in insight.issues],
        )

        save_session(user_id=user_id, memory=memory)
        embed_analysis(memory=memory, profile=profile)

        # Auto-update saved profile with current settings
        if profile:
            save_profile(user_id, profile)

        logger.info(
            "Persisted analysis session %s for user %s", thread_id[:8], user_id[:8]
        )
    except Exception:
        logger.warning("Failed to persist analysis session", exc_info=True)


def _generate_extraction_guidance(user_message: str) -> str:
    """Generate helpful guidance when extraction couldn't produce structured data.

    This creates a friendly, conversational response that acknowledges what the user
    said and guides them toward providing the information we need.
    """
    # Check if user described problems/pain points without process steps
    problem_keywords = [
        "problem",
        "issue",
        "struggle",
        "mess",
        "broken",
        "slow",
        "error",
        "complaint",
    ]
    has_problems = any(kw in user_message.lower() for kw in problem_keywords)

    # Check if user mentioned a process or workflow
    process_keywords = ["process", "workflow", "procedure", "how we", "steps", "flow"]
    mentions_process = any(kw in user_message.lower() for kw in process_keywords)

    # Build a conversational response
    if has_problems and not mentions_process:
        # User described problems but not the process
        return (
            "I can hear there are some real pain points here. To help identify what's "
            "causing these issues, I need to understand how work actually flows through "
            "your team. Could you walk me through the typical steps from start to finish? "
            "For example: when a new [project/request/order] comes in, what happens first, "
            "and then what happens next?"
        )

    if mentions_process:
        # User mentioned a process but we couldn't extract steps
        return (
            "Thanks for sharing that context. To analyze this properly, I need a bit more "
            "detail about the specific steps involved. Could you walk me through what happens "
            "at each stage? For instance: who does what, roughly how long each part takes, "
            "and which steps depend on others being done first?"
        )

    # Generic but still helpful response
    return (
        "I'd love to help optimize your process. To do that, I need to understand the "
        "workflow in more detail. Could you describe the main steps involved? For each "
        "step, it helps to know: what happens, who's involved, and roughly how long it "
        "takes. Even rough estimates like 'a few hours' or 'about a day' are useful."
    )
