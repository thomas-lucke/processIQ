"""Business profile persistence — one row per user UUID.

Stores industry, company size, constraints, preferences across sessions.
Rejected approaches accumulate over time to prevent re-suggesting them.
"""

import json
import logging
from datetime import UTC, datetime

from processiq.models.memory import (
    BusinessProfile,
    CompanySize,
    Industry,
    RegulatoryEnvironment,
    RevenueRange,
)
from processiq.persistence.db import get_connection

logger = logging.getLogger(__name__)

_SCHEMA_INITIALIZED = False


def _ensure_schema() -> None:
    global _SCHEMA_INITIALIZED
    if _SCHEMA_INITIALIZED:
        return
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS business_profiles (
            user_id       TEXT PRIMARY KEY,
            industry      TEXT,
            custom_industry TEXT DEFAULT '',
            company_size  TEXT,
            revenue_range TEXT DEFAULT 'prefer_not_to_say',
            regulatory_env TEXT DEFAULT 'moderate',
            typical_constraints TEXT DEFAULT '[]',
            preferred_frameworks TEXT DEFAULT '[]',
            previous_improvements TEXT DEFAULT '[]',
            rejected_approaches TEXT DEFAULT '[]',
            notes         TEXT DEFAULT '',
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        )
    """)
    conn.commit()
    _SCHEMA_INITIALIZED = True


def save_profile(user_id: str, profile: BusinessProfile) -> None:
    """Upsert business profile."""
    _ensure_schema()
    conn = get_connection()
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO business_profiles
            (user_id, industry, custom_industry, company_size, revenue_range,
             regulatory_env, typical_constraints, preferred_frameworks,
             previous_improvements, rejected_approaches, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            industry = excluded.industry,
            custom_industry = excluded.custom_industry,
            company_size = excluded.company_size,
            revenue_range = excluded.revenue_range,
            regulatory_env = excluded.regulatory_env,
            typical_constraints = excluded.typical_constraints,
            preferred_frameworks = excluded.preferred_frameworks,
            previous_improvements = excluded.previous_improvements,
            rejected_approaches = excluded.rejected_approaches,
            notes = excluded.notes,
            updated_at = excluded.updated_at
        """,
        (
            user_id,
            profile.industry.value if profile.industry else None,
            profile.custom_industry,
            profile.company_size.value if profile.company_size else None,
            profile.annual_revenue.value,
            profile.regulatory_environment.value,
            json.dumps(profile.typical_constraints),
            json.dumps(profile.preferred_frameworks),
            json.dumps(profile.previous_improvements),
            json.dumps(profile.rejected_approaches),
            profile.notes,
            now,
            now,
        ),
    )
    conn.commit()
    logger.info("Saved profile for user %s", user_id[:8])


def load_profile(user_id: str) -> BusinessProfile | None:
    """Load profile for a returning user. Returns None if not found."""
    _ensure_schema()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM business_profiles WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return None

    return BusinessProfile(
        industry=Industry(row["industry"]) if row["industry"] else None,
        custom_industry=row["custom_industry"] or "",
        company_size=CompanySize(row["company_size"]) if row["company_size"] else None,
        annual_revenue=RevenueRange(row["revenue_range"]),
        regulatory_environment=RegulatoryEnvironment(row["regulatory_env"]),
        typical_constraints=json.loads(row["typical_constraints"]),
        preferred_frameworks=json.loads(row["preferred_frameworks"]),
        previous_improvements=json.loads(row["previous_improvements"]),
        rejected_approaches=json.loads(row["rejected_approaches"]),
        notes=row["notes"] or "",
    )


def delete_profile(user_id: str) -> bool:
    """Delete the business profile for a user. Returns True if a row was deleted."""
    _ensure_schema()
    conn = get_connection()
    cursor = conn.execute("DELETE FROM business_profiles WHERE user_id = ?", (user_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    logger.info("Deleted profile for user %s (found=%s)", user_id[:8], deleted)
    return deleted


def update_rejected_approaches(user_id: str, approaches: list[str]) -> None:
    """Append to rejected_approaches. Deduplicates."""
    _ensure_schema()
    conn = get_connection()
    row = conn.execute(
        "SELECT rejected_approaches FROM business_profiles WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if row is None:
        # No profile yet — create a minimal one
        profile = BusinessProfile(rejected_approaches=approaches)
        save_profile(user_id, profile)
        return

    existing = json.loads(row["rejected_approaches"])
    updated = list(dict.fromkeys(existing + approaches))  # preserve order, dedupe
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "UPDATE business_profiles SET rejected_approaches = ?, updated_at = ? WHERE user_id = ?",
        (json.dumps(updated), now, user_id),
    )
    conn.commit()
    logger.info(
        "Updated rejected approaches for user %s (+%d)", user_id[:8], len(approaches)
    )
