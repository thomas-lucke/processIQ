"""API request/response schemas for the ProcessIQ FastAPI backend.

These are the HTTP contract models — separate from domain models in processiq/models/.
They can be thin wrappers, but they must not contain business logic.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from processiq.analysis.visualization import GraphSchema
from processiq.models import (
    AnalysisInsight,
    BusinessProfile,
    Constraints,
    ProcessData,
)

# ---------------------------------------------------------------------------
# Shared sub-types
# ---------------------------------------------------------------------------


class UIMessage(BaseModel):
    """A chat message from the UI conversation history."""

    role: Literal["user", "assistant"]
    content: str


# ---------------------------------------------------------------------------
# /analyze
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    process: ProcessData
    constraints: Constraints | None = None
    profile: BusinessProfile | None = None
    thread_id: str | None = None
    user_id: str | None = None
    analysis_mode: str | None = None
    llm_provider: Literal["anthropic", "openai", "ollama"] | None = None
    feedback_history: dict[str, dict[str, Any]] | None = None
    max_cycles_override: int | None = None


class AnalyzeResponse(BaseModel):
    message: str
    analysis_insight: AnalysisInsight | None = None
    graph_schema: GraphSchema | None = None
    thread_id: str | None = None
    is_error: bool = False
    error_code: str | None = None
    reasoning_trace: list[str] = Field(default_factory=list)
    context_sources: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# /profile
# ---------------------------------------------------------------------------


class ProfileResponse(BaseModel):
    profile: BusinessProfile | None = None


# ---------------------------------------------------------------------------
# /feedback
# ---------------------------------------------------------------------------


class FeedbackRequest(BaseModel):
    accepted: list[str] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class FeedbackResponse(BaseModel):
    status: str = "ok"


# ---------------------------------------------------------------------------
# /extract  (text)
# ---------------------------------------------------------------------------


class ExtractTextRequest(BaseModel):
    text: str
    analysis_mode: str | None = None
    additional_context: str = ""
    current_process_data: ProcessData | None = None
    ui_messages: list[UIMessage] | None = None
    constraints: Constraints | None = None
    profile: BusinessProfile | None = None
    llm_provider: Literal["anthropic", "openai", "ollama"] | None = None


class ExtractResponse(BaseModel):
    message: str
    process_data: ProcessData | None = None
    needs_input: bool = False
    suggested_questions: list[str] = Field(default_factory=list)
    improvement_suggestions: str | None = None
    is_error: bool = False
    error_code: str | None = None


# ---------------------------------------------------------------------------
# /extract-file  (binary upload handled as form-data by FastAPI)
# ---------------------------------------------------------------------------

# No dedicated request model — file comes in as UploadFile.
# Response reuses ExtractResponse.


# ---------------------------------------------------------------------------
# /sessions
# ---------------------------------------------------------------------------


class RecommendationSummary(BaseModel):
    """Lean recommendation record for the Analysis Library.

    Stores the most useful fields for the Library view without the full
    Recommendation model (which includes verbose arrays).
    """

    title: str
    description: str
    expected_benefit: str
    estimated_roi: str = ""


class AnalysisSessionSummary(BaseModel):
    """Read-only summary of a past analysis session for the Library view."""

    session_id: str
    process_name: str
    process_description: str
    industry: str
    timestamp: str
    step_names: list[str]
    bottlenecks_found: list[str]
    suggestions_offered: list[str]
    suggestions_accepted: list[str]
    suggestions_rejected: list[str]
    recommendations_full: list[RecommendationSummary] = Field(default_factory=list)


class SessionsResponse(BaseModel):
    sessions: list[AnalysisSessionSummary]


# ---------------------------------------------------------------------------
# /continue
# ---------------------------------------------------------------------------


class ContinueRequest(BaseModel):
    thread_id: str
    user_message: str
    analysis_mode: str | None = None


class ContinueResponse(BaseModel):
    message: str
    process_data: ProcessData | None = None
    analysis_insight: AnalysisInsight | None = None
    thread_id: str | None = None
    needs_input: bool = False
    is_error: bool = False
    error_code: str | None = None
