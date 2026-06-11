"""Pydantic schema for a structured Jenkins build-failure diagnosis."""

from typing import Optional
from pydantic import BaseModel, Field


class Diagnosis(BaseModel):
    """Structured diagnosis of a Jenkins pipeline failure.

    Produced by DiagnosisAgent and consumed downstream for reporting,
    ticketing, or automated fix suggestions.
    """

    error_type: str = Field(
        description=(
            "Category of the failure. One of: 'dependency_not_found', "
            "'test_failure', 'syntax_error', 'build_error', 'unknown'."
        )
    )
    failed_stage: Optional[str] = Field(
        default=None,
        description=(
            "Name of the Jenkins pipeline stage where the failure occurred, "
            "e.g. 'Install Dependencies' or 'Test'. Null if not determinable."
        ),
    )
    root_cause: str = Field(
        description=(
            "1-2 sentences explaining WHAT went wrong, in plain English. "
            "Focus on the technical cause, not on symptoms."
        )
    )
    root_cause_evidence: str = Field(
        description=(
            "The single most relevant line from the build log that proves the "
            "root cause, copied verbatim. E.g. 'AssertionError: assert 2 == 3'."
        )
    )
    fix_suggestion: str = Field(
        description=(
            "1-3 actionable sentences describing HOW to fix the issue. "
            "Be specific: name files, commands, or code changes where possible."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How confident you are in this diagnosis, from 0.0 (guessing) to "
            "1.0 (certain). Use lower values when log evidence is ambiguous."
        ),
    )
    affected_file: Optional[str] = Field(
        default=None,
        description=(
            "Filename most likely responsible for the failure, e.g. 'test_main.py'. "
            "Null if not identifiable from the log."
        ),
    )
    affected_line: Optional[int] = Field(
        default=None,
        description=(
            "Line number within affected_file where the failure originates. "
            "Null if not determinable."
        ),
    )
