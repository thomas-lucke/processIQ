"""Tests for processiq.persistence.profile_store.

Uses an in-memory SQLite database injected via monkeypatch — no disk I/O,
no cross-test state.
"""

import sqlite3

import pytest

from processiq.models.memory import (
    BusinessProfile,
    CompanySize,
    Industry,
    RegulatoryEnvironment,
    RevenueRange,
)

# ---------------------------------------------------------------------------
# Fixture: isolated in-memory DB injected into the module under test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    """Replace get_connection with an in-memory SQLite connection for each test."""
    import processiq.persistence.profile_store as store_module

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row

    monkeypatch.setattr(store_module, "_SCHEMA_INITIALIZED", False)
    monkeypatch.setattr(
        "processiq.persistence.profile_store.get_connection", lambda: conn
    )
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# save_profile / load_profile
# ---------------------------------------------------------------------------


class TestSaveAndLoad:
    def test_load_returns_none_for_unknown_user(self):
        from processiq.persistence.profile_store import load_profile

        assert load_profile("unknown-user") is None

    def test_save_then_load_roundtrip(self):
        from processiq.persistence.profile_store import load_profile, save_profile

        profile = BusinessProfile(
            industry=Industry.TECHNOLOGY,
            company_size=CompanySize.SMALL,
            notes="Test notes",
        )
        save_profile("user-1", profile)
        loaded = load_profile("user-1")

        assert loaded is not None
        assert loaded.industry == Industry.TECHNOLOGY
        assert loaded.company_size == CompanySize.SMALL
        assert loaded.notes == "Test notes"

    def test_save_overwrites_existing_profile(self):
        from processiq.persistence.profile_store import load_profile, save_profile

        save_profile("user-1", BusinessProfile(industry=Industry.TECHNOLOGY))
        save_profile("user-1", BusinessProfile(industry=Industry.HEALTHCARE))

        loaded = load_profile("user-1")
        assert loaded is not None
        assert loaded.industry == Industry.HEALTHCARE

    def test_save_profile_with_lists(self):
        from processiq.persistence.profile_store import load_profile, save_profile

        profile = BusinessProfile(
            typical_constraints=["No cloud", "SOX compliance"],
            rejected_approaches=["Offshore"],
            preferred_frameworks=["Lean"],
        )
        save_profile("user-2", profile)
        loaded = load_profile("user-2")

        assert loaded is not None
        assert loaded.typical_constraints == ["No cloud", "SOX compliance"]
        assert loaded.rejected_approaches == ["Offshore"]
        assert loaded.preferred_frameworks == ["Lean"]

    def test_save_profile_full(self):
        from processiq.persistence.profile_store import load_profile, save_profile

        profile = BusinessProfile(
            industry=Industry.FINANCIAL_SERVICES,
            company_size=CompanySize.ENTERPRISE,
            annual_revenue=RevenueRange.FROM_20M_TO_100M,
            regulatory_environment=RegulatoryEnvironment.HIGHLY_REGULATED,
        )
        save_profile("user-3", profile)
        loaded = load_profile("user-3")

        assert loaded is not None
        assert loaded.regulatory_environment == RegulatoryEnvironment.HIGHLY_REGULATED
        assert loaded.annual_revenue == RevenueRange.FROM_20M_TO_100M


# ---------------------------------------------------------------------------
# delete_profile
# ---------------------------------------------------------------------------


class TestDeleteProfile:
    def test_delete_existing_profile_returns_true(self):
        from processiq.persistence.profile_store import delete_profile, save_profile

        save_profile("user-del", BusinessProfile())
        assert delete_profile("user-del") is True

    def test_delete_nonexistent_returns_false(self):
        from processiq.persistence.profile_store import delete_profile

        assert delete_profile("does-not-exist") is False

    def test_deleted_profile_is_not_loadable(self):
        from processiq.persistence.profile_store import (
            delete_profile,
            load_profile,
            save_profile,
        )

        save_profile("user-del2", BusinessProfile(industry=Industry.RETAIL))
        delete_profile("user-del2")
        assert load_profile("user-del2") is None


# ---------------------------------------------------------------------------
# update_rejected_approaches
# ---------------------------------------------------------------------------


class TestUpdateRejectedApproaches:
    def test_appends_to_existing_profile(self):
        from processiq.persistence.profile_store import (
            load_profile,
            save_profile,
            update_rejected_approaches,
        )

        save_profile("user-rej", BusinessProfile(rejected_approaches=["Offshore"]))
        update_rejected_approaches("user-rej", ["Automate everything"])

        loaded = load_profile("user-rej")
        assert loaded is not None
        assert "Offshore" in loaded.rejected_approaches
        assert "Automate everything" in loaded.rejected_approaches

    def test_deduplicates_approaches(self):
        from processiq.persistence.profile_store import (
            load_profile,
            save_profile,
            update_rejected_approaches,
        )

        save_profile("user-rej2", BusinessProfile(rejected_approaches=["Offshore"]))
        update_rejected_approaches("user-rej2", ["Offshore"])

        loaded = load_profile("user-rej2")
        assert loaded is not None
        assert loaded.rejected_approaches.count("Offshore") == 1

    def test_creates_profile_if_not_exists(self):
        from processiq.persistence.profile_store import (
            load_profile,
            update_rejected_approaches,
        )

        update_rejected_approaches("user-new", ["RPA"])
        loaded = load_profile("user-new")
        assert loaded is not None
        assert "RPA" in loaded.rejected_approaches
