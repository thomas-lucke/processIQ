"""Tests for processiq.models.constraints."""

from processiq.models import ConflictResult, Constraints, Priority


class TestPriority:
    def test_values(self):
        assert Priority.COST_REDUCTION.value == "cost_reduction"
        assert Priority.TIME_REDUCTION.value == "time_reduction"
        assert Priority.QUALITY_IMPROVEMENT.value == "quality_improvement"
        assert Priority.COMPLIANCE.value == "compliance"

    def test_member_count(self):
        assert len(Priority) == 4


class TestConstraints:
    def test_defaults(self):
        c = Constraints()
        assert c.budget_limit is None
        assert c.no_new_hires is False
        assert c.max_error_rate_increase_pct == 0.0
        assert c.must_maintain_audit_trail is False
        assert c.timeline_weeks is None
        assert c.priority == Priority.COST_REDUCTION
        assert c.custom_constraints == []

    def test_is_hiring_allowed_true(self, default_constraints):
        assert default_constraints.is_hiring_allowed() is True

    def test_is_hiring_allowed_false(self, strict_constraints):
        assert strict_constraints.is_hiring_allowed() is False

    def test_has_budget_limit_false(self, default_constraints):
        assert default_constraints.has_budget_limit() is False

    def test_has_budget_limit_true(self, strict_constraints):
        assert strict_constraints.has_budget_limit() is True


class TestConflictResult:
    def test_no_conflicts(self):
        r = ConflictResult(is_valid=True)
        assert r.has_conflicts is False
        assert r.conflicts == []
        assert r.warnings == []

    def test_has_conflicts(self):
        r = ConflictResult(
            is_valid=False,
            conflicts=["Exceeds budget"],
            warnings=["Tight timeline"],
        )
        assert r.has_conflicts is True
        assert len(r.conflicts) == 1

    def test_has_conflicts_false_when_empty(self):
        r = ConflictResult(is_valid=True, conflicts=[])
        assert r.has_conflicts is False
