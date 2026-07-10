"""Tests for AutoFixAgent and FixPlan schema.

No real Jenkins, no real LLM, no real GitHub.
Uses tmp_path for file isolation and patches builtins.input for the confirmation gate.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline_doctor.agent.auto_fix_agent import AutoFixAgent
from pipeline_doctor.agent.diagnosis_schema import Diagnosis
from pipeline_doctor.agent.fix_plan_schema import FixPlan


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_diagnosis(
    error_type: str = "syntax_error",
    affected_file: str | None = "main.py",
    root_cause: str = "Missing colon in function definition.",
) -> Diagnosis:
    return Diagnosis(
        error_type=error_type,
        failed_stage="Build",
        root_cause=root_cause,
        root_cause_evidence="def multiply(x, y)",
        fix_suggestion="Add missing colon to the function definition.",
        confidence=0.9,
        affected_file=affected_file,
        affected_line=5,
    )


def make_syntax_repo(tmp_path: Path, broken: bool = True) -> Path:
    repo_dir = tmp_path / "failing-syntax"
    repo_dir.mkdir()
    content = (
        "def add(a, b):\n    return a + b\n\ndef multiply(x, y)\n    return x * y\n"
        if broken
        else "def add(a, b):\n    return a + b\n\ndef multiply(x, y):\n    return x * y\n"
    )
    (repo_dir / "main.py").write_text(content, encoding="utf-8")
    return repo_dir


# ── FixPlan schema ────────────────────────────────────────────────────────────


class TestFixPlanSchema:
    def test_valid_plan_creates(self):
        plan = FixPlan(
            job_name="failing-syntax",
            build_number=2,
            error_type="syntax_error",
            root_cause="Missing colon",
            affected_file="main.py",
            proposed_change="def multiply(x, y) → def multiply(x, y):",
            safe_to_apply=True,
            requires_confirmation=True,
            explanation="Deterministisch erkannter Fehler.",
        )
        assert plan.job_name == "failing-syntax"
        assert plan.build_number == 2
        assert plan.safe_to_apply is True
        assert plan.requires_confirmation is True

    def test_affected_file_optional(self):
        plan = FixPlan(
            job_name="failing-tests",
            build_number=4,
            error_type="test_failure",
            root_cause="Wrong assertion",
            affected_file=None,
            proposed_change="Keine automatische Änderung.",
            safe_to_apply=False,
            requires_confirmation=True,
            explanation="Test oder Implementierung unklar.",
        )
        assert plan.affected_file is None
        assert plan.safe_to_apply is False

    def test_requires_confirmation_default_true(self):
        plan = FixPlan(
            job_name="x",
            build_number=1,
            error_type="unknown",
            root_cause="?",
            proposed_change="none",
            safe_to_apply=False,
            explanation="n/a",
        )
        assert plan.requires_confirmation is True


# ── syntax_error plan ─────────────────────────────────────────────────────────


class TestSyntaxFixPlan:
    def test_syntax_error_planned_correctly(self, tmp_path):
        make_syntax_repo(tmp_path)
        agent = AutoFixAgent(test_repos_root=tmp_path)
        diagnosis = make_diagnosis("syntax_error", "main.py")
        plan = agent.plan_fix(diagnosis, "failing-syntax", 2)

        assert plan.error_type == "syntax_error"
        assert plan.safe_to_apply is True
        assert plan.requires_confirmation is True
        assert "multiply" in plan.proposed_change

    def test_syntax_fix_describes_exact_line(self, tmp_path):
        make_syntax_repo(tmp_path)
        agent = AutoFixAgent(test_repos_root=tmp_path)
        plan = agent.plan_fix(make_diagnosis("syntax_error", "main.py"), "failing-syntax", 2)
        # Change description must include both the old and fixed form
        assert "def multiply(x, y)" in plan.proposed_change
        assert "def multiply(x, y):" in plan.proposed_change

    def test_syntax_not_safe_when_file_missing(self, tmp_path):
        (tmp_path / "failing-syntax").mkdir()
        # No main.py created
        agent = AutoFixAgent(test_repos_root=tmp_path)
        plan = agent.plan_fix(make_diagnosis("syntax_error", "main.py"), "failing-syntax", 2)
        assert plan.safe_to_apply is False

    def test_syntax_not_safe_when_no_affected_file(self, tmp_path):
        make_syntax_repo(tmp_path)
        agent = AutoFixAgent(test_repos_root=tmp_path)
        plan = agent.plan_fix(make_diagnosis("syntax_error", None), "failing-syntax", 2)
        assert plan.safe_to_apply is False

    def test_syntax_not_safe_when_already_correct(self, tmp_path):
        make_syntax_repo(tmp_path, broken=False)
        agent = AutoFixAgent(test_repos_root=tmp_path)
        plan = agent.plan_fix(make_diagnosis("syntax_error", "main.py"), "failing-syntax", 2)
        assert plan.safe_to_apply is False


# ── dependency_not_found ──────────────────────────────────────────────────────


class TestDependencyPlan:
    def test_dependency_not_safe(self, tmp_path):
        agent = AutoFixAgent(test_repos_root=tmp_path)
        plan = agent.plan_fix(
            make_diagnosis("dependency_not_found", "requirements.txt"), "failing-dependency", 3
        )
        assert plan.safe_to_apply is False
        assert plan.error_type == "dependency_not_found"

    def test_dependency_no_file_change_even_on_yes(self, tmp_path):
        repo_dir = tmp_path / "failing-dependency"
        repo_dir.mkdir()
        req = repo_dir / "requirements.txt"
        original = "this-package-does-not-exist==1.0\n"
        req.write_text(original, encoding="utf-8")

        agent = AutoFixAgent(test_repos_root=tmp_path)
        with patch("builtins.input", return_value="y"):
            applied = agent.run(
                make_diagnosis("dependency_not_found", "requirements.txt"),
                "failing-dependency",
                3,
            )

        assert applied is False
        assert req.read_text(encoding="utf-8") == original


# ── test_failure ──────────────────────────────────────────────────────────────


class TestTestFailurePlan:
    def test_test_failure_not_safe(self, tmp_path):
        agent = AutoFixAgent(test_repos_root=tmp_path)
        plan = agent.plan_fix(
            make_diagnosis("test_failure", "test_main.py"), "failing-tests", 4
        )
        assert plan.safe_to_apply is False
        assert plan.error_type == "test_failure"

    def test_test_failure_no_file_change_even_on_yes(self, tmp_path):
        repo_dir = tmp_path / "failing-tests"
        repo_dir.mkdir()
        test_file = repo_dir / "test_main.py"
        original = "assert add(1, 1) == 3\n"
        test_file.write_text(original, encoding="utf-8")

        agent = AutoFixAgent(test_repos_root=tmp_path)
        with patch("builtins.input", return_value="y"):
            applied = agent.run(
                make_diagnosis("test_failure", "test_main.py"), "failing-tests", 4
            )

        assert applied is False
        assert test_file.read_text(encoding="utf-8") == original


# ── Confirmation gate ─────────────────────────────────────────────────────────


class TestConfirmationGate:
    def test_fix_applied_on_yes(self, tmp_path):
        make_syntax_repo(tmp_path)
        agent = AutoFixAgent(test_repos_root=tmp_path)

        with patch("builtins.input", return_value="y"), \
             patch.object(agent, "_show_git_diff"):
            applied = agent.run(make_diagnosis("syntax_error", "main.py"), "failing-syntax", 2)

        assert applied is True
        content = (tmp_path / "failing-syntax" / "main.py").read_text(encoding="utf-8")
        assert "def multiply(x, y):" in content

    def test_fix_applied_on_yes_uppercase(self, tmp_path):
        make_syntax_repo(tmp_path)
        agent = AutoFixAgent(test_repos_root=tmp_path)

        with patch("builtins.input", return_value="Y"), \
             patch.object(agent, "_show_git_diff"):
            applied = agent.run(make_diagnosis("syntax_error", "main.py"), "failing-syntax", 2)

        assert applied is True

    def test_fix_not_applied_on_no(self, tmp_path):
        make_syntax_repo(tmp_path)
        original = (tmp_path / "failing-syntax" / "main.py").read_text(encoding="utf-8")
        agent = AutoFixAgent(test_repos_root=tmp_path)

        with patch("builtins.input", return_value="n"):
            applied = agent.run(make_diagnosis("syntax_error", "main.py"), "failing-syntax", 2)

        assert applied is False
        assert (tmp_path / "failing-syntax" / "main.py").read_text(encoding="utf-8") == original

    def test_fix_not_applied_on_enter(self, tmp_path):
        make_syntax_repo(tmp_path)
        original = (tmp_path / "failing-syntax" / "main.py").read_text(encoding="utf-8")
        agent = AutoFixAgent(test_repos_root=tmp_path)

        with patch("builtins.input", return_value=""):
            applied = agent.run(make_diagnosis("syntax_error", "main.py"), "failing-syntax", 2)

        assert applied is False
        assert (tmp_path / "failing-syntax" / "main.py").read_text(encoding="utf-8") == original

    def test_fix_not_applied_on_arbitrary_input(self, tmp_path):
        make_syntax_repo(tmp_path)
        original = (tmp_path / "failing-syntax" / "main.py").read_text(encoding="utf-8")
        agent = AutoFixAgent(test_repos_root=tmp_path)

        with patch("builtins.input", return_value="maybe"):
            applied = agent.run(make_diagnosis("syntax_error", "main.py"), "failing-syntax", 2)

        assert applied is False
        assert (tmp_path / "failing-syntax" / "main.py").read_text(encoding="utf-8") == original


# ── Colon fix correctness ─────────────────────────────────────────────────────


class TestColonFix:
    def test_colon_added_only_to_def_without_colon(self, tmp_path):
        make_syntax_repo(tmp_path)
        agent = AutoFixAgent(test_repos_root=tmp_path)
        file_path = tmp_path / "failing-syntax" / "main.py"
        changes = AutoFixAgent._find_missing_colons(file_path.read_text(encoding="utf-8"))

        AutoFixAgent._apply_line_fixes(file_path, changes)

        lines = file_path.read_text(encoding="utf-8").splitlines()
        assert any(line.strip() == "def add(a, b):" for line in lines)
        assert any(line.strip() == "def multiply(x, y):" for line in lines)

    def test_existing_correct_defs_unchanged(self, tmp_path):
        make_syntax_repo(tmp_path, broken=False)
        file_path = tmp_path / "failing-syntax" / "main.py"
        original = file_path.read_text(encoding="utf-8")
        changes = AutoFixAgent._find_missing_colons(original)

        count = AutoFixAgent._apply_line_fixes(file_path, changes)

        assert count == 0
        assert file_path.read_text(encoding="utf-8") == original

    def test_find_missing_colons_returns_correct_line_number(self):
        content = "def add(a, b):\n    return a + b\n\ndef multiply(x, y)\n    return x * y\n"
        changes = AutoFixAgent._find_missing_colons(content)
        assert len(changes) == 1
        line_nr, original, fixed = changes[0]
        assert line_nr == 4
        assert original == "def multiply(x, y)"
        assert fixed == "def multiply(x, y):"

    def test_find_missing_colons_empty_on_correct_file(self):
        content = "def add(a, b):\n    return a + b\n"
        assert AutoFixAgent._find_missing_colons(content) == []

    def test_detect_syntax_error_finds_typo(self):
        content = "df multiply(x, y):\n    return x * y\n"
        result = AutoFixAgent._detect_syntax_error(content, "main.py")
        assert result is not None
        line_nr, broken_line, error_msg = result
        assert line_nr == 1
        assert "df multiply" in broken_line

    def test_detect_syntax_error_returns_none_on_valid(self):
        content = "def multiply(x, y):\n    return x * y\n"
        assert AutoFixAgent._detect_syntax_error(content, "main.py") is None

    def test_llm_fix_used_when_regex_fails(self, tmp_path):
        """compile() finds error, LLM provides fix → plan is safe."""
        repo_dir = tmp_path / "failing-syntax"
        repo_dir.mkdir()
        # 'df' typo — regex won't match, compile() will catch it
        (repo_dir / "main.py").write_text("df multiply(x, y):\n    return x * y\n", encoding="utf-8")

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content="def multiply(x, y):")

        agent = AutoFixAgent(test_repos_root=tmp_path, llm=mock_llm)
        plan = agent.plan_fix(make_diagnosis("syntax_error", "main.py"), "failing-syntax", 2)

        assert plan.safe_to_apply is True
        assert plan.line_fixes
        assert "def multiply(x, y):" in plan.line_fixes[0][2]
