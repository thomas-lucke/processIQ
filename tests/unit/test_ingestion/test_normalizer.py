"""Tests for processiq.ingestion.normalizer (pure logic, no LLM calls)."""

import pytest
from pydantic import ValidationError

from processiq.ingestion.normalizer import (
    ClarificationNeeded,
    ExtractedStep,
    ExtractionResponse,
    ExtractionResult,
    _extraction_result_to_process_data,
    _find_previous_non_group_step,
    _infer_missing_dependencies,
)
from processiq.models import ProcessStep

# ---------------------------------------------------------------------------
# ExtractedStep validation
# ---------------------------------------------------------------------------


class TestExtractedStep:
    def test_minimal_valid_step(self):
        step = ExtractedStep(
            step_name="Submit request",
            average_time_hours=0.5,
            resources_needed=1,
        )
        assert step.step_name == "Submit request"
        assert step.error_rate_pct == 0.0
        assert step.cost_per_instance == 0.0
        assert step.depends_on == []
        assert step.estimated_fields == []
        assert step.step_type == "normal"

    def test_negative_time_clamped_to_zero(self):
        step = ExtractedStep(step_name="S", average_time_hours=-1.0, resources_needed=1)
        assert step.average_time_hours == 0.0

    def test_error_rate_above_100_clamped(self):
        step = ExtractedStep(
            step_name="S",
            average_time_hours=1.0,
            resources_needed=1,
            error_rate_pct=101.0,
        )
        assert step.error_rate_pct == 100.0

    def test_error_rate_exactly_100_valid(self):
        step = ExtractedStep(
            step_name="S",
            average_time_hours=1.0,
            resources_needed=1,
            error_rate_pct=100.0,
        )
        assert step.error_rate_pct == 100.0

    def test_confidence_above_1_clamped(self):
        step = ExtractedStep(
            step_name="S",
            average_time_hours=1.0,
            resources_needed=1,
            confidence=1.5,
        )
        assert step.confidence == 1.0

    def test_confidence_below_0_clamped(self):
        step = ExtractedStep(
            step_name="S",
            average_time_hours=1.0,
            resources_needed=1,
            confidence=-0.1,
        )
        assert step.confidence == 0.0

    def test_group_id_without_type_auto_cleared(self):
        """group_id set but group_type not → both cleared by validator."""
        step = ExtractedStep(
            step_name="S",
            average_time_hours=1.0,
            resources_needed=1,
            group_id="my_group",
            group_type=None,
        )
        assert step.group_id is None
        assert step.group_type is None

    def test_group_type_without_id_auto_cleared(self):
        step = ExtractedStep(
            step_name="S",
            average_time_hours=1.0,
            resources_needed=1,
            group_id=None,
            group_type="alternative",
        )
        assert step.group_id is None
        assert step.group_type is None

    def test_both_group_fields_set_valid(self):
        step = ExtractedStep(
            step_name="S",
            average_time_hours=1.0,
            resources_needed=1,
            group_id="receive_order",
            group_type="alternative",
        )
        assert step.group_id == "receive_order"
        assert step.group_type == "alternative"

    def test_valid_step_types(self):
        for stype in ("normal", "conditional", "loop"):
            step = ExtractedStep(
                step_name="S",
                average_time_hours=1.0,
                resources_needed=1,
                step_type=stype,
            )
            assert step.step_type == stype

    def test_invalid_step_type_rejected(self):
        with pytest.raises(ValidationError):
            ExtractedStep(
                step_name="S",
                average_time_hours=1.0,
                resources_needed=1,
                step_type="unknown",
            )


# ---------------------------------------------------------------------------
# ExtractionResult
# ---------------------------------------------------------------------------


