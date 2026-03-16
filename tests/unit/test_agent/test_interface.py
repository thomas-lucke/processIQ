"""Tests for processiq.agent.interface.

Strategy: mock at the boundary (normalize_with_llm, compile_graph) to test
routing and response-shaping logic without real LLM calls or graph execution.
"""

from unittest.mock import MagicMock, patch

from processiq.agent.interface import (
    AgentResponse,
    analyze_process,
    continue_conversation,
    extract_from_text,
)
from processiq.exceptions import ExtractionError
from processiq.ingestion.normalizer import (
    ClarificationNeeded,
    ExtractionResponse,
    ExtractionResult,
)
from processiq.models import AnalysisInsight

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extraction_result(process_name: str = "Test Process") -> ExtractionResult:
    """Minimal ExtractionResult with one step."""
    from processiq.ingestion.normalizer import ExtractedStep

    return ExtractionResult(
        process_name=process_name,
        steps=[
            ExtractedStep(
                step_name="Step A", average_time_hours=1.0, resources_needed=1
            )
        ],
    )


def _make_extraction_response(process_name: str = "Test Process") -> ExtractionResponse:
    """ExtractionResponse for a successful extraction."""
    return ExtractionResponse(
        response_type="extracted",
        extraction=_make_extraction_result(process_name),
    )


def _make_clarification_response() -> ExtractionResponse:
    """ExtractionResponse requesting clarification."""
    clarification = ClarificationNeeded(
        message="Could you tell me more about your process?",
        detected_intent="some process",
        clarifying_questions=["How many steps?", "How long does each step take?"],
        why_more_info_needed="Input was too vague to extract structured data.",
    )
    return ExtractionResponse(
        response_type="needs_clarification",
        clarification=clarification,
    )


def _make_graph_result(insight: AnalysisInsight) -> dict:
    """Fake LangGraph invoke result with a completed analysis."""
    return {
        "analysis_insight": insight,
        "reasoning_trace": ["Checked context", "Ran analysis"],
        "needs_clarification": False,
        "clarification_questions": [],
        "error": "",
    }


# ---------------------------------------------------------------------------
# AgentResponse properties
# ---------------------------------------------------------------------------


class TestAgentResponseProperties:
    def test_has_data_true_when_process_data_set(self, simple_process):
        resp = AgentResponse(message="ok", process_data=simple_process)
        assert resp.has_data is True

    def test_has_data_false_when_no_process_data(self):
        resp = AgentResponse(message="ok")
        assert resp.has_data is False

    def test_has_analysis_true_when_insight_set(self, sample_insight):
        resp = AgentResponse(message="ok", analysis_insight=sample_insight)
        assert resp.has_analysis is True

    def test_has_analysis_false_when_no_insight(self):
        resp = AgentResponse(message="ok")
        assert resp.has_analysis is False

    def test_needs_clarification_true_when_both_set(self):
        clarification = ClarificationNeeded(
            message="Tell me more.",
            detected_intent="something",
            clarifying_questions=["q1"],
            why_more_info_needed="not enough info",
        )
        resp = AgentResponse(
            message="ok", needs_input=True, clarification_context=clarification
        )
        assert resp.needs_clarification is True

    def test_needs_clarification_false_when_no_context(self):
        resp = AgentResponse(message="ok", needs_input=True)
        assert resp.needs_clarification is False

    def test_extraction_warnings_returns_list_from_result(self):
        from processiq.ingestion.normalizer import ExtractedStep

        extraction = ExtractionResult(
            steps=[
                ExtractedStep(
                    step_name="Step A", average_time_hours=1.0, resources_needed=1
                )
            ],
            warnings=["Missing cost data"],
        )
        resp = AgentResponse(message="ok", extraction_result=extraction)
        assert resp.extraction_warnings == ["Missing cost data"]

    def test_extraction_warnings_empty_when_no_result(self):
        resp = AgentResponse(message="ok")
        assert resp.extraction_warnings == []


# ---------------------------------------------------------------------------
# extract_from_text — guard clauses (no mocking needed)
# ---------------------------------------------------------------------------


