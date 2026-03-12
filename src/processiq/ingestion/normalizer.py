"""LLM-powered data normalizer for ProcessIQ.

Uses Instructor with Anthropic/OpenAI to extract structured process data
from messy or unstructured inputs (text descriptions, poorly formatted tables).

Supports integration with Docling for document parsing:
    >>> from processiq.ingestion import parse_file, normalize_parsed_document
    >>> doc = parse_file("process.pdf")
    >>> data, result = normalize_parsed_document(doc)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

import instructor
from anthropic import Anthropic
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator, model_validator

from processiq.config import TASK_EXTRACTION, settings
from processiq.exceptions import ExtractionError
from processiq.models.process import ProcessData, ProcessStep
from processiq.prompts import get_extraction_prompt

if TYPE_CHECKING:
    from processiq.ingestion.docling_parser import ParsedDocument

logger = logging.getLogger(__name__)

# Cached Instructor-wrapped clients (stateless, safe to reuse)
_anthropic_client: instructor.Instructor | None = None
_openai_client: instructor.Instructor | None = None


class ExtractedStep(BaseModel):
    """A process step extracted by the LLM."""

    step_name: str = Field(..., description="Name of the process step")
    average_time_hours: float = Field(..., description="Average time in hours")
    resources_needed: int = Field(
        ...,
        description="Number of people involved. Use 0 for fully automated steps with no human touch.",
    )
    error_rate_pct: float = Field(default=0.0, description="Error rate percentage")
    cost_per_instance: float = Field(
        default=0.0, description="Cost per execution in dollars"
    )
    estimated_fields: list[str] = Field(
        default_factory=list,
        description="Field names that were estimated by AI rather than provided by the user "
        "(e.g., ['cost_per_instance', 'error_rate_pct'])",
    )

    @field_validator("error_rate_pct", mode="before")
    @classmethod
    def clamp_error_rate(cls, v: object) -> object:
        if isinstance(v, int | float):
            return max(0.0, min(100.0, float(v)))
        return v

    @field_validator("average_time_hours", mode="before")
    @classmethod
    def clamp_time(cls, v: object) -> object:
        if isinstance(v, int | float):
            return max(0.0, float(v))
        return v

    @field_validator("resources_needed", mode="before")
    @classmethod
    def clamp_resources(cls, v: object) -> object:
        if isinstance(v, int | float):
            return max(0, int(v))
        return v

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: object) -> object:
        if isinstance(v, int | float):
            return max(0.0, min(1.0, float(v)))
        return v

    depends_on: list[str] = Field(
        default_factory=list,
        description="REQUIRED for every step except the first. List the step_name "
        "values of all steps that must complete before this one can start. "
        "Sequential descriptions ('after that', 'then', 'next') mean this step "
        "depends on the previous step. If this step follows a group of "
        "alternative steps, list ALL alternatives as dependencies.",
    )
    group_id: str | None = Field(
        default=None,
        description="Groups related steps. Steps with the same group_id are "
        "alternatives (either/or) or parallel (simultaneous). Use a short "
        "descriptive slug like 'receive_order' or 'post_delivery'.",
    )
    group_type: Literal["alternative", "parallel"] | None = Field(
        default=None,
        description="'alternative' = either/or choices (phone OR email), "
        "'parallel' = simultaneous steps (invoice paid AND tax entry).",
    )
    confidence: float = Field(
        default=1.0, ge=0, le=1, description="LLM's confidence in this extraction (0-1)"
    )
    step_type: Literal["normal", "conditional", "loop"] = Field(
        default="normal",
        description="'normal' = runs every time, 'conditional' = only runs under certain conditions "
        "(e.g. only if client requests revision), 'loop' = can cycle back to an earlier step.",
    )
    notes: str = Field(default="", description="Any caveats or assumptions made")

    @model_validator(mode="after")
    def ensure_estimated_fields_complete(self) -> ExtractedStep:
        """Auto-populate estimated_fields for zero numeric values the LLM forgot to flag.

        Only applies to average_time_hours, cost_per_instance, and error_rate_pct.
        resources_needed=0 is a valid explicit value (fully automated step) and is
        intentionally excluded.
        """
        auto_estimated = set(self.estimated_fields)
        if self.average_time_hours == 0.0:
            auto_estimated.add("average_time_hours")
        if self.cost_per_instance == 0.0:
            auto_estimated.add("cost_per_instance")
        if self.error_rate_pct == 0.0:
            auto_estimated.add("error_rate_pct")
        self.estimated_fields = list(auto_estimated)
        return self

    @model_validator(mode="after")
    def validate_group_fields(self) -> ExtractedStep:
        """Ensure group_id and group_type are both set or both unset."""
        if (self.group_id is None) != (self.group_type is None):
            # Auto-fix: if one is set but not the other, clear both
            self.group_id = None
            self.group_type = None
        return self


class ExtractionResult(BaseModel):
    """Result of successful LLM extraction."""

    steps: list[ExtractedStep] = Field(
        ..., min_length=1, description="Extracted process steps"
    )
    process_name: str = Field(
        default="Extracted Process", description="Inferred process name"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Issues found during extraction"
    )

    @field_validator("steps")
    @classmethod
    def strip_empty_steps(cls, v: list[ExtractedStep]) -> list[ExtractedStep]:
        return [s for s in v if s.step_name.strip()]


class ClarificationNeeded(BaseModel):
    """Returned when input is insufficient for extraction."""

    message: str = Field(
        ...,
        description="Natural, conversational response to the user. Write this as if you're a friendly consultant responding to their message. Acknowledge what they said, mention what you understood, and weave in your questions naturally. Do NOT use bullet points or numbered lists - write in flowing prose.",
    )
    detected_intent: str = Field(
        ..., description="What process the user seems to be describing"
    )
    what_we_understood: list[str] = Field(
        default_factory=list,
        description="Partial information detected (step names, context, etc.)",
    )
    clarifying_questions: list[str] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Questions to ask the user for more detail (for internal tracking)",
    )
    why_more_info_needed: str = Field(
        ..., description="Brief explanation of what's missing (for internal tracking)"
    )


class ExtractionResponse(BaseModel):
    """LLM returns EITHER extraction results OR clarifying questions - never both.

    This enables the 'smart interviewer' pattern: when users provide vague input
    like 'marketing campaign rollout', we ask good questions instead of inventing data.
    """

    response_type: Literal["extracted", "needs_clarification"] = Field(
        ..., description="Whether extraction succeeded or more info is needed"
    )

    # Populated when response_type == "extracted"
    extraction: ExtractionResult | None = Field(
        default=None,
        description="Extraction results (only if response_type='extracted')",
    )

    # Populated when response_type == "needs_clarification"
    clarification: ClarificationNeeded | None = Field(
        default=None,
        description="Clarification request (only if response_type='needs_clarification')",
    )


def _get_anthropic_client() -> instructor.Instructor:
    """Get cached Instructor-wrapped Anthropic client."""
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client

    api_key = settings.anthropic_api_key.get_secret_value()
    if not api_key:
        raise ExtractionError(
            message="Anthropic API key not configured",
            source="normalizer",
            user_message="LLM extraction requires an API key. Please configure ANTHROPIC_API_KEY.",
        )
    client = Anthropic(api_key=api_key)
    _anthropic_client = instructor.from_anthropic(client)
    return _anthropic_client


def _get_openai_client() -> instructor.Instructor:
    """Get cached Instructor-wrapped OpenAI client."""
    global _openai_client
    if _openai_client is not None:
        return _openai_client

    api_key = settings.openai_api_key.get_secret_value()
    if not api_key:
        raise ExtractionError(
            message="OpenAI API key not configured",
            source="normalizer",
            user_message="LLM extraction requires an API key. Please configure OPENAI_API_KEY.",
        )
    client = OpenAI(api_key=api_key)
    _openai_client = instructor.from_openai(client)
    return _openai_client


def _extract_with_anthropic(
    content: str,
    additional_context: str = "",
    conversation_context: str = "",
    has_process: bool = False,
    model: str = "claude-haiku-4-5-20251001",
) -> ExtractionResponse:
    """Extract process data using Anthropic Claude.

    Returns ExtractionResponse which may contain either:
    - Extracted process data (if input was sufficient)
    - Clarifying questions (if input was too vague)

    Uses Instructor's built-in retry mechanism which passes validation errors
    back to the LLM for self-correction (better than blind retries).
    """
    client = _get_anthropic_client()

    prompt = get_extraction_prompt(
        content=content,
        additional_context=additional_context,
        conversation_context=conversation_context,
        has_process=has_process,
    )

    logger.debug("Extracting with Anthropic model: %s (temperature=0)", model)

    result: ExtractionResponse = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0,  # Maximize schema adherence for extraction
        max_retries=3,  # Instructor retries with validation feedback
        messages=[{"role": "user", "content": prompt}],
        response_model=ExtractionResponse,
    )

    if result.response_type == "extracted" and result.extraction:
        logger.info("Extracted %d steps with Anthropic", len(result.extraction.steps))
    else:
        logger.info(
            "Anthropic requested clarification: %s",
            result.clarification.detected_intent if result.clarification else "unknown",
        )
    return result


def _extract_with_openai(
    content: str,
    additional_context: str = "",
    conversation_context: str = "",
    has_process: bool = False,
    model: str = "gpt-4o-mini",
) -> ExtractionResponse:
    """Extract process data using OpenAI GPT.

    Returns ExtractionResponse which may contain either:
    - Extracted process data (if input was sufficient)
    - Clarifying questions (if input was too vague)

    Uses Instructor's built-in retry mechanism which passes validation errors
    back to the LLM for self-correction (better than blank retries).
    """
    from processiq.llm import is_restricted_openai_model

    client = _get_openai_client()

    prompt = get_extraction_prompt(
        content=content,
        additional_context=additional_context,
        conversation_context=conversation_context,
        has_process=has_process,
    )

    restricted = is_restricted_openai_model(model)
    temperature = 1.0 if restricted else 0
    logger.debug(
        "Extracting with OpenAI model: %s (temperature=%s, restricted=%s)",
        model,
        temperature,
        restricted,
    )

    # GPT-5/o-series: max_completion_tokens only, no temperature override
    create_kwargs: dict[str, object] = {
        "model": model,
        "max_retries": 3,
        "messages": [{"role": "user", "content": prompt}],
        "response_model": ExtractionResponse,
    }
    if restricted:
        create_kwargs["max_completion_tokens"] = 16384
    else:
        create_kwargs["max_tokens"] = 4096
        create_kwargs["temperature"] = 0

    result: ExtractionResponse = client.chat.completions.create(**create_kwargs)  # type: ignore[call-overload]

    if result.response_type == "extracted" and result.extraction:
        logger.info("Extracted %d steps with OpenAI", len(result.extraction.steps))
    else:
        logger.info(
            "OpenAI requested clarification: %s",
            result.clarification.detected_intent if result.clarification else "unknown",
        )
    return result


def _extraction_result_to_process_data(result: ExtractionResult) -> ProcessData:
    """Convert LLM extraction result to ProcessData model."""
    steps = [
        ProcessStep(
            step_name=step.step_name,
            average_time_hours=step.average_time_hours,
            resources_needed=step.resources_needed,
            error_rate_pct=step.error_rate_pct,
            cost_per_instance=step.cost_per_instance,
            estimated_fields=step.estimated_fields,
            depends_on=step.depends_on,
            group_id=step.group_id,
            group_type=step.group_type,
            step_type=step.step_type,
            notes=step.notes,
        )
        for step in result.steps
    ]

    _infer_missing_dependencies(steps)

    return ProcessData(name=result.process_name, steps=steps)


def _infer_missing_dependencies(steps: list[ProcessStep]) -> None:
    """Fill in sequential dependencies the LLM omitted.

    When the LLM doesn't populate depends_on for non-first steps that aren't
    part of a group, default them to depend on the previous step. For steps
    that follow a group of alternatives, depend on all alternatives in that group.

    Mutates the steps list in place.
    """
    if len(steps) < 2:
        return

    all_step_names = {s.step_name for s in steps}
    filled = 0

    for i, step in enumerate(steps[1:], start=1):
        if step.depends_on:
            # Validate that referenced dependencies actually exist
            step.depends_on = [d for d in step.depends_on if d in all_step_names]
            if step.depends_on:
                continue

        # Skip steps that are part of a group — they share deps with siblings
        # and should have been handled by the LLM
        if step.group_id:
            prev_non_group = _find_previous_non_group_step(steps, i, step.group_id)
            if prev_non_group:
                step.depends_on = [prev_non_group.step_name]
                filled += 1
            continue

        # Check if previous step(s) form a group of alternatives
        prev = steps[i - 1]
        if prev.group_id and prev.group_type == "alternative":
            # Depend on all alternatives in that group
            group_deps = [s.step_name for s in steps[:i] if s.group_id == prev.group_id]
            step.depends_on = group_deps
            filled += 1
        else:
            # Simple sequential: depend on previous step
            step.depends_on = [prev.step_name]
            filled += 1

    if filled:
        logger.info("Inferred sequential dependencies for %d steps", filled)


def _find_previous_non_group_step(
    steps: list[ProcessStep], current_idx: int, current_group_id: str
) -> ProcessStep | None:
    """Find the nearest previous step not in the same group."""
    for j in range(current_idx - 1, -1, -1):
        if steps[j].group_id != current_group_id:
            return steps[j]
    return None


def normalize_with_llm(
    content: str,
    additional_context: str = "",
    analysis_mode: str | None = None,
    provider: Literal["anthropic", "openai", "ollama"] | None = None,
    model: str | None = None,
    conversation_context: str = "",
    has_process: bool = False,
) -> tuple[ProcessData | None, ExtractionResponse]:
    """Normalize messy data into structured ProcessData using an LLM.

    This function implements the 'smart interviewer' pattern:
    - If input has sufficient detail, extracts structured process data
    - If input is too vague (e.g., just a process name), returns clarifying questions
    - If conversation_context contains current data and user requests edits,
      applies the edits and returns updated process data

    Args:
        content: Raw text content to extract from (text description, table dump, etc.).
        additional_context: Optional context about the business or process.
        analysis_mode: Analysis mode preset (cost_optimized, balanced, deep_analysis).
        provider: LLM provider override. If None, uses analysis mode or task config.
        model: Specific model override. If None, uses analysis mode or task config.
        conversation_context: Optional context with current process data and recent
            messages. Enables edit requests like "change step 3 time to 2 hours".
        has_process: True when the session already has confirmed process data.
            Used by the extraction router to select the correct prompt template.

    Returns:
        Tuple of (ProcessData | None, ExtractionResponse).
        - If response.response_type == "extracted": ProcessData is populated
        - If response.response_type == "needs_clarification": ProcessData is None,
          and response.clarification contains questions to ask the user

    Raises:
        ExtractionError: If extraction fails after retries.

    Example (sufficient data):
        >>> text = '''
        ... Our expense approval process:
        ... 1. Employee fills form (30 min)
        ... 2. Manager reviews (about 1 hour, sometimes 2)
        ... 3. Finance approves (45 min)
        ... '''
        >>> data, response = normalize_with_llm(text)
        >>> if response.response_type == "extracted":
        ...     for step in data.steps:
        ...         print(f"{step.step_name}: {step.average_time_hours}h")

    Example (needs clarification):
        >>> text = "marketing campaign rollout"
        >>> data, response = normalize_with_llm(text)
        >>> if response.response_type == "needs_clarification":
        ...     for q in response.clarification.clarifying_questions:
        ...         print(q)

    Example (edit request with context):
        >>> context = build_conversation_context(current_process, ui_messages)
        >>> data, response = normalize_with_llm(
        ...     "change step 3 time to 2 hours",
        ...     conversation_context=context
        ... )
    """
    # Get task-specific config (applies analysis mode and task overrides to global defaults)
    resolved_provider, resolved_model, _ = settings.get_resolved_config(
        task=TASK_EXTRACTION, analysis_mode=analysis_mode, provider=provider
    )

    # Apply explicit overrides
    effective_provider: str = provider or resolved_provider
    model = model or resolved_model

    # Validate provider for Instructor (only anthropic/openai supported)
    if effective_provider not in ("anthropic", "openai"):
        logger.warning(
            "Provider '%s' not supported for extraction, falling back to openai",
            effective_provider,
        )
        effective_provider = "openai"
        model = settings.get_default_model("openai")

    mode_info = f" [mode={analysis_mode}]" if analysis_mode else ""
    logger.info(
        "Normalizing content with %s/%s (task=extraction)%s",
        effective_provider,
        model,
        mode_info,
    )

    try:
        if effective_provider == "anthropic":
            response = _extract_with_anthropic(
                content,
                additional_context=additional_context,
                conversation_context=conversation_context,
                has_process=has_process,
                model=model,
            )
        elif effective_provider == "openai":
            response = _extract_with_openai(
                content,
                additional_context=additional_context,
                conversation_context=conversation_context,
                has_process=has_process,
                model=model,
            )
        else:
            raise ValueError(f"Unknown provider: {effective_provider}")

    except Exception as e:
        logger.error("LLM extraction failed: %s", e)
        raise ExtractionError(
            message=f"LLM extraction failed: {e}",
            source="normalizer",
            user_message="Failed to extract process data. Please try again or use a structured format.",
        ) from e

    # Handle clarification requests
    if response.response_type == "needs_clarification":
        logger.info(
            "LLM needs clarification for '%s': %d questions",
            response.clarification.detected_intent
            if response.clarification
            else "unknown",
            len(response.clarification.clarifying_questions)
            if response.clarification
            else 0,
        )
        return None, response

    # Handle successful extraction
    if response.extraction is None:
        # Shouldn't happen if LLM follows schema, but handle gracefully
        logger.error("LLM returned 'extracted' but no extraction data")
        raise ExtractionError(
            message="LLM returned invalid response",
            source="normalizer",
            user_message="Failed to extract process data. Please try again.",
        )

    extraction = response.extraction

    # Log warnings if any
    if extraction.warnings:
        for warning in extraction.warnings:
            logger.warning("Extraction warning: %s", warning)

    # Log low-confidence extractions
    low_confidence = [s for s in extraction.steps if s.confidence < 0.7]
    if low_confidence:
        logger.warning(
            "%d steps have low confidence: %s",
            len(low_confidence),
            [s.step_name for s in low_confidence],
        )

    process_data = _extraction_result_to_process_data(extraction)
    return process_data, response


def normalize_dataframe_with_llm(
    df_text: str,
    column_info: str = "",
    provider: Literal["anthropic", "openai", "ollama"] | None = None,
) -> tuple[ProcessData | None, ExtractionResponse]:
    """Normalize a messy DataFrame (as text) into ProcessData.

    Use this when pandas loaded a table but columns don't match expected schema.

    Args:
        df_text: DataFrame as string (e.g., df.to_string() or df.to_csv()).
        column_info: Description of what each column might mean.
        provider: LLM provider to use.

    Returns:
        Tuple of (ProcessData | None, ExtractionResponse).
        ProcessData is None if LLM needs clarification.

    Example:
        >>> df = pd.read_excel("messy.xlsx")
        >>> data, response = normalize_dataframe_with_llm(
        ...     df.to_string(),
        ...     column_info="Column A is task name, B is probably duration"
        ... )
    """
    additional_context = f"""
