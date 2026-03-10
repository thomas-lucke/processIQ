"""Analysis session persistence — one row per analysis run.

Stores bottlenecks, recommendations, and user feedback for cross-session
pattern detection and the persistent rejection loop.
"""

import json
import logging
from collections import Counter

from processiq.models.memory import AnalysisMemory
from processiq.persistence.db import get_connection

logger = logging.getLogger(__name__)

_SCHEMA_INITIALIZED = False


def _ensure_schema() -> None:
    global _SCHEMA_INITIALIZED
    if _SCHEMA_INITIALIZED:
        return
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analysis_sessions (
            session_id    TEXT PRIMARY KEY,
            user_id       TEXT NOT NULL,
            process_name  TEXT NOT NULL,
            process_description TEXT DEFAULT '',
            industry      TEXT,
            timestamp     TEXT NOT NULL,
            step_names    TEXT DEFAULT '[]',
            bottlenecks   TEXT DEFAULT '[]',
            recommendations TEXT DEFAULT '[]',
            accepted_recs TEXT DEFAULT '[]',
            rejected_recs TEXT DEFAULT '[]',
            rejection_reasons TEXT DEFAULT '[]'
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_user ON analysis_sessions(user_id)"
    )
    conn.commit()
    _SCHEMA_INITIALIZED = True


def save_session(user_id: str, memory: AnalysisMemory) -> None:
    """Save an analysis session after it completes."""
    _ensure_schema()
    conn = get_connection()
    conn.execute(
        """
        INSERT OR REPLACE INTO analysis_sessions
            (session_id, user_id, process_name, process_description, industry,
             timestamp, step_names, bottlenecks, recommendations,
             accepted_recs, rejected_recs, rejection_reasons)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            memory.id,
            user_id,
            memory.process_name,
            memory.process_description,
            memory.industry,
            memory.timestamp.isoformat(),
            json.dumps(memory.step_names),
            json.dumps(memory.bottlenecks_found),
            json.dumps(memory.suggestions_offered),
            json.dumps(memory.suggestions_accepted),
            json.dumps(memory.suggestions_rejected),
            json.dumps(memory.rejection_reasons),
        ),
    )
    conn.commit()
    logger.info(
        "Saved analysis session %s for user %s (process: %s)",
        memory.id[:8],
        user_id[:8],
        memory.process_name,
    )


def update_session_feedback(
    session_id: str,
    accepted: list[str],
    rejected: list[str],
    reasons: list[str],
) -> None:
    """Update feedback on a specific session's recommendations."""
    _ensure_schema()
    conn = get_connection()
    row = conn.execute(
        "SELECT accepted_recs, rejected_recs, rejection_reasons FROM analysis_sessions WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        logger.warning("Session %s not found for feedback update", session_id[:8])
        return

    existing_accepted = json.loads(row["accepted_recs"])
    existing_rejected = json.loads(row["rejected_recs"])
    existing_reasons = json.loads(row["rejection_reasons"])

    updated_accepted = list(dict.fromkeys(existing_accepted + accepted))
    updated_rejected = list(dict.fromkeys(existing_rejected + rejected))
    updated_reasons = existing_reasons + reasons

    conn.execute(
        """
        UPDATE analysis_sessions
        SET accepted_recs = ?, rejected_recs = ?, rejection_reasons = ?
        WHERE session_id = ?
        """,
        (
            json.dumps(updated_accepted),
            json.dumps(updated_rejected),
            json.dumps(updated_reasons),
            session_id,
        ),
    )
    conn.commit()
    logger.info("Updated feedback for session %s", session_id[:8])


def get_user_sessions(user_id: str, limit: int = 20) -> list[AnalysisMemory]:
    """Load past sessions for a user, newest first."""
    _ensure_schema()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM analysis_sessions WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
        (user_id, limit),
    ).fetchall()

    return [
        AnalysisMemory(
            id=row["session_id"],
            user_id=row["user_id"],
            process_name=row["process_name"],
            process_description=row["process_description"] or "",
            industry=row["industry"] or "",
            timestamp=row["timestamp"],
            step_names=json.loads(row["step_names"]),
            bottlenecks_found=json.loads(row["bottlenecks"]),
            suggestions_offered=json.loads(row["recommendations"]),
            suggestions_accepted=json.loads(row["accepted_recs"]),
            suggestions_rejected=json.loads(row["rejected_recs"]),
            rejection_reasons=json.loads(row["rejection_reasons"]),
        )
        for row in rows
    ]


def get_recent_rejections(user_id: str, limit: int = 50) -> list[tuple[str, str]]:
    """Get (recommendation_title, rejection_reason) pairs across all sessions.

    Returns the most recent rejections first, up to `limit`.
    """
    _ensure_schema()
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT rejected_recs, rejection_reasons
        FROM analysis_sessions
        WHERE user_id = ? AND rejected_recs != '[]'
        ORDER BY timestamp DESC
        """,
        (user_id,),
    ).fetchall()

    pairs: list[tuple[str, str]] = []
    for row in rows:
        recs = json.loads(row["rejected_recs"])
        reasons = json.loads(row["rejection_reasons"])
        for rec, reason in zip(recs, reasons, strict=False):
            pairs.append((rec, reason))
            if len(pairs) >= limit:
                return pairs
    return pairs


def delete_user_sessions(user_id: str) -> int:
    """Delete all analysis sessions for a user. Returns number of rows deleted."""
    _ensure_schema()
    conn = get_connection()
    cursor = conn.execute("DELETE FROM analysis_sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    count = cursor.rowcount
    logger.info("Deleted %d analysis sessions for user %s", count, user_id[:8])
    return count


def detect_patterns(user_id: str) -> list[str]:
    """Detect recurring patterns across past analyses.

    Flags bottleneck step names that appear in >50% of analyses.
    Returns plain strings for injection into analyze.j2.
    """
    _ensure_schema()
    conn = get_connection()
    rows = conn.execute(
        "SELECT bottlenecks FROM analysis_sessions WHERE user_id = ? ORDER BY timestamp DESC LIMIT 20",
        (user_id,),
    ).fetchall()

    if len(rows) < 2:
        return []

    total = len(rows)
    bottleneck_counter: Counter[str] = Counter()
    for row in rows:
        # Count each bottleneck once per session (not per occurrence)
        unique_bottlenecks = set(json.loads(row["bottlenecks"]))
        for b in unique_bottlenecks:
            bottleneck_counter[b] += 1

    patterns: list[str] = []
    for bottleneck, count in bottleneck_counter.most_common():
        if count / total > 0.5:
            patterns.append(
                f"'{bottleneck}' has been a bottleneck in {count} of your last "
                f"{total} analyses. This may be an organizational pattern, not "
                f"a process-specific issue."
            )

    if patterns:
        logger.info(
            "Detected %d cross-session patterns for user %s",
            len(patterns),
            user_id[:8],
        )

    return patterns
