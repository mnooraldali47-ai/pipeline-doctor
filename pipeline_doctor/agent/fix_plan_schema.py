"""Pydantic schema for a concrete fix plan produced by AutoFixAgent."""

from typing import Optional
from pydantic import BaseModel, Field


class FixPlan(BaseModel):
    """Actionable fix plan derived from a Diagnosis.

    safe_to_apply=True means the fix can be offered to the user;
    it is never applied without requires_confirmation being fulfilled.
    safe_to_apply=False means the fix is deliberately withheld
    (ambiguous risk, e.g. dependency or test failures).
    """

    job_name: str = Field(description="Jenkins job name, maps to test-repos/{job_name}/")
    build_number: int = Field(description="Build number the diagnosis came from.")
    error_type: str = Field(description="Error category, mirrors Diagnosis.error_type.")
    root_cause: str = Field(description="Short root-cause summary from the diagnosis.")
    affected_file: Optional[str] = Field(
        default=None,
        description="Basename of the file to be changed, or None.",
    )
    proposed_change: str = Field(
        description="Human-readable description of the exact change to be made."
    )
    safe_to_apply: bool = Field(
        description=(
            "True if the fix can be offered for application after confirmation. "
            "False means the fix is intentionally not automated."
        )
    )
    requires_confirmation: bool = Field(
        default=True,
        description="Always True — no fix is applied without user confirmation.",
    )
    explanation: str = Field(
        description="Why this fix is (or is not) safe to apply automatically."
    )
