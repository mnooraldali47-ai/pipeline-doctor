"""Tests for LogPreprocessor."""

import pytest
from pipeline_doctor.tools.log_preprocessor import LogPreprocessor

# ── Mock log with realistic Jenkins structure ──────────────────────────────
# Contains: git checkout boilerplate, Pipeline frames, one failing test stage.
_MOCK_LOG = """\
Started by user Test
Obtained Jenkinsfile from git https://github.com/test/repo.git
[Pipeline] Start of Pipeline
[Pipeline] node
Running on Jenkins in /var/jenkins_home/workspace/test
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Declarative: Checkout SCM)
[Pipeline] checkout
Selected Git installation does not exist. Using Default
The recommended git tool is: NONE
No credentials specified
 > git rev-parse --resolve-git-dir /var/jenkins_home/workspace/test/.git # timeout=10
Fetching changes from the remote Git repository
 > git config remote.origin.url https://github.com/test/repo.git # timeout=10
Fetching upstream changes from https://github.com/test/repo.git
 > git --version # timeout=10
 > git --version # 'git version 2.47.3'
 > git fetch --tags --force --progress -- https://github.com/test/repo.git +refs/heads/*:refs/remotes/origin/* # timeout=10
 > git rev-parse refs/remotes/origin/master^{commit} # timeout=10
Checking out Revision abc123 (refs/remotes/origin/master)
 > git config core.sparsecheckout # timeout=10
 > git checkout -f abc123 # timeout=10
[Pipeline] }
[Pipeline] // stage
[Pipeline] withEnv
[Pipeline] {
[Pipeline] stage
[Pipeline] { (Install Dependencies)
[Pipeline] sh
+ pip install -r requirements.txt
Requirement already satisfied: pytest
Requirement already satisfied: iniconfig
Requirement already satisfied: packaging
[Pipeline] }
[Pipeline] // stage
[Pipeline] stage
[Pipeline] { (Test)
[Pipeline] sh
+ python -m pytest -v
============================= test session starts ==============================
collected 2 items
test_foo.py::test_ok PASSED
test_foo.py::test_fail FAILED
=================================== FAILURES ===================================
def test_fail():
>       assert 1 == 2
E       assert 1 == 2
test_foo.py:5: AssertionError
=========================== 1 failed, 1 passed in 0.01s ==========================
[Pipeline] }
[Pipeline] // stage
[Pipeline] stage
[Pipeline] { (Declarative: Post Actions)
[Pipeline] echo
BUILD FAILED: tests failed.
[Pipeline] }
[Pipeline] // stage
[Pipeline] }
[Pipeline] // withEnv
[Pipeline] }
[Pipeline] // node
[Pipeline] End of Pipeline
ERROR: script returned exit code 1
Finished: FAILURE
"""


@pytest.fixture
def preprocessor() -> LogPreprocessor:
    return LogPreprocessor(max_lines=80)


@pytest.fixture
def result(preprocessor: LogPreprocessor) -> dict:
    return preprocessor.preprocess(_MOCK_LOG)


class TestCompressionRatio:
    def test_ratio_below_50_percent(self, result: dict) -> None:
        assert result["compression_ratio"] < 0.5, (
            f"Expected <50% retention, got {result['compression_ratio']:.0%}. "
            "Boilerplate removal may be broken."
        )

    def test_sizes_consistent(self, result: dict) -> None:
        assert result["compressed_size"] <= result["original_size"]
        assert result["compressed_size"] == len(
            result["filtered_text"].encode("utf-8")
        )


class TestErrorDetection:
    def test_assertion_error_detected(self, result: dict) -> None:
        assert "AssertionError" in result["error_indicators"]

    def test_failed_keyword_detected(self, result: dict) -> None:
        assert "FAILED" in result["error_indicators"]

    def test_exit_code_detected(self, result: dict) -> None:
        assert "exit code 1" in result["error_indicators"]

    def test_failed_stage_is_test(self, result: dict) -> None:
        assert result["failed_stage"] == "Test"


class TestBoilerplateRemoval:
    def test_git_commands_removed(self, result: dict) -> None:
        for line in result["filtered_text"].splitlines():
            assert not line.strip().startswith("> git"), (
                f"Git command leaked into output: {line!r}"
            )

    def test_pipeline_bare_brace_removed(self, result: dict) -> None:
        assert "[Pipeline] {" not in result["filtered_text"].splitlines()

    def test_pipeline_close_brace_removed(self, result: dict) -> None:
        for line in result["filtered_text"].splitlines():
            assert line.strip() != "[Pipeline] }", f"Close brace leaked: {line!r}"

    def test_pipeline_sh_removed(self, result: dict) -> None:
        assert "[Pipeline] sh" not in result["filtered_text"]

    def test_empty_lines_removed(self, result: dict) -> None:
        for line in result["filtered_text"].splitlines():
            assert line.strip() != ""


class TestContentPreserved:
    def test_assertion_error_in_text(self, result: dict) -> None:
        assert "AssertionError" in result["filtered_text"]

    def test_stage_marker_preserved(self, result: dict) -> None:
        assert "[Pipeline] { (Test)" in result["filtered_text"]

    def test_exit_code_line_preserved(self, result: dict) -> None:
        assert "exit code 1" in result["filtered_text"]


class TestTrimming:
    def test_trim_respects_max_lines(self) -> None:
        preprocessor = LogPreprocessor(max_lines=5)
        long_log = "\n".join(
            [f"ERROR: something bad line {i}" for i in range(100)]
        )
        result = preprocessor.preprocess(long_log)
        lines = result["filtered_text"].splitlines()
        assert len(lines) <= 6  # 5 + trim marker

    def test_trim_marker_present_when_trimmed(self) -> None:
        preprocessor = LogPreprocessor(max_lines=3)
        long_log = "\n".join(
            [f"ERROR: bad line {i}" for i in range(50)]
        )
        result = preprocessor.preprocess(long_log)
        assert "Zeilen gekürzt" in result["filtered_text"]

    def test_no_trim_marker_when_fits(self, result: dict) -> None:
        assert "Zeilen gekürzt" not in result["filtered_text"]
