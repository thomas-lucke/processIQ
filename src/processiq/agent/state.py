"""LangGraph agent state definition for ProcessIQ.

Uses TypedDict for better performance in state passing between nodes.
"""

from typing import Annotated, Any

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from processiq.models import (
    AnalysisInsight,
    BusinessProfile,
    Constraints,
    ProcessData,
)


class AgentState(TypedDict, total=False):
    """State passed between LangGraph nodes.

    Using TypedDict (not Pydantic) for LangGraph performance.
    Fields marked total=False are optional.
    """

    # Input data
    process: ProcessData
    constraints: Constraints | None
    profile: BusinessProfile | None

    # Analysis results
    analysis_insight: AnalysisInsight | None

    # Confidence and data quality
    confidence_score: float
    data_gaps: list[str]

    # Agent reasoning and decisions
    messages: Annotated[list[Any], add_messages]  # Conversation history
    reasoning_trace: list[str]  # Log of agent decisions
    current_phase: str  # Current execution phase

    # Control flow
    needs_clarification: bool
    clarification_questions: list[str]
    user_response: str | None

    # Error handling
    error: str | None

    # LLM configuration (passed from API layer)
    analysis_mode: str | None
    llm_provider: str | None

    # User feedback on recommendations (for self-improving analysis)
    feedback_history: dict[str, dict[str, object]]

    # Agentic investigation loop
    process_metrics: Any | None  # ProcessMetrics — cached from initial_analysis_node
    cycle_count: int  # LLM decision turns completed
    max_cycles_override: (
        int | None
    )  # from UI slider; None = use settings.agent_max_cycles

    # Persistent memory context (RAG)
    similar_past_analyses: list[dict[str, Any]]  # from ChromaDB retrieval
    persistent_rejections: list[tuple[str, str]]  # (rec_title, reason) across sessions
    cross_session_patterns: list[str]  # detected recurring patterns
    memory_brief: (
        str | None
    )  # Pre-synthesised memory context from memory_synthesis_node


# Initial state factory
def create_initial_state(
    process: ProcessData,
    constraints: Constraints | None = None,
    profile: BusinessProfile | None = None,
    analysis_mode: str | None = None,
    llm_provider: str | None = None,
    feedback_history: dict[str, dict[str, object]] | None = None,
    max_cycles_override: int | None = None,
    similar_past_analyses: list[dict[str, Any]] | None = None,
    persistent_rejections: list[tuple[str, str]] | None = None,
    cross_session_patterns: list[str] | None = None,
) -> AgentState:
    """Create initial agent state with required fields."""
    return AgentState(
        process=process,
        constraints=constraints,
        profile=profile,
        analysis_insight=None,
        confidence_score=0.0,
        data_gaps=[],
        messages=[],
        reasoning_trace=[],
        current_phase="initialization",
        needs_clarification=False,
        clarification_questions=[],
        user_response=None,
        error=None,
        analysis_mode=analysis_mode,
        llm_provider=llm_provider,
        feedback_history=feedback_history or {},
        process_metrics=None,
        cycle_count=0,
        max_cycles_override=max_cycles_override,
        similar_past_analyses=similar_past_analyses or [],
        persistent_rejections=persistent_rejections or [],
        cross_session_patterns=cross_session_patterns or [],
        memory_brief=None,
    )