class TestExtractionResult:
    def _make_step(self, name: str = "Step A") -> ExtractedStep:
        return ExtractedStep(step_name=name, average_time_hours=1.0, resources_needed=1)

    def test_requires_at_least_one_step(self):
        with pytest.raises(ValidationError):
            ExtractionResult(steps=[])

    def test_default_process_name(self):
        result = ExtractionResult(steps=[self._make_step()])
        assert result.process_name == "Extracted Process"

    def test_warnings_default_empty(self):
        result = ExtractionResult(steps=[self._make_step()])
        assert result.warnings == []


# ---------------------------------------------------------------------------
# ExtractionResponse
# ---------------------------------------------------------------------------


class TestExtractionResponse:
    def test_extracted_response(self):
        step = ExtractedStep(step_name="S", average_time_hours=1.0, resources_needed=1)
        extraction = ExtractionResult(steps=[step])
        resp = ExtractionResponse(response_type="extracted", extraction=extraction)
        assert resp.response_type == "extracted"
        assert resp.extraction is extraction

    def test_needs_clarification_response(self):
        clarification = ClarificationNeeded(
            message="I need more info",
            detected_intent="expense approval",
            clarifying_questions=["How many steps?"],
            why_more_info_needed="Not enough detail",
        )
        resp = ExtractionResponse(
            response_type="needs_clarification", clarification=clarification
        )
        assert resp.response_type == "needs_clarification"
        assert resp.clarification is clarification

    def test_invalid_response_type_rejected(self):
        with pytest.raises(ValidationError):
            ExtractionResponse(response_type="unknown")


# ---------------------------------------------------------------------------
# _infer_missing_dependencies
# ---------------------------------------------------------------------------


def _make_steps(*names: str, group_specs: dict | None = None) -> list[ProcessStep]:
    """Create a list of ProcessStep by name, with optional group specs."""
    group_specs = group_specs or {}
    steps = []
    for name in names:
        spec = group_specs.get(name, {})
        steps.append(
            ProcessStep(
                step_name=name,
                average_time_hours=1.0,
                resources_needed=1,
                **spec,
            )
        )
    return steps


class TestInferMissingDependencies:
    def test_single_step_no_change(self):
        steps = _make_steps("Only Step")
        _infer_missing_dependencies(steps)
        assert steps[0].depends_on == []

    def test_two_steps_no_deps_inferred_sequential(self):
        steps = _make_steps("Step A", "Step B")
        _infer_missing_dependencies(steps)
        assert steps[1].depends_on == ["Step A"]

    def test_existing_valid_deps_preserved(self):
        steps = _make_steps("Step A", "Step B")
        steps[1].depends_on = ["Step A"]
        _infer_missing_dependencies(steps)
        assert steps[1].depends_on == ["Step A"]

    def test_invalid_dep_reference_cleaned(self):
        steps = _make_steps("Step A", "Step B")
        steps[1].depends_on = ["Nonexistent Step"]
        _infer_missing_dependencies(steps)
        # Invalid dep removed, then sequential dep inferred
        assert steps[1].depends_on == ["Step A"]

    def test_three_steps_sequential_chain(self):
        steps = _make_steps("A", "B", "C")
        _infer_missing_dependencies(steps)
        assert steps[1].depends_on == ["A"]
        assert steps[2].depends_on == ["B"]

    def test_alternative_group_successor_depends_on_all_alternatives(self):
        """Step after a group of alternatives should depend on all alternatives."""
        steps = [
            ProcessStep(step_name="Start", average_time_hours=1.0, resources_needed=1),
            ProcessStep(
                step_name="Phone Order",
                average_time_hours=0.5,
                resources_needed=1,
                group_id="receive_order",
                group_type="alternative",
                depends_on=["Start"],
            ),
            ProcessStep(
                step_name="Email Order",
                average_time_hours=0.5,
                resources_needed=1,
                group_id="receive_order",
                group_type="alternative",
                depends_on=["Start"],
            ),
            ProcessStep(
                step_name="Process Order", average_time_hours=1.0, resources_needed=1
            ),
        ]
        _infer_missing_dependencies(steps)
        # "Process Order" comes after the alternatives group — should depend on both
        assert "Phone Order" in steps[3].depends_on
        assert "Email Order" in steps[3].depends_on

    def test_group_member_without_deps_gets_previous_non_group(self):
        """Second member of a group should depend on last non-group step."""
        steps = [
            ProcessStep(step_name="Prep", average_time_hours=1.0, resources_needed=1),
            ProcessStep(
                step_name="Option A",
                average_time_hours=1.0,
                resources_needed=1,
                group_id="options",
                group_type="alternative",
                depends_on=["Prep"],
            ),
            ProcessStep(
                step_name="Option B",
                average_time_hours=1.0,
                resources_needed=1,
                group_id="options",
                group_type="alternative",
            ),
        ]
        _infer_missing_dependencies(steps)
        assert steps[2].depends_on == ["Prep"]