This is tabular data that was loaded from a spreadsheet.
The column structure may not match the expected schema.

Additional info about columns:
{column_info if column_info else "No additional info provided."}

Map the columns to the expected fields based on content and column names.
"""
    return normalize_with_llm(
        df_text, provider=provider, additional_context=additional_context
    )


def normalize_parsed_document(
    document: ParsedDocument,
    analysis_mode: str | None = None,
    provider: Literal["anthropic", "openai", "ollama"] | None = None,
    model: str | None = None,
) -> tuple[ProcessData | None, ExtractionResponse]:
    """Normalize a parsed document (from Docling) into ProcessData.

    This is the recommended way to extract process data from documents.
    It intelligently combines text content with table data for better extraction.

    Flow: File → Docling → ParsedDocument → this function → ProcessData

    Args:
        document: ParsedDocument from docling_parser.parse_document().
        analysis_mode: Analysis mode preset (cost_optimized, balanced, deep_analysis).
        provider: LLM provider override. If None, uses analysis mode or task config.
        model: Specific model override. If None, uses analysis mode or task config.

    Returns:
        Tuple of (ProcessData | None, ExtractionResponse).
        ProcessData is None if LLM needs clarification.

    Raises:
        ExtractionError: If extraction fails or document parsing failed.

    Example:
        >>> from processiq.ingestion import parse_file, normalize_parsed_document
        >>> doc = parse_file("process_workflow.pdf")
        >>> data, response = normalize_parsed_document(doc)
        >>> if response.response_type == "extracted":
        ...     print(f"Extracted {len(data.steps)} steps")
    """
    # Check if document parsing succeeded
    if not document.success:
        raise ExtractionError(
            message=f"Document parsing failed: {document.error}",
            source="normalizer",
            user_message=document.error or "Failed to parse the document.",
        )

    # Check if document has content
    if not document.text.strip():
        raise ExtractionError(
            message="Document has no text content",
            source="normalizer",
            user_message="The document appears to be empty or contains only images without text.",
        )

    # Build enhanced content for LLM
    # If document has tables, include them prominently as they often contain process steps
    content_parts = []

    # Add tables first (often contain the key process data)
    table_chunks = [c for c in document.chunks if c.chunk_type == "table"]
    if table_chunks:
        content_parts.append("## Tables found in document:\n")
        for i, chunk in enumerate(table_chunks, 1):
            page_info = f" (page {chunk.page})" if chunk.page else ""
            content_parts.append(f"### Table {i}{page_info}:\n{chunk.content}\n")

    # Add full text content
    content_parts.append("\n## Full document text:\n")
    content_parts.append(document.text)

    combined_content = "\n".join(content_parts)

    # Build context about the document
    additional_context = f"""
This content was extracted from a document file: {document.metadata.get("filename", "unknown")}
Format: {document.metadata.get("format", "unknown")}
Pages: {document.metadata.get("page_count", "unknown")}
Contains tables: {document.has_tables}

The document may contain process workflow information in tables, lists, or prose.
Pay special attention to any tables as they often contain structured step data.
"""

    logger.info(
        "Normalizing parsed document: %s (%d chars, %d tables)",
        document.metadata.get("filename", "unknown"),
        len(combined_content),
        len(table_chunks),
    )

    return normalize_with_llm(
        combined_content,
        additional_context=additional_context,
        analysis_mode=analysis_mode,
        provider=provider,
        model=model,
    )
