"""Memory models for ProcessIQ."""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Industry(str, Enum):
    """Industry classification options."""

    FINANCIAL_SERVICES = "financial_services"
    HEALTHCARE = "healthcare"
    MANUFACTURING = "manufacturing"
    RETAIL = "retail"
    TECHNOLOGY = "technology"
    GOVERNMENT = "government"
    EDUCATION = "education"
    OTHER = "other"


class CompanySize(str, Enum):
    """Company size classification."""

    STARTUP = "startup"  # < 50 employees
    SMALL = "small"  # 50-200 employees
    MID_MARKET = "mid_market"  # 200-1000 employees
    ENTERPRISE = "enterprise"  # > 1000 employees


class RevenueRange(str, Enum):
    """Annual revenue range for calibrating recommendation costs."""

    UNDER_100K = "under_100k"  # < $100K
    FROM_100K_TO_500K = "100k_to_500k"  # $100K - $500K
    FROM_500K_TO_1M = "500k_to_1m"  # $500K - $1M
    FROM_1M_TO_5M = "1m_to_5m"  # $1M - $5M
    FROM_5M_TO_20M = "5m_to_20m"  # $5M - $20M
    FROM_20M_TO_100M = "20m_to_100m"  # $20M - $100M
    OVER_100M = "over_100m"  # > $100M
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class RegulatoryEnvironment(str, Enum):
    """Regulatory strictness level."""

    MINIMAL = "minimal"
    MODERATE = "moderate"
    STRICT = "strict"
    HIGHLY_REGULATED = "highly_regulated"


class BusinessProfile(BaseModel):
    """Semantic memory: Facts about the business (Profile approach).

    Phase 1: Populated from user input at session start.
    Phase 2: Persisted and updated across sessions.
    """

    industry: Industry | None = Field(
        default=None, description="Industry classification (None = not yet specified)"
    )
    custom_industry: str = Field(
        default="", description="User-specified industry when 'Other' is selected"
    )
    company_size: CompanySize | None = Field(
        default=None, description="Company size category (None = not yet specified)"
    )
    annual_revenue: RevenueRange = Field(
        default=RevenueRange.PREFER_NOT_TO_SAY,
        description="Annual revenue range for calibrating recommendation costs",
    )
    regulatory_environment: RegulatoryEnvironment = Field(
        default=RegulatoryEnvironment.MODERATE, description="Regulatory strictness"
    )
    typical_constraints: list[str] = Field(
        default_factory=list, description="Common constraints for this business"
    )
    preferred_frameworks: list[str] = Field(
        default_factory=list,
        description="Frameworks user responds well to (Lean, Six Sigma, etc.)",
    )
    previous_improvements: list[str] = Field(
        default_factory=list, description="Past improvement initiatives"
    )
    rejected_approaches: list[str] = Field(
        default_factory=list, description="Approaches user has rejected before"
    )
    notes: str = Field(default="", description="Additional context about the business")


class AnalysisMemory(BaseModel):
    """Episodic memory: Past analysis experience.

    Stored in SQLite (`analysis_sessions` table) and embedded in ChromaDB
    for semantic retrieval during future analyses.
    """

    id: str = Field(..., description="Unique identifier for this analysis")
    user_id: str = Field(default="", description="User who ran this analysis")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="When analysis was performed",
    )
    process_name: str = Field(..., description="Name of the analyzed process")
    process_description: str = Field(
        default="",
        description="Short summary of the process (for display in past analyses)",
    )
    industry: str = Field(default="", description="Industry at time of analysis")
    step_names: list[str] = Field(
        default_factory=list,
        description="All step names in the process (for embedding text construction)",
    )
    bottlenecks_found: list[str] = Field(
        default_factory=list, description="Issue titles identified as bottlenecks"
    )
    suggestions_offered: list[str] = Field(
        default_factory=list, description="Recommendation titles offered"
    )
    suggestions_accepted: list[str] = Field(
        default_factory=list, description="Recommendation titles accepted"
    )
    suggestions_rejected: list[str] = Field(
        default_factory=list, description="Recommendation titles rejected"
    )
    rejection_reasons: list[str] = Field(
        default_factory=list,
        description="Why suggestions were rejected (critical for learning)",
    )
    recommendations_full: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Full recommendation objects serialized as dicts (title, description, "
        "expected_benefit, estimated_roi). Stored for the Analysis Library view.",
    )
    process_summary: str = Field(
        default="",
        description="LLM-generated 1-2 sentence summary of the process. "
        "Included in ChromaDB embedding for richer semantic retrieval.",
    )
    issue_descriptions: list[str] = Field(
        default_factory=list,
        description="Full descriptions of identified issues (not just titles). "
        "Included in ChromaDB embedding so future retrievals can match on reasoning.",
    )
    outcome_notes: str = Field(default="", description="Post-implementation notes")

    @property
    def acceptance_rate(self) -> float:
        """Calculate suggestion acceptance rate."""
        total = len(self.suggestions_accepted) + len(self.suggestions_rejected)
        if total == 0:
            return 0.0
        return len(self.suggestions_accepted) / total


class SimilarAnalysis(BaseModel):
    """A past analysis retrieved by semantic similarity from ChromaDB."""

    session_id: str
    process_name: str
    similarity_score: float
    bottlenecks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    rejected_recs: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    timestamp: datetime
