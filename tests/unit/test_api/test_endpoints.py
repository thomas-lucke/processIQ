"""Tests for FastAPI endpoints in api/main.py.

All interface.py calls are mocked — these tests verify routing, request
validation, response shape, and error handling, not business logic.
"""

from unittest.mock import MagicMock, patch

import pytest
from api.main import app
from fastapi.testclient import TestClient

from processiq.models import ProcessData, ProcessStep

client = TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_process_payload() -> dict:
    return {
        "process": {
            "name": "Test Process",
            "steps": [
                {
                    "step_name": "Step A",
                    "average_time_hours": 1.0,
                    "resources_needed": 1,
                }
            ],
        }
    }


@pytest.fixture
def mock_analyze_result() -> MagicMock:
    result = MagicMock()
    result.message = "Analysis complete"
    result.analysis_insight = None
    result.thread_id = "thread-abc"
    result.is_error = False
    result.error_code = None
    result.reasoning_trace = []
    result.process_data = ProcessData(
        name="Test Process",
        steps=[
            ProcessStep(step_name="Step A", average_time_hours=1.0, resources_needed=1)
        ],
    )
    return result


@pytest.fixture
def mock_extract_result() -> MagicMock:
    result = MagicMock()
    result.message = "Please describe your process."
    result.process_data = None
    result.needs_input = True
    result.suggested_questions = ["How many steps?"]
    result.improvement_suggestions = None
    result.is_error = False
    result.error_code = None
    return result


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /analyze
# ---------------------------------------------------------------------------


class TestAnalyze:
    def test_valid_request_returns_200(
        self, minimal_process_payload, mock_analyze_result
    ):
        with patch(
            "api.main.interface.analyze_process", return_value=mock_analyze_result
        ):
            response = client.post("/analyze", json=minimal_process_payload)
        assert response.status_code == 200

    def test_response_shape(self, minimal_process_payload, mock_analyze_result):
        with patch(
            "api.main.interface.analyze_process", return_value=mock_analyze_result
        ):
            response = client.post("/analyze", json=minimal_process_payload)
        data = response.json()
        assert "message" in data
        assert "is_error" in data
        assert "thread_id" in data

    def test_description_too_long_returns_422(self):
        payload = {
            "process": {
                "name": "Test",
                "description": "x" * 5001,
                "steps": [
                    {"step_name": "A", "average_time_hours": 1.0, "resources_needed": 1}
                ],
            }
        }
        response = client.post("/analyze", json=payload)
        assert response.status_code == 422

    def test_missing_process_returns_422(self):
        response = client.post("/analyze", json={})
        assert response.status_code == 422

    def test_ollama_disabled_returns_400(self, minimal_process_payload):
        minimal_process_payload["llm_provider"] = "ollama"
        with patch("api.main.settings.ollama_enabled", False):
            response = client.post("/analyze", json=minimal_process_payload)
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# /extract
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_valid_request_returns_200(self, mock_extract_result):
        with patch(
            "api.main.interface.extract_from_text", return_value=mock_extract_result
        ):
            response = client.post(
                "/extract", json={"text": "We have a 3-step hiring process."}
            )
        assert response.status_code == 200

    def test_response_shape(self, mock_extract_result):
        with patch(
            "api.main.interface.extract_from_text", return_value=mock_extract_result
        ):
            response = client.post("/extract", json={"text": "Some process"})
        data = response.json()
        assert "message" in data
        assert "needs_input" in data
        assert "is_error" in data

    def test_text_too_long_returns_422(self):
        response = client.post("/extract", json={"text": "x" * 10_001})
        assert response.status_code == 422

    def test_missing_text_returns_422(self):
        response = client.post("/extract", json={})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# /continue
# ---------------------------------------------------------------------------


class TestContinueConversation:
    def test_valid_request_returns_200(self):
        mock_result = MagicMock()
        mock_result.message = "Got it."
        mock_result.process_data = None
        mock_result.analysis_insight = None
        mock_result.thread_id = "thread-abc"
        mock_result.needs_input = False
        mock_result.is_error = False
        mock_result.error_code = None

        with patch(
            "api.main.interface.continue_conversation", return_value=mock_result
        ):
            response = client.post(
                "/continue",
                json={"thread_id": "thread-abc", "user_message": "Add another step"},
            )
        assert response.status_code == 200

    def test_message_too_long_returns_422(self):
        response = client.post(
            "/continue",
            json={"thread_id": "t", "user_message": "x" * 10_001},
        )
        assert response.status_code == 422

    def test_missing_thread_id_returns_422(self):
        response = client.post("/continue", json={"user_message": "hello"})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# /graph-schema/{thread_id}
# ---------------------------------------------------------------------------


class TestGraphSchema:
    def test_unknown_thread_returns_404(self):
        response = client.get("/graph-schema/nonexistent-thread")
        assert response.status_code == 404

    def test_known_thread_returns_graph(self, mock_analyze_result):
        with patch(
            "api.main.interface.analyze_process", return_value=mock_analyze_result
        ):
            client.post(
                "/analyze",
                json={
                    "process": {
                        "name": "Test",
                        "steps": [
                            {
                                "step_name": "Step A",
                                "average_time_hours": 1.0,
                                "resources_needed": 1,
                            }
                        ],
                    },
                    "thread_id": "thread-abc",
                },
            )

        response = client.get("/graph-schema/thread-abc")
        assert response.status_code == 200
        data = response.json()
        assert "before_nodes" in data
        assert "after_nodes" in data
        assert "edges" in data