class TestExtractFromTextGuards:
    def test_empty_string_returns_error(self):
        resp = extract_from_text("")
        assert resp.is_error is True
        assert resp.error_code == "empty_input"
        assert resp.needs_input is True

    def test_whitespace_only_returns_error(self):
        resp = extract_from_text("   \n\t  ")
        assert resp.is_error is True
        assert resp.error_code == "empty_input"


# ---------------------------------------------------------------------------
# extract_from_text — LLM paths (normalize_with_llm mocked)
# ---------------------------------------------------------------------------


class TestExtractFromTextLLMPaths:
    @patch(
        "processiq.agent.interface._generate_improvement_suggestions", return_value=None
    )
    @patch("processiq.agent.interface.normalize_with_llm")
    def test_successful_extraction_returns_process_data_and_confidence(
        self, mock_normalize, mock_suggestions, simple_process
    ):
        mock_normalize.return_value = (simple_process, _make_extraction_response())

        resp = extract_from_text("Our onboarding process has three steps...")

        assert resp.is_error is False
        assert resp.process_data is not None
        assert resp.needs_input is True  # awaiting user confirmation
        assert resp.has_data is True
        assert resp.confidence is not None

    @patch("processiq.agent.interface.normalize_with_llm")
    def test_clarification_response_sets_needs_input_and_questions(
        self, mock_normalize
    ):
        mock_normalize.return_value = (None, _make_clarification_response())

        resp = extract_from_text("I have a process")

        assert resp.needs_input is True
        assert resp.is_error is False
        assert resp.clarification_context is not None
        assert resp.needs_clarification is True
        assert len(resp.suggested_questions) > 0

    @patch(
        "processiq.agent.interface._generate_improvement_suggestions", return_value=None
    )
    @patch("processiq.agent.interface.normalize_with_llm")
    def test_no_data_no_clarification_returns_needs_more_detail(
        self, mock_normalize, mock_suggestions
    ):
        """When LLM returns extracted but process_data is None, prompt for more info."""
        resp_obj = _make_extraction_response()
        mock_normalize.return_value = (None, resp_obj)
        # Override response_type so neither branch triggers, forcing the fallthrough
        resp_obj.response_type = "extracted"
        resp_obj.extraction = None

        resp = extract_from_text("Something vague")

        assert resp.is_error is False
        assert resp.error_code == "needs_more_detail"
        assert resp.needs_input is True

    @patch("processiq.agent.interface.normalize_with_llm")
    def test_extraction_error_returns_error_response(self, mock_normalize):
        mock_normalize.side_effect = ExtractionError(
            message="LLM failed",
            source="normalizer",
            user_message="Could not extract process data.",
        )

        resp = extract_from_text("Some process description")

        assert resp.is_error is True
        assert resp.error_code == "extraction_failed"
        assert "Could not extract" in resp.message

    @patch("processiq.agent.interface.normalize_with_llm")
    def test_unexpected_exception_returns_error_response(self, mock_normalize):
        mock_normalize.side_effect = RuntimeError("Unexpected boom")

        resp = extract_from_text("Some process description")

        assert resp.is_error is True
        assert resp.error_code == "unexpected_error"

    @patch(
        "processiq.agent.interface._generate_improvement_suggestions",
        return_value="Add cost data.",
    )
    @patch("processiq.agent.interface.normalize_with_llm")
    def test_improvement_suggestions_attached_when_generated(
        self, mock_normalize, mock_suggestions, simple_process
    ):
        mock_normalize.return_value = (simple_process, _make_extraction_response())

        resp = extract_from_text("Three step process")

        # Verify the function was actually called (not bypassed) and its result attached
        mock_suggestions.assert_called_once()
        assert resp.improvement_suggestions == "Add cost data."

    @patch(
        "processiq.agent.interface._generate_improvement_suggestions", return_value=None
    )
    @patch("processiq.agent.interface.normalize_with_llm")
    def test_improvement_suggestions_none_when_not_generated(
        self, mock_normalize, mock_suggestions, simple_process
    ):
        mock_normalize.return_value = (simple_process, _make_extraction_response())

        resp = extract_from_text("Three step process")

        assert resp.improvement_suggestions is None


# ---------------------------------------------------------------------------
# analyze_process — graph execution paths
# ---------------------------------------------------------------------------


