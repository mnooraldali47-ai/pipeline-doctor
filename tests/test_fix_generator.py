"""Unit tests for FixGenerator — LLM chain is fully mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pipeline_doctor.agent.diagnosis_schema import Diagnosis
from pipeline_doctor.agent.fix_schema import FixProposal


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_DIAGNOSIS = Diagnosis(
    error_type="SyntaxError",
    failed_stage="Syntax Check",
    root_cause="Missing colon at end of function definition",
    root_cause_evidence="def multiply(x, y)",
    fix_suggestion="Add colon after function parameters",
    confidence=0.99,
    affected_file="main.py",
    affected_line=4,
)

SAMPLE_BROKEN_CODE = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "def multiply(x, y)\n"
    "    return x * y\n"
)

SAMPLE_FIXED_CODE = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "def multiply(x, y):\n"
    "    return x * y\n"
)


def _mock_chain(fix_proposal: FixProposal | None, parsing_error=None) -> MagicMock:
    """Build a mock LLM chain that returns a preset invoke() result."""
    chain = MagicMock()
    chain.invoke.return_value = {
        "parsed": fix_proposal,
        "parsing_error": parsing_error,
        "raw": MagicMock(content="raw output"),
    }
    return chain


def _make_fix_proposal() -> FixProposal:
    return FixProposal(
        fixed_code=SAMPLE_FIXED_CODE,
        explanation="Added missing colon after function parameters on line 4.",
        confidence=0.97,
        lines_changed=[4],
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_fix_generator_instantiable() -> None:
    """FixGenerator can be created when get_llm() is mocked."""
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock()

    with patch("pipeline_doctor.agent.fix_generator.get_llm", return_value=mock_llm):
        from pipeline_doctor.agent.fix_generator import FixGenerator

        generator = FixGenerator()

    assert generator is not None
    mock_llm.with_structured_output.assert_called_once_with(FixProposal, include_raw=True)


def test_generate_fix_returns_fix_proposal() -> None:
    """generate_fix() returns a FixProposal when LLM parses successfully."""
    expected = _make_fix_proposal()
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = _mock_chain(expected)

    with patch("pipeline_doctor.agent.fix_generator.get_llm", return_value=mock_llm):
        from pipeline_doctor.agent.fix_generator import FixGenerator

        generator = FixGenerator()
        fix = generator.generate_fix(SAMPLE_BROKEN_CODE, SAMPLE_DIAGNOSIS)

    assert isinstance(fix, FixProposal)
    assert fix.fixed_code == SAMPLE_FIXED_CODE
    assert fix.confidence == 0.97
    assert fix.lines_changed == [4]
    assert "colon" in fix.explanation.lower()


def test_generate_fix_raises_on_parsing_error() -> None:
    """generate_fix() raises ValueError when LLM output cannot be parsed."""
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = _mock_chain(
        fix_proposal=None,
        parsing_error="JSON decode error at line 1",
    )

    with patch("pipeline_doctor.agent.fix_generator.get_llm", return_value=mock_llm):
        from pipeline_doctor.agent.fix_generator import FixGenerator

        generator = FixGenerator()

        with pytest.raises(ValueError, match="FixProposal"):
            generator.generate_fix(SAMPLE_BROKEN_CODE, SAMPLE_DIAGNOSIS)


def test_fix_proposal_has_all_fields() -> None:
    """FixProposal model exposes fixed_code, explanation, confidence, lines_changed."""
    fix = _make_fix_proposal()

    assert hasattr(fix, "fixed_code")
    assert hasattr(fix, "explanation")
    assert hasattr(fix, "confidence")
    assert hasattr(fix, "lines_changed")

    assert isinstance(fix.fixed_code, str)
    assert isinstance(fix.explanation, str)
    assert isinstance(fix.confidence, float)
    assert isinstance(fix.lines_changed, list)


def test_fix_proposal_confidence_bounds() -> None:
    """FixProposal rejects confidence values outside [0.0, 1.0]."""
    with pytest.raises(Exception):
        FixProposal(
            fixed_code="x = 1",
            explanation="test",
            confidence=1.5,
            lines_changed=[],
        )

    with pytest.raises(Exception):
        FixProposal(
            fixed_code="x = 1",
            explanation="test",
            confidence=-0.1,
            lines_changed=[],
        )


def test_build_prompt_contains_diagnosis_fields() -> None:
    """_build_prompt() injects all diagnosis fields into the user message."""
    from pipeline_doctor.agent.fix_generator import FixGenerator

    prompt = FixGenerator._build_prompt(SAMPLE_BROKEN_CODE, SAMPLE_DIAGNOSIS)

    assert "Missing colon" in prompt
    assert "def multiply(x, y)" in prompt
    assert "Add colon" in prompt
    assert "main.py" in prompt
    assert "# line 1:" in prompt
    assert "# line 4:" in prompt
