"""Pydantic schema for a structured code-fix proposal."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FixProposal(BaseModel):
    """A proposed fix for a detected code bug.

    Produced by FixGenerator and consumed downstream for branch creation,
    commit generation, and pull-request submission.
    """

    fixed_code: str = Field(
        description=(
            "The COMPLETE corrected file content, ready to be written to disk. "
            "Must include ALL original lines, not just the changed section. "
            "No markdown fences (no ``` blocks)."
        )
    )
    explanation: str = Field(
        description=(
            "1-2 sentences describing what was changed and why. "
            "Reference the specific line or construct that was fixed."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confidence that this fix is correct, from 0.0 (guessing) to "
            "1.0 (certain). Set below 0.6 when the fix involves assumptions "
            "not directly supported by the diagnosis."
        ),
    )
    lines_changed: list[int] = Field(
        description=(
            "1-based line numbers in the ORIGINAL file that were modified. "
            "Empty list if the change adds new lines only at the end."
        )
    )
