"""Process data models for ProcessIQ."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProcessStep(BaseModel):
    """A single step in a business process."""

    step_name: str = Field(..., min_length=1, description="Name of the process step")
    average_time_hours: float = Field(
        ..., ge=0, description="Average time to complete in hours"
    )
    resources_needed: int = Field(
        ...,
        ge=0,
        description="Number of people involved. Use 0 for fully automated steps with no human touch.",
    )
    error_rate_pct: float = Field(
        default=0.0,
        ge=0,
        le=100,
        description="Percentage of times this step fails/needs rework",
    )
    cost_per_instance: float = Field(
        default=0.0, ge=0, description="Cost in dollars per execution"
    )
    estimated_fields: list[str] = Field(
        default_factory=list,
        description="Field names estimated by AI (e.g., ['cost_per_instance', 'error_rate_pct'])",
    )
    depends_on: list[str] = Field(
        default_factory=list, description="Steps that must complete before this one"
    )
    group_id: str | None = Field(
        default=None,
        description="Groups related steps together (alternatives or parallel). "
        "Steps sharing a group_id are either/or choices or happen simultaneously.",
    )
    group_type: Literal["alternative", "parallel"] | None = Field(
        default=None,
        description="'alternative' = either/or (e.g., phone OR email), "
        "'parallel' = simultaneous (e.g., invoice paid AND added to tax system).",
    )
    step_type: Literal["normal", "conditional", "loop"] = Field(
        default="normal",
        description="'normal' = runs every time, 'conditional' = only runs under certain conditions, "
        "'loop' = can cycle back to an earlier step.",
    )
    notes: str = Field(
        default="",
        description="Assumptions, conditional triggers, or ambiguities flagged during extraction.",
    )

    @field_validator("depends_on", mode="before")
    @classmethod
    def parse_depends_on(cls, v: str | list[str] | None) -> list[str]:
        """Parse depends_on from semicolon or comma-separated string or list."""
        if v is None:
            return []
        if isinstance(v, str):
            # Try semicolon first, then comma
            if ";" in v:
                return [s.strip() for s in v.split(";") if s.strip()]
            return [s.strip() for s in v.split(",") if s.strip()]
        return v


class ProcessData(BaseModel):
    """Complete process data for analysis."""

    name: str = Field(
        ..., min_length=1, description="Name of the process being analyzed"
    )
    description: str = Field(
        default="", description="Optional description of the process"
    )
    steps: list[ProcessStep] = Field(
        ..., min_length=1, description="List of process steps"
    )
    annual_volume: int | None = Field(
        default=None,
        description="Estimated number of times this process runs per year. "
        "If not provided, will be estimated from company size / industry.",
    )

    @property
    def total_time_hours(self) -> float:
        """Calculate total process time (sum of all steps)."""
        return sum(step.average_time_hours for step in self.steps)

    @property
    def total_cost(self) -> float:
        """Calculate total process cost (sum of all steps)."""
        return sum(step.cost_per_instance for step in self.steps)

    @property
    def step_names(self) -> list[str]:
        """Get list of all step names."""
        return [step.step_name for step in self.steps]

    def get_step(self, name: str) -> ProcessStep | None:
        """Get a step by name."""
        for step in self.steps:
            if step.step_name == name:
                return step
        return None

    def merge_with(self, other: "ProcessData") -> "ProcessData":
        """Merge another ProcessData into this one.

        Matching steps (by name, case-insensitive): other's non-zero values
        overwrite self's values and clear the field from estimated_fields.
        New steps from other are appended. Steps only in self are preserved.
        """
        # Index other's steps by normalized name
        other_by_name: dict[str, ProcessStep] = {
            s.step_name.strip().lower(): s for s in other.steps
        }
        seen_names: set[str] = set()
        merged_steps: list[ProcessStep] = []

        for existing in self.steps:
            key = existing.step_name.strip().lower()
            seen_names.add(key)
            incoming = other_by_name.get(key)

            if incoming is None:
                # Step only in self — keep as-is
                merged_steps.append(existing.model_copy())
                continue

            # Merge: incoming non-zero values overwrite existing
            estimated = list(existing.estimated_fields)
            merge_fields = {
                "average_time_hours": (
                    incoming.average_time_hours,
                    existing.average_time_hours,
                ),
                "cost_per_instance": (
                    incoming.cost_per_instance,
                    existing.cost_per_instance,
                ),
                "error_rate_pct": (incoming.error_rate_pct, existing.error_rate_pct),
            }

            merged_values: dict[str, float] = {}
            for field_name, (new_v, old_v) in merge_fields.items():
                if new_v != 0:
                    merged_values[field_name] = new_v
                    if field_name in estimated:
                        estimated.remove(field_name)
                else:
                    merged_values[field_name] = old_v

            merged_steps.append(
                ProcessStep(
                    step_name=existing.step_name,
                    average_time_hours=merged_values["average_time_hours"],
                    cost_per_instance=merged_values["cost_per_instance"],
                    error_rate_pct=merged_values["error_rate_pct"],
                    resources_needed=incoming.resources_needed
                    if incoming.resources_needed > 1
                    else existing.resources_needed,
                    depends_on=incoming.depends_on or existing.depends_on,
                    estimated_fields=estimated,
                    group_id=existing.group_id or incoming.group_id,
                    group_type=existing.group_type or incoming.group_type,
                    step_type=existing.step_type,
                    notes=existing.notes or incoming.notes,
                )
            )

        # Append steps only in other
        for other_step in other.steps:
            if other_step.step_name.strip().lower() not in seen_names:
                merged_steps.append(other_step.model_copy())

        return ProcessData(
            name=self.name,
            description=self.description or other.description,
            steps=merged_steps,
        )