# ---------------------------------------------------------------------------
# _find_previous_non_group_step
# ---------------------------------------------------------------------------


class TestFindPreviousNonGroupStep:
    def test_returns_none_when_all_same_group(self):
        steps = [
            ProcessStep(
                step_name="A",
                average_time_hours=1.0,
                resources_needed=1,
                group_id="g1",
                group_type="alternative",
            ),
            ProcessStep(
                step_name="B",
                average_time_hours=1.0,
                resources_needed=1,
                group_id="g1",
                group_type="alternative",
            ),
        ]
        result = _find_previous_non_group_step(steps, 1, "g1")
        assert result is None

    def test_returns_first_non_group_step(self):
        steps = [
            ProcessStep(
                step_name="Outside", average_time_hours=1.0, resources_needed=1
            ),
            ProcessStep(
                step_name="A",
                average_time_hours=1.0,
                resources_needed=1,
                group_id="g1",
                group_type="alternative",
            ),
            ProcessStep(
                step_name="B",
                average_time_hours=1.0,
                resources_needed=1,
                group_id="g1",
                group_type="alternative",
            ),
        ]
        result = _find_previous_non_group_step(steps, 2, "g1")
        assert result is not None
        assert result.step_name == "Outside"


# ---------------------------------------------------------------------------
# _extraction_result_to_process_data
# ---------------------------------------------------------------------------


class TestExtractionResultToProcessData:
    def test_converts_steps(self):
        steps = [
            ExtractedStep(step_name="A", average_time_hours=1.0, resources_needed=1),
            ExtractedStep(step_name="B", average_time_hours=2.0, resources_needed=2),
        ]
        result = ExtractionResult(steps=steps, process_name="Test Process")
        data = _extraction_result_to_process_data(result)
        assert data.name == "Test Process"
        assert len(data.steps) == 2
        assert data.steps[0].step_name == "A"

    def test_infers_sequential_dependencies(self):
        steps = [
            ExtractedStep(
                step_name="First", average_time_hours=1.0, resources_needed=1
            ),
            ExtractedStep(
                step_name="Second", average_time_hours=1.0, resources_needed=1
            ),
        ]
        result = ExtractionResult(steps=steps)
        data = _extraction_result_to_process_data(result)
        assert data.steps[1].depends_on == ["First"]

    def test_copies_all_fields(self):
        step = ExtractedStep(
            step_name="Review",
            average_time_hours=2.0,
            resources_needed=2,
            error_rate_pct=5.0,
            cost_per_instance=100.0,
            estimated_fields=["cost_per_instance"],
            step_type="conditional",
            notes="Only runs on large orders",
        )
        result = ExtractionResult(steps=[step])
        data = _extraction_result_to_process_data(result)
        ps = data.steps[0]
        assert ps.step_name == "Review"
        assert ps.average_time_hours == 2.0
        assert ps.error_rate_pct == 5.0
        assert ps.cost_per_instance == 100.0
        assert "cost_per_instance" in ps.estimated_fields
        assert ps.step_type == "conditional"
        assert ps.notes == "Only runs on large orders"
