"""LangGraph graph construction for ProcessIQ agent.

Builds the stateful graph with nodes, edges, and conditional routing.

Graph flow:
    check_context → (sufficient) → memory_synthesis → initial_analysis → (issues found?) → investigate ↔ tools
                  → (insufficient) → request_clarification → (loop back)          ↓ (no issues / cycle limit)
                                                                               finalize → END
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from processiq.agent.edges import (
    route_after_clarification,
    route_after_context_check,
    route_after_initial_analysis,
    route_investigation,
)
from processiq.agent.nodes import (
    check_context_sufficiency,
    finalize_analysis_node,
    initial_analysis_node,
    investigate_node,
    memory_synthesis_node,
)
from processiq.agent.state import AgentState
from processiq.agent.tools import INVESTIGATION_TOOLS
from processiq.config import TASK_CLARIFICATION, settings

logger = logging.getLogger(__name__)

# Cached compiled graphs (keyed by checkpointer identity)
_compiled_graph_no_cp: Any = None
_compiled_graph_with_cp: dict[int, Any] = {}


def build_graph() -> StateGraph[AgentState]:
    """Build the ProcessIQ analysis graph.

    Graph structure:
    ```
    START
      │
      ▼
    check_context ──────────────────────┐
      │                                 │
      │ (sufficient)                    │ (insufficient)
      ▼                                 ▼
    initial_analysis          request_clarification
      │                                 │
      │ (issues found)                  │ (user responds)
      ▼              ◄──────────────────┘
    investigate ──► tools
      │ (no tool calls / cycle limit)
      ▼
    finalize ──► END
      ▲
      │ (no issues)
      └── initial_analysis
    ```
    """
    logger.info("Building ProcessIQ analysis graph")

    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("check_context", check_context_sufficiency)
    graph.add_node("request_clarification", _request_clarification_node)
    graph.add_node("memory_synthesis", memory_synthesis_node)
    graph.add_node("initial_analysis", initial_analysis_node)
    graph.add_node("investigate", investigate_node)
    graph.add_node("tools", ToolNode(INVESTIGATION_TOOLS))
    graph.add_node("finalize", finalize_analysis_node)

    # Set entry point
    graph.set_entry_point("check_context")

    # Conditional edges
    graph.add_conditional_edges(
        "check_context",
        route_after_context_check,
        {
            "request_clarification": "request_clarification",
            "analyze": "memory_synthesis",
        },
    )

    # memory_synthesis always proceeds to initial_analysis (unconditional)
    graph.add_edge("memory_synthesis", "initial_analysis")

    graph.add_conditional_edges(
        "request_clarification",
        route_after_clarification,
        {
            "check_context": "check_context",
            "analyze": "memory_synthesis",
        },
    )

    graph.add_conditional_edges(
        "initial_analysis",
        route_after_initial_analysis,
        {
            "investigate": "investigate",
            "finalize": "finalize",
        },
    )

    graph.add_conditional_edges(
        "investigate",
        route_investigation,
        {
            "tools": "tools",
            "finalize": "finalize",
        },
    )

    # Tool results loop back to investigate for next LLM decision turn
    graph.add_edge("tools", "investigate")
    graph.add_edge("finalize", END)

    logger.info("Graph built successfully")
    return graph


def compile_graph(checkpointer: Any = None) -> Any:
    """Compile the graph for execution, with caching.

    The graph structure is deterministic so compilation is cached.
    One cached graph per unique checkpointer instance.

    Args:
        checkpointer: Optional checkpointer for state persistence.
                     Use MemorySaver for development, SqliteSaver for production.

    Returns:
        Compiled graph ready for invocation.
    """
    global _compiled_graph_no_cp

    if checkpointer is None:
        if _compiled_graph_no_cp is not None:
            logger.debug("Reusing cached compiled graph (no checkpointer)")
            return _compiled_graph_no_cp
        graph = build_graph()
        logger.info("Compiling graph without checkpointer (first time)")
        _compiled_graph_no_cp = graph.compile()
        return _compiled_graph_no_cp

    cp_id = id(checkpointer)
    if cp_id in _compiled_graph_with_cp:
        logger.debug("Reusing cached compiled graph (checkpointer=%d)", cp_id)
        return _compiled_graph_with_cp[cp_id]

    graph = build_graph()
    logger.info("Compiling graph with checkpointer (first time)")
    compiled = graph.compile(checkpointer=checkpointer)
    _compiled_graph_with_cp[cp_id] = compiled
    return compiled


def _generate_llm_clarification_questions(
    confidence: float,
    data_gaps: list[str],
    phase: str,
    partial_results: list[str] | None = None,
    analysis_mode: str | None = None,
    llm_provider: str | None = None,
) -> list[str] | None:
    """Generate clarification questions using LLM.

    Returns None if LLM is disabled or fails (caller should use fallback).
    """
    if not settings.llm_explanations_enabled:
        return None

    try:
        from processiq.llm import get_chat_model
        from processiq.prompts import get_clarification_prompt, get_system_prompt

        model = get_chat_model(
            task=TASK_CLARIFICATION,
            analysis_mode=analysis_mode,
            provider=llm_provider,
        )

        system_msg = get_system_prompt()
        user_msg = get_clarification_prompt(
            confidence=confidence,
            phase=phase,
            data_gaps=data_gaps,
            partial_results=partial_results,
        )

        logger.debug("Generating LLM clarification questions")
        response = model.invoke(
            [
                SystemMessage(content=system_msg),
                HumanMessage(content=user_msg),
            ]
        )

        # Parse response into list of questions
        from processiq.llm import extract_text_content

        content = extract_text_content(response)

        # Simple parsing: split by numbered lines
        questions: list[str] = []
        for line in content.split("\n"):
            line = line.strip()
            if line and len(line) > 2 and line[0].isdigit() and line[1] in ".):":
                questions.append(line[2:].strip())
            elif line and line.startswith("-"):
                questions.append(line[1:].strip())

        if questions:
            logger.info("LLM generated %d clarification questions", len(questions))
            return questions[:3]
        logger.warning("Could not parse LLM response into questions, using as-is")
        return [content]

    except Exception as e:
        logger.warning("LLM clarification question generation failed: %s", e)
        return None


def _request_clarification_node(state: AgentState) -> dict[str, Any]:
    """Node: Request clarification from user.

    Uses LLM to generate contextual clarification questions when enabled.
    """
    logger.info("Node: request_clarification - awaiting user input")

    confidence = state.get("confidence_score", 0.5)
    data_gaps = state.get("data_gaps", [])
    existing_questions = state.get("clarification_questions", [])

    # Try LLM for better questions
    llm_questions = _generate_llm_clarification_questions(
        confidence=confidence,
        data_gaps=data_gaps,
        phase="initial_analysis",
        partial_results=None,
        analysis_mode=state.get("analysis_mode"),
        llm_provider=state.get("llm_provider"),
    )

    used_llm = llm_questions is not None

    # Use LLM questions if available, otherwise fall back to template
    if llm_questions:
        formatted_questions = llm_questions
    elif existing_questions:
        formatted_questions = existing_questions
    else:
        formatted_questions = [f"Please provide: {gap}" for gap in data_gaps[:3]]

    reasoning = f"Requesting clarification: {len(formatted_questions)} questions"
    if used_llm:
        reasoning += " (LLM generated)"

    return {
        "clarification_questions": formatted_questions,
        "reasoning_trace": [*state.get("reasoning_trace", []), reasoning],
        "current_phase": "awaiting_input",
    }