class TestAnalyzeProcess:
    @patch("processiq.agent.interface.get_checkpointer", return_value=None)
    @patch("processiq.agent.interface.compile_graph")
    def test_happy_path_returns_analysis(
        self, mock_compile, mock_checkpointer, simple_process, sample_insight
    ):
        mock_app = MagicMock()
        mock_app.invoke.return_value = _make_graph_result(sample_insight)
        mock_compile.return_value = mock_app

        resp = analyze_process(simple_process)

        assert resp.is_error is False
        assert resp.has_analysis is True
        assert resp.analysis_insight is sample_insight

    @patch("processiq.agent.interface.get_checkpointer", return_value=None)
    @patch("processiq.agent.interface.compile_graph")
    def test_happy_path_populates_confidence(
        self, mock_compile, mock_checkpointer, simple_process, sample_insight
    ):
        mock_app = MagicMock()
        mock_app.invoke.return_value = _make_graph_result(sample_insight)
        mock_compile.return_value = mock_app

        resp = analyze_process(simple_process)

        assert resp.confidence is not None

    @patch("processiq.agent.interface.get_checkpointer", return_value=None)
    @patch("processiq.agent.interface.compile_graph")
    def test_thread_id_generated_when_not_provided(
        self, mock_compile, mock_checkpointer, simple_process, sample_insight
    ):
        import re

        mock_app = MagicMock()
        mock_app.invoke.return_value = _make_graph_result(sample_insight)
        mock_compile.return_value = mock_app

        resp = analyze_process(simple_process)

        # Should be a valid UUID v4
        assert resp.thread_id is not None
        assert re.match(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
            resp.thread_id,
        )

    @patch("processiq.agent.interface.get_checkpointer", return_value=None)
    @patch("processiq.agent.interface.compile_graph")
    def test_thread_id_preserved_when_provided(
        self, mock_compile, mock_checkpointer, simple_process, sample_insight
    ):
        mock_app = MagicMock()
        mock_app.invoke.return_value = _make_graph_result(sample_insight)
        mock_compile.return_value = mock_app

        resp = analyze_process(simple_process, thread_id="my-thread-123")

        assert resp.thread_id == "my-thread-123"

    @patch("processiq.agent.interface.get_checkpointer", return_value=None)
    @patch("processiq.agent.interface.compile_graph")
    def test_clarification_request_from_graph(
        self, mock_compile, mock_checkpointer, simple_process
    ):
        mock_app = MagicMock()
        mock_app.invoke.return_value = {
            "analysis_insight": None,
            "reasoning_trace": [],
            "needs_clarification": True,
            "clarification_questions": ["What is the error rate?"],
            "error": "",
        }
        mock_compile.return_value = mock_app

        resp = analyze_process(simple_process)

        assert resp.needs_input is True
        assert "What is the error rate?" in resp.suggested_questions
        assert resp.is_error is False

    @patch("processiq.agent.interface.get_checkpointer", return_value=None)
    @patch("processiq.agent.interface.compile_graph")
    def test_no_insight_no_error_returns_fallback_message(
        self, mock_compile, mock_checkpointer, simple_process
    ):
        mock_app = MagicMock()
        mock_app.invoke.return_value = {
            "analysis_insight": None,
            "reasoning_trace": [],
            "needs_clarification": False,
            "clarification_questions": [],
            "error": "",
        }
        mock_compile.return_value = mock_app

        resp = analyze_process(simple_process)

        # No insight means is_error=True with error_code="no_results" per source
        assert resp.is_error is True
        assert resp.error_code == "no_results"
        assert (
            "try again" in resp.message.lower() or "could not" in resp.message.lower()
        )

    @patch("processiq.agent.interface.get_checkpointer", return_value=None)
    @patch("processiq.agent.interface.compile_graph")
    def test_graph_exception_returns_error_response(
        self, mock_compile, mock_checkpointer, simple_process
    ):
        # Raise inside invoke (the actual try block), not at compile time
        mock_app = MagicMock()
        mock_app.invoke.side_effect = RuntimeError("Graph blew up")
        mock_compile.return_value = mock_app

        resp = analyze_process(simple_process)

        assert resp.is_error is True
        assert resp.error_code == "unexpected_error"

    @patch("processiq.agent.interface.get_checkpointer", return_value=None)
    @patch("processiq.agent.interface.compile_graph")
    def test_reasoning_trace_attached(
        self, mock_compile, mock_checkpointer, simple_process, sample_insight
    ):
        mock_app = MagicMock()
        mock_app.invoke.return_value = _make_graph_result(sample_insight)
        mock_compile.return_value = mock_app

        resp = analyze_process(simple_process)

        assert resp.reasoning_trace == ["Checked context", "Ran analysis"]

    @patch("processiq.agent.interface.get_checkpointer", return_value=None)
    @patch("processiq.agent.interface.compile_graph")
    def test_timeout_error_state_returns_message(
        self, mock_compile, mock_checkpointer, simple_process
    ):
        mock_app = MagicMock()
        mock_app.invoke.return_value = {
            "analysis_insight": None,
            "reasoning_trace": [],
            "needs_clarification": False,
            "clarification_questions": [],
            "error": "timeout",
        }
        mock_compile.return_value = mock_app

        resp = analyze_process(simple_process)

        assert "timeout" in resp.message.lower() or "time limit" in resp.message.lower()


