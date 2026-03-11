"""Tests for processiq.models.process."""

import pytest
from pydantic import ValidationError

from processiq.models import ProcessData, ProcessStep


class TestProcessStep:
    """Tests for ProcessStep model."""

    def test_valid_creation(self):
        step = ProcessStep(
            step_name="Review document",
            average_time_hours=1.5,
            resources_needed=2,
        )
        assert step.step_name == "Review document"
        assert step.average_time_hours == 1.5
        assert step.resources_needed == 2

    def test_defaults(self):
        step = ProcessStep(
            step_name="A step",
            average_time_hours=1.0,
            resources_needed=1,
        )
        assert step.error_rate_pct == 0.0
        assert step.cost_per_instance == 0.0
        assert step.depends_on == []
        assert step.estimated_fields == []

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            ProcessStep(step_name="", average_time_hours=1.0, resources_needed=1)

    def test_rejects_negative_time(self):
        with pytest.raises(ValidationError):
            ProcessStep(step_name="X", average_time_hours=-1.0, resources_needed=1)

    def test_allows_zero_resources_for_automated_steps(self):
        # resources_needed=0 is valid for fully automated steps with no human touch
        step = ProcessStep(step_name="X", average_time_hours=1.0, resources_needed=0)
        assert step.resources_needed == 0

    def test_error_rate_upper_bound(self):
        with pytest.raises(ValidationError):
            ProcessStep(
                step_name="X",
                average_time_hours=1.0,
                resources_needed=1,
                error_rate_pct=101.0,
            )

    def test_error_rate_lower_bound(self):
        with pytest.raises(ValidationError):
            ProcessStep(
                step_name="X",
                average_time_hours=1.0,
                resources_needed=1,
                error_rate_pct=-1.0,
            )

    def test_depends_on_from_semicolon_string(self):
        step = ProcessStep(
            step_name="X",
            average_time_hours=1.0,
            resources_needed=1,
            depends_on="Step A; Step B",
        )
        assert step.depends_on == ["Step A", "Step B"]

    def test_depends_on_from_comma_string(self):
        step = ProcessStep(
            step_name="X",
            average_time_hours=1.0,
            resources_needed=1,
            depends_on="Step A, Step B",
        )
        assert step.depends_on == ["Step A", "Step B"]

    def test_depends_on_from_list(self):
        step = ProcessStep(
            step_name="X",
            average_time_hours=1.0,
            resources_needed=1,
            depends_on=["Step A", "Step B"],
        )
        assert step.depends_on == ["Step A", "Step B"]

    def test_depends_on_from_none(self):
        step = ProcessStep(
            step_name="X",
            average_time_hours=1.0,
            resources_needed=1,
            depends_on=None,
        )
        assert step.depends_on == []

    def test_depends_on_strips_whitespace(self):
        step = ProcessStep(
            step_name="X",
            average_time_hours=1.0,
            resources_needed=1,
            depends_on="  Step A ;  Step B  ",
        )
        assert step.depends_on == ["Step A", "Step B"]

    def test_depends_on_empty_string(self):
        step = ProcessStep(
            step_name="X",
            average_time_hours=1.0,
            resources_needed=1,
            depends_on="",
        )
        assert step.depends_on == []


class TestProcessData:
    """Tests for ProcessData model."""

    def test_valid_creation(self, single_step_process):
        assert single_step_process.name == "Single Step"
        assert len(single_step_process.steps) == 1

    def test_rejects_empty_steps(self):
        with pytest.raises(ValidationError):
            ProcessData(name="Empty", steps=[])

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            ProcessData(
                name="",
                steps=[
                    ProcessStep(
                        step_name="X", average_time_hours=1.0, resources_needed=1
                    )
                ],
            )

    def test_total_time_hours(self, simple_process):
        assert simple_process.total_time_hours == pytest.approx(3.5)

    def test_total_cost(self, simple_process):
        assert simple_process.total_cost == pytest.approx(175.0)

    def test_step_names(self, simple_process):
        assert simple_process.step_names == ["Step A", "Step B", "Step C"]

    def test_get_step_found(self, simple_process):
        step = simple_process.get_step("Step B")
        assert step is not None
        assert step.average_time_hours == 2.0

    def test_get_step_not_found(self, simple_process):
        assert simple_process.get_step("Nonexistent") is None

    def test_description_default(self):
        process = ProcessData(
            name="Test",
            steps=[
                ProcessStep(step_name="X", average_time_hours=1.0, resources_needed=1)
            ],
        )
        assert process.description == ""

    def test_total_time_zero_cost_process(self, zero_cost_process):
        assert zero_cost_process.total_time_hours == pytest.approx(3.0)
        assert zero_cost_process.total_cost == pytest.approx(0.0)
