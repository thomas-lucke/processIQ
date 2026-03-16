"""Shared fixtures for ProcessIQ tests."""

import pytest

from processiq.models import (
    AnalysisInsight,
    BusinessProfile,
    CompanySize,
    Constraints,
    Industry,
    Issue,
    NotAProblem,
    Priority,
    ProcessData,
    ProcessStep,
    Recommendation,
    RegulatoryEnvironment,
    RevenueRange,
)

# ---------------------------------------------------------------------------
# Process fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def single_step_process() -> ProcessData:
    """Minimal valid process: 1 step."""
    return ProcessData(
        name="Single Step",
        steps=[
            ProcessStep(
                step_name="Do the thing",
                average_time_hours=1.0,
                resources_needed=1,
            )
        ],
    )


@pytest.fixture
def simple_process() -> ProcessData:
    """3-step linear process for basic tests."""
    return ProcessData(
        name="Simple Process",
        description="A basic 3-step process",
        steps=[
            ProcessStep(
                step_name="Step A",
                average_time_hours=1.0,
                cost_per_instance=50.0,
                resources_needed=1,
            ),
            ProcessStep(
                step_name="Step B",
                average_time_hours=2.0,
                cost_per_instance=100.0,
                resources_needed=2,
                depends_on=["Step A"],
            ),
            ProcessStep(
                step_name="Step C",
                average_time_hours=0.5,
                cost_per_instance=25.0,
                resources_needed=1,
                depends_on=["Step B"],
            ),
        ],
    )


@pytest.fixture
def creative_agency_process() -> ProcessData:
    """13-step creative agency process (canonical test case)."""
    steps = [
        ProcessStep(
            step_name="Client brings a new project",
            average_time_hours=0.5,
            cost_per_instance=25,
            resources_needed=1,
        ),
        ProcessStep(
            step_name="Employee talks to the client",
            average_time_hours=1.0,
            cost_per_instance=50,
            resources_needed=1,
            depends_on=["Client brings a new project"],
        ),
        ProcessStep(
            step_name="Client gives access to files",
            average_time_hours=0.5,
            cost_per_instance=25,
            resources_needed=1,
            depends_on=["Employee talks to the client"],
        ),
        ProcessStep(
            step_name="Share files with employees",
            average_time_hours=0.5,
            cost_per_instance=50,
            resources_needed=2,
            depends_on=["Client gives access to files"],
        ),
        ProcessStep(
            step_name="Create tasks based on files",
            average_time_hours=1.0,
            cost_per_instance=100,
            resources_needed=2,
            depends_on=["Share files with employees"],
        ),
        ProcessStep(
            step_name="Review tasks by manager",
            average_time_hours=1.0,
            cost_per_instance=100,
            resources_needed=1,
            depends_on=["Create tasks based on files"],
        ),
        ProcessStep(
            step_name="Send invoice to client",
            average_time_hours=0.5,
            cost_per_instance=25,
            resources_needed=1,
            depends_on=["Review tasks by manager"],
        ),
        ProcessStep(
            step_name="Work on the solution",
            average_time_hours=4.0,
            cost_per_instance=300,
            resources_needed=3,
            depends_on=["Review tasks by manager"],
        ),
        ProcessStep(
            step_name="Manager reviews the solution",
            average_time_hours=1.0,
            cost_per_instance=100,
            resources_needed=1,
            depends_on=["Work on the solution"],
        ),
        ProcessStep(
            step_name="Implement the solution",
            average_time_hours=2.0,
            cost_per_instance=150,
            resources_needed=3,
            depends_on=["Manager reviews the solution"],
        ),
        ProcessStep(
            step_name="Get feedback from client",
            average_time_hours=0.5,
            cost_per_instance=25,
            resources_needed=1,
            depends_on=["Implement the solution"],
        ),
        ProcessStep(
            step_name="Adjust the solution",
            average_time_hours=1.0,
            cost_per_instance=100,
            resources_needed=2,
            depends_on=["Get feedback from client"],
        ),
        ProcessStep(
            step_name="Client happy",
            average_time_hours=0.5,
            cost_per_instance=25,
            resources_needed=1,
            depends_on=["Adjust the solution"],
        ),
    ]
    return ProcessData(
        name="Creative Agency Project Workflow",
        description="13-step project delivery process for a creative agency",
        steps=steps,
    )


@pytest.fixture
def zero_cost_process() -> ProcessData:
    """Process where all costs are zero (edge case)."""
    return ProcessData(
        name="No Cost Process",
        steps=[
            ProcessStep(
                step_name="Free Step A",
                average_time_hours=1.0,
                resources_needed=1,
            ),
            ProcessStep(
                step_name="Free Step B",
                average_time_hours=2.0,
                resources_needed=1,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Constraints fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_constraints() -> Constraints:
    """Constraints with all defaults."""
    return Constraints()


@pytest.fixture
def strict_constraints() -> Constraints:
    """Tight constraints for filtering tests."""
    return Constraints(
        budget_limit=5000.0,
        no_new_hires=True,
        must_maintain_audit_trail=True,
        timeline_weeks=4,
        priority=Priority.COST_REDUCTION,
        custom_constraints=["No cloud migration"],
    )


# ---------------------------------------------------------------------------
# BusinessProfile fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_profile() -> BusinessProfile:
    """Profile with just industry and size."""
    return BusinessProfile(
        industry=Industry.TECHNOLOGY,
        company_size=CompanySize.SMALL,
    )


@pytest.fixture
def full_profile() -> BusinessProfile:
    """Fully populated profile."""
    return BusinessProfile(
        industry=Industry.FINANCIAL_SERVICES,
        company_size=CompanySize.ENTERPRISE,
        annual_revenue=RevenueRange.FROM_20M_TO_100M,
        regulatory_environment=RegulatoryEnvironment.HIGHLY_REGULATED,
        typical_constraints=["SOX compliance", "Change management board"],
        rejected_approaches=["Offshore outsourcing"],
        notes="We tried RPA in 2023, it didn't work for our legacy systems.",
    )


# ---------------------------------------------------------------------------
# AnalysisInsight fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_insight() -> AnalysisInsight:
    """Minimal AnalysisInsight for export/display tests."""
    return AnalysisInsight(
        process_summary="5-step order process, ~8 hours total",
        patterns=["2 approval steps", "1 external handoff"],
        issues=[
            Issue(
                title="Redundant approvals",
                description="Two separate approval steps could be combined.",
                affected_steps=["Manager approval", "Director approval"],
                severity="medium",
            ),
        ],
        recommendations=[
            Recommendation(
                title="Consolidate approvals",
                addresses_issue="Redundant approvals",
                description="Merge manager and director review into single step.",
                expected_benefit="~1 hour saved per instance",
                feasibility="easy",
            ),
        ],
        not_problems=[
            NotAProblem(
                step_name="Design solution",
                why_not_a_problem="Core creative work that produces the deliverable.",
            ),
        ],
    )