# ---------------------------------------------------------------------------
# continue_conversation — routing logic
# ---------------------------------------------------------------------------


class TestContinueConversation:
    def test_empty_message_returns_error(self):
        resp = continue_conversation(thread_id="t1", user_message="")
        assert resp.is_error is True
        assert resp.error_code == "empty_input"
        assert resp.thread_id == "t1"

    def test_whitespace_message_returns_error(self):
        resp = continue_conversation(thread_id="t1", user_message="   ")
        assert resp.is_error is True
        assert resp.error_code == "empty_input"

    @patch("processiq.agent.interface.get_checkpointer", return_value=None)
    @patch(
        "processiq.agent.interface._generate_improvement_suggestions", return_value=None
    )
    @patch("processiq.agent.interface.normalize_with_llm")
    def test_no_checkpointer_falls_back_to_extraction(
        self, mock_normalize, mock_suggestions, mock_checkpointer, simple_process
    ):
        """When persistence is disabled, falls back to extract_from_text."""
        mock_normalize.return_value = (simple_process, _make_extraction_response())

        resp = continue_conversation(
            thread_id="t1", user_message="Our process has 3 steps"
        )

        assert resp.is_error is False
        assert resp.has_data is True

    @patch("processiq.agent.interface.extract_from_file")
    def test_file_upload_delegates_to_extract_from_file(self, mock_extract):
        mock_extract.return_value = AgentResponse(message="Extracted from file")

        resp = continue_conversation(
            thread_id="t1",
            user_message="",
            file_bytes=b"col1,col2\nA,B",
            filename="process.csv",
        )

        mock_extract.assert_called_once()
        assert resp.message == "Extracted from file"

    @patch("processiq.agent.interface.get_checkpointer")
    def test_checkpointer_error_falls_back_to_extraction(self, mock_get_checkpointer):
        """If checkpointer raises during get(), fall back gracefully."""
        mock_checkpointer = MagicMock()
        mock_checkpointer.get.side_effect = RuntimeError("DB unavailable")
        mock_get_checkpointer.return_value = mock_checkpointer

        with patch("processiq.agent.interface.extract_from_text") as mock_extract:
            mock_extract.return_value = AgentResponse(message="fallback")
            resp = continue_conversation(thread_id="t1", user_message="hello")

        assert resp.message == "fallback"

    @patch("processiq.agent.interface.get_checkpointer")
    def test_no_checkpoint_found_starts_fresh(self, mock_get_checkpointer):
        """Thread ID with no saved state falls back to extract_from_text."""
        mock_checkpointer = MagicMock()
        mock_checkpointer.get.return_value = None
        mock_get_checkpointer.return_value = mock_checkpointer

        with patch("processiq.agent.interface.extract_from_text") as mock_extract:
            mock_extract.return_value = AgentResponse(message="fresh start")
            resp = continue_conversation(thread_id="t1", user_message="hello")

        assert resp.message == "fresh start"
