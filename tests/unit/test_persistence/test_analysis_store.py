"""Tests for processiq.persistence.analysis_store.

Uses an in-memory SQLite database injected via monkeypatch.
"""

import sqlite3
import uuid
from datetime import UTC, datetime

import pytest

from processiq.models.memory import AnalysisMemory

# ---------------------------------------------------------------------------
# Fixture: isolated in-memory DB
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    """Replace get_connection with an in-memory SQLite connection for each test."""
    import processiq.persistence.analysis_store as store_module

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row

    monkeypatch.setattr(store_module, "_SCHEMA_INITIALIZED", False)
    monkeypatch.setattr(
        "processiq.persistence.analysis_store.get_connection", lambda: conn
    )
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_memory(
    process_name: str = "Test Process",
    bottlenecks: list[str] | None = None,
    rejected: list[str] | None = None,
    reasons: list[str] | None = None,
) -> AnalysisMemory:
    return AnalysisMemory(
        id=str(uuid.uuid4()),
        process_name=process_name,
        process_description="A test process",
        industry="technology",
        timestamp=datetime.now(UTC),
        step_names=["Step A", "Step B"],
        bottlenecks_found=bottlenecks or [],
        suggestions_offered=["Suggestion 1"],
        suggestions_accepted=[],
        suggestions_rejected=rejected or [],
        rejection_reasons=reasons or [],
    )


# ---------------------------------------------------------------------------
# save_session / get_user_sessions
# ---------------------------------------------------------------------------


class TestSaveAndGetSessions:
    def test_no_sessions_returns_empty_list(self):
        from processiq.persistence.analysis_store import get_user_sessions

        assert get_user_sessions("user-1") == []

    def test_save_then_retrieve(self):
        from processiq.persistence.analysis_store import get_user_sessions, save_session

        memory = _make_memory("Hiring Process")
        save_session("user-1", memory)

        sessions = get_user_sessions("user-1")
        assert len(sessions) == 1
        assert sessions[0].process_name == "Hiring Process"

    def test_sessions_scoped_to_user(self):
        from processiq.persistence.analysis_store import get_user_sessions, save_session

        save_session("user-1", _make_memory("Process A"))
        save_session("user-2", _make_memory("Process B"))

        assert len(get_user_sessions("user-1")) == 1
        assert len(get_user_sessions("user-2")) == 1

    def test_multiple_sessions_all_returned(self):
        from processiq.persistence.analysis_store import get_user_sessions, save_session

        save_session("user-1", _make_memory("Process A"))
        save_session("user-1", _make_memory("Process B"))
        save_session("user-1", _make_memory("Process C"))

        sessions = get_user_sessions("user-1")
        assert len(sessions) == 3
        names = {s.process_name for s in sessions}
        assert names == {"Process A", "Process B", "Process C"}

    def test_limit_respected(self):
        from processiq.persistence.analysis_store import get_user_sessions, save_session

        for i in range(5):
            save_session("user-1", _make_memory(f"Process {i}"))

        sessions = get_user_sessions("user-1", limit=3)
        assert len(sessions) == 3


# ---------------------------------------------------------------------------
# update_session_feedback
# ---------------------------------------------------------------------------


class TestUpdateSessionFeedback:
    def test_update_accepted_and_rejected(self):
        from processiq.persistence.analysis_store import (
            get_user_sessions,
            save_session,
            update_session_feedback,
        )

        memory = _make_memory()
        save_session("user-1", memory)
        update_session_feedback(
            session_id=memory.id,
            accepted=["Suggestion 1"],
            rejected=["Suggestion 2"],
            reasons=["Too expensive"],
        )

        sessions = get_user_sessions("user-1")
        assert "Suggestion 1" in sessions[0].suggestions_accepted
        assert "Suggestion 2" in sessions[0].suggestions_rejected

    def test_update_nonexistent_session_does_not_raise(self):
        from processiq.persistence.analysis_store import update_session_feedback

        # Should log a warning and return gracefully
        update_session_feedback(
            session_id="nonexistent",
            accepted=["X"],
            rejected=[],
            reasons=[],
        )


# ---------------------------------------------------------------------------
# get_recent_rejections
# ---------------------------------------------------------------------------


class TestGetRecentRejections:
    def test_returns_empty_for_no_sessions(self):
        from processiq.persistence.analysis_store import get_recent_rejections

        assert get_recent_rejections("user-1") == []

    def test_returns_rejection_reason_pairs(self):
        from processiq.persistence.analysis_store import (
            get_recent_rejections,
            save_session,
            update_session_feedback,
        )

        memory = _make_memory()
        save_session("user-1", memory)
        update_session_feedback(
            session_id=memory.id,
            accepted=[],
            rejected=["Automate everything"],
            reasons=["Too risky"],
        )

        pairs = get_recent_rejections("user-1")
        assert len(pairs) == 1
        assert pairs[0][0] == "Automate everything"
        assert pairs[0][1] == "Too risky"


# ---------------------------------------------------------------------------
# detect_patterns
# ---------------------------------------------------------------------------


class TestDetectPatterns:
    def test_no_patterns_for_single_session(self):
        from processiq.persistence.analysis_store import detect_patterns, save_session

        save_session("user-1", _make_memory(bottlenecks=["Approval step"]))
        assert detect_patterns("user-1") == []

    def test_recurring_bottleneck_detected(self):
        from processiq.persistence.analysis_store import detect_patterns, save_session

        for _ in range(3):
            save_session("user-1", _make_memory(bottlenecks=["Approval step"]))

        patterns = detect_patterns("user-1")
        assert len(patterns) == 1
        assert "Approval step" in patterns[0]

    def test_non_recurring_bottleneck_not_flagged(self):
        from processiq.persistence.analysis_store import detect_patterns, save_session

        save_session("user-1", _make_memory(bottlenecks=["Step A"]))
        save_session("user-1", _make_memory(bottlenecks=["Step B"]))
        save_session("user-1", _make_memory(bottlenecks=["Step C"]))

        # Each bottleneck appears in only 1/3 sessions — below the 50% threshold
        patterns = detect_patterns("user-1")
        assert patterns == []


# ---------------------------------------------------------------------------
# delete_user_sessions
# ---------------------------------------------------------------------------


class TestDeleteUserSessions:
    def test_deletes_all_sessions_for_user(self):
        from processiq.persistence.analysis_store import (
            delete_user_sessions,
            get_user_sessions,
            save_session,
        )

        save_session("user-1", _make_memory("P1"))
        save_session("user-1", _make_memory("P2"))
        delete_user_sessions("user-1")

        assert get_user_sessions("user-1") == []

    def test_does_not_delete_other_users_sessions(self):
        from processiq.persistence.analysis_store import (
            delete_user_sessions,
            get_user_sessions,
            save_session,
        )

        save_session("user-1", _make_memory("P1"))
        save_session("user-2", _make_memory("P2"))
        delete_user_sessions("user-1")

        assert len(get_user_sessions("user-2")) == 1

    def test_returns_count_of_deleted_rows(self):
        from processiq.persistence.analysis_store import (
            delete_user_sessions,
            save_session,
        )

        save_session("user-1", _make_memory("P1"))
        save_session("user-1", _make_memory("P2"))

        assert delete_user_sessions("user-1") == 2
