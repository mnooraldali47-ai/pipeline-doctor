"""Tests for DiagnosisAgent."""

from unittest.mock import MagicMock, patch, call
import pytest

from pipeline_doctor.agent.diagnosis_schema import Diagnosis
from pipeline_doctor.agent.diagnosis_agent import DiagnosisAgent
from pipeline_doctor.tools.log_preprocessor import LogPreprocessor

# ── Shared fixtures ────────────────────────────────────────────────────────

_MOCK_DIAGNOSIS = Diagnosis(
    error_type="test_failure",
    failed_stage="Test",
    root_cause="Two test assertions failed with incorrect expected values.",
    root_cause_evidence="AssertionError: assert 2 == 3",
    fix_suggestion=(
        "Fix the expected values in test_main.py. "
        "assert add(1, 1) should expect 2, not 3."
    ),
    confidence=0.95,
    affected_file="test_main.py",
    affected_line=10,
)

_MOCK_LOG = """\
[Pipeline] { (Test)
+ python -m pytest -v
test_main.py::test_fail FAILED
test_main.py:10: AssertionError
assert 2 == 3
ERROR: script returned exit code 1
Finished: FAILURE
"""


@pytest.fixture
def mock_chain():
    """Structured-output chain that returns _MOCK_DIAGNOSIS."""
    chain = MagicMock()
    chain.invoke.return_value = {
        "raw": MagicMock(response_metadata={"token_usage": {
            "prompt_tokens": 200,
            "completion_tokens": 80,
            "total_tokens": 280,
        }}),
        "parsed": _MOCK_DIAGNOSIS,
        "parsing_error": None,
    }
    return chain


@pytest.fixture
def mock_llm(mock_chain):
    """LLM mock whose with_structured_output returns mock_chain."""
    llm = MagicMock()
    llm.with_structured_output.return_value = mock_chain
    return llm


@pytest.fixture
def agent(mock_llm):
    """DiagnosisAgent with get_llm() patched to avoid .env dependency."""
    with patch("pipeline_doctor.agent.diagnosis_agent.get_llm", return_value=mock_llm):
        return DiagnosisAgent()


# ── Instantiation ──────────────────────────────────────────────────────────

class TestInstantiation:
    def test_agent_uses_mocked_llm(self, mock_llm):
        with patch("pipeline_doctor.agent.diagnosis_agent.get_llm", return_value=mock_llm):
            a = DiagnosisAgent()
        assert a._llm is mock_llm

    def test_agent_creates_preprocessor(self, agent):
        assert isinstance(agent._preprocessor, LogPreprocessor)

    def test_structured_output_chain_configured(self, agent, mock_llm):
        mock_llm.with_structured_output.assert_called_once_with(
            Diagnosis, include_raw=True
        )


# ── diagnose() return type and values ─────────────────────────────────────

class TestDiagnoseReturnType:
    def test_returns_diagnosis_instance(self, agent):
        result = agent.diagnose(_MOCK_LOG)
        assert isinstance(result, Diagnosis)

    def test_error_type_matches(self, agent):
        assert agent.diagnose(_MOCK_LOG).error_type == "test_failure"

    def test_failed_stage_matches(self, agent):
        assert agent.diagnose(_MOCK_LOG).failed_stage == "Test"

    def test_confidence_in_valid_range(self, agent):
        c = agent.diagnose(_MOCK_LOG).confidence
        assert 0.0 <= c <= 1.0

    def test_root_cause_nonempty(self, agent):
        assert agent.diagnose(_MOCK_LOG).root_cause

    def test_fix_suggestion_nonempty(self, agent):
        assert agent.diagnose(_MOCK_LOG).fix_suggestion

    def test_evidence_nonempty(self, agent):
        assert agent.diagnose(_MOCK_LOG).root_cause_evidence


# ── LLM call mechanics ─────────────────────────────────────────────────────

class TestLLMInteraction:
    def test_chain_invoked_once(self, agent, mock_chain):
        agent.diagnose(_MOCK_LOG)
        mock_chain.invoke.assert_called_once()

    def test_prompt_contains_filtered_log(self, agent, mock_chain):
        agent.diagnose(_MOCK_LOG)
        messages = mock_chain.invoke.call_args[0][0]
        human_content = messages[1].content
        assert "Filtered build log" in human_content

    def test_prompt_contains_error_indicators(self, agent, mock_chain):
        agent.diagnose(_MOCK_LOG)
        messages = mock_chain.invoke.call_args[0][0]
        human_content = messages[1].content
        assert "error_indicators" in human_content

    def test_system_prompt_set(self, agent, mock_chain):
        agent.diagnose(_MOCK_LOG)
        messages = mock_chain.invoke.call_args[0][0]
        assert "CI/CD engineer" in messages[0].content


# ── Failed-stage fallback ──────────────────────────────────────────────────

class TestFailedStageFallback:
    def test_null_llm_stage_filled_from_preprocessor(self, mock_llm, mock_chain):
        """If LLM returns failed_stage=None, preprocessor value is used."""
        diagnosis_no_stage = _MOCK_DIAGNOSIS.model_copy(update={"failed_stage": None})
        mock_chain.invoke.return_value = {
            "raw": MagicMock(response_metadata={}),
            "parsed": diagnosis_no_stage,
            "parsing_error": None,
        }
        mock_llm.with_structured_output.return_value = mock_chain

        with patch("pipeline_doctor.agent.diagnosis_agent.get_llm", return_value=mock_llm):
            a = DiagnosisAgent()

        result = a.diagnose(_MOCK_LOG)
        # Preprocessor detects "Test" stage from _MOCK_LOG
        assert result.failed_stage == "Test"


# ── Error handling ─────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_raises_on_parsing_failure(self, agent, mock_chain):
        mock_chain.invoke.return_value = {
            "raw": MagicMock(response_metadata={}),
            "parsed": None,
            "parsing_error": Exception("bad JSON"),
        }
        with pytest.raises(ValueError, match="unparseable"):
            agent.diagnose(_MOCK_LOG)


# ── diagnose_from_file ─────────────────────────────────────────────────────

class TestDiagnoseFromFile:
    def test_reads_file_and_delegates(self, agent, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(_MOCK_LOG, encoding="utf-8")

        result = agent.diagnose_from_file(str(log_file))
        assert isinstance(result, Diagnosis)
        assert result.error_type == "test_failure"

    def test_missing_file_raises(self, agent):
        with pytest.raises(FileNotFoundError):
            agent.diagnose_from_file("/nonexistent/path/build.log")


# ── Live integration (skipped in CI) ──────────────────────────────────────

@pytest.mark.skip(reason="Requires live GWDG API — run manually: pytest -k live")
class TestLiveIntegration:
    def test_live_diagnose_tests_log(self):
        from pathlib import Path
        log_path = (
            Path(__file__).parent.parent / "logs" / "failing-tests-build-4.log"
        )
        a = DiagnosisAgent()
        result = a.diagnose_from_file(str(log_path))
        assert result.error_type in {
            "test_failure", "dependency_not_found", "syntax_error",
            "build_error", "unknown",
        }
        assert result.confidence >= 0.0
        assert result.root_cause
