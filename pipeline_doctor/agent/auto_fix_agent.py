"""AutoFixAgent — proposes and (with confirmation) applies fixes to test-repos.

Workflow:
    1. plan_fix()  — analyse Diagnosis, build FixPlan
    2. run()       — display plan, ask [y/N], apply only on "y"

Syntax error detection strategy (in order):
    1. Regex: missing colon on function/class/if/for/while definition line
    2. compile() fallback: detect any SyntaxError, then ask LLM for the corrected line

dependency_not_found and test_failure: shown compactly, never applied automatically.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .diagnosis_schema import Diagnosis
from .fix_plan_schema import FixPlan

# Matches any block-opening statement that requires a colon but has none, e.g.:
#   def foo(x, y)
#   class Bar
#   if x > 0
#   for i in range(10)
#   while True
_MISSING_COLON = re.compile(
    r"^(\s*(?:def|class|if|elif|else|for|while|with|try|except|finally)\b[^:#]*)\s*$"
)


class AutoFixAgent:
    """Plans and (after confirmation) applies fixes to test-repo source files.

    Args:
        test_repos_root: Override the default test-repos/ directory (for tests).
        llm: Inject an LLM instance (for tests). None = lazy-load via get_llm().
    """

    def __init__(
        self,
        test_repos_root: Optional[Path] = None,
        llm=None,
    ) -> None:
        if test_repos_root is None:
            self._repos_root = Path(__file__).parent.parent.parent / "test-repos"
        else:
            self._repos_root = Path(test_repos_root)
        self._llm = llm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan_fix(
        self,
        diagnosis: Diagnosis,
        job_name: str,
        build_number: int,
    ) -> FixPlan:
        """Derive a FixPlan from a Diagnosis."""
        normalized = self._normalize_error_type(diagnosis.error_type)
        if normalized == "syntax_error":
            return self._plan_syntax_fix(diagnosis, job_name, build_number)
        if normalized == "dependency_not_found":
            return self._plan_dependency_fix(diagnosis, job_name, build_number)
        if normalized == "test_failure":
            return self._plan_test_failure(diagnosis, job_name, build_number)
        return self._plan_unknown(diagnosis, job_name, build_number)

    def run(
        self,
        diagnosis: Diagnosis,
        job_name: str,
        build_number: int,
    ) -> bool:
        """Full interactive workflow: show plan, ask, apply if confirmed.

        Returns:
            True if the fix was applied, False otherwise.
        """
        plan = self.plan_fix(diagnosis, job_name, build_number)

        if not plan.safe_to_apply:
            print(f"\n⛔ {plan.error_type}: {plan.explanation}")
            return False

        self._display_plan(plan)
        answer = input("\nMöchtest du diesen Fix anwenden? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("   Abgebrochen — keine Änderungen vorgenommen.")
            return False

        self._apply_fix(plan)
        self._show_git_diff(job_name)
        print("\n✅  Fix erfolgreich angewendet.")
        return True

    # ------------------------------------------------------------------
    # Plan builders
    # ------------------------------------------------------------------

    def _plan_syntax_fix(
        self, diagnosis: Diagnosis, job_name: str, build_number: int
    ) -> FixPlan:
        affected_file = diagnosis.affected_file
        if not affected_file:
            return self._unsafe_plan(diagnosis, job_name, build_number,
                                     "Keine betroffene Datei identifiziert.")

        file_path = self._repos_root / job_name / affected_file
        if not file_path.exists():
            return self._unsafe_plan(diagnosis, job_name, build_number,
                                     f"{affected_file} nicht gefunden unter test-repos/{job_name}/")

        content = file_path.read_text(encoding="utf-8")

        # ── Strategy 1: regex ─────────────────────────────────────────
        changes = self._find_missing_colons(content)
        if changes:
            proposed = "\n".join(
                f"   Zeile {ln}: {old.strip()!r}  →  {new.strip()!r}"
                for ln, old, new in changes
            )
            return FixPlan(
                job_name=job_name,
                build_number=build_number,
                error_type="syntax_error",
                root_cause=diagnosis.root_cause,
                affected_file=affected_file,
                proposed_change=proposed,
                safe_to_apply=True,
                requires_confirmation=True,
                explanation="Fehlender Doppelpunkt erkannt — deterministischer Fix.",
                line_fixes=changes,
            )

        # ── Strategy 2: compile() + LLM ──────────────────────────────
        error = self._detect_syntax_error(content, affected_file)
        if error:
            line_nr, broken_line, error_msg = error
            fixed_line = self._llm_fix_syntax_line(
                broken_line.strip(), error_msg, affected_file
            )
            if fixed_line:
                indent = len(broken_line) - len(broken_line.lstrip())
                full_fixed = " " * indent + fixed_line.lstrip()
                proposed = (
                    f"   Zeile {line_nr}: {broken_line.rstrip()!r}\n"
                    f"          →  {full_fixed!r}"
                )
                return FixPlan(
                    job_name=job_name,
                    build_number=build_number,
                    error_type="syntax_error",
                    root_cause=diagnosis.root_cause,
                    affected_file=affected_file,
                    proposed_change=proposed,
                    safe_to_apply=True,
                    requires_confirmation=True,
                    explanation=f"SyntaxError auf Zeile {line_nr} ({error_msg}) — LLM-Fix.",
                    line_fixes=[(line_nr, broken_line.rstrip(), full_fixed)],
                )
            return self._unsafe_plan(
                diagnosis, job_name, build_number,
                f"SyntaxError auf Zeile {line_nr} erkannt, aber LLM konnte keinen Fix generieren."
            )

        return self._unsafe_plan(
            diagnosis, job_name, build_number,
            "Kein Syntaxproblem in der Datei gefunden — möglicherweise bereits gefixt."
        )

    def _plan_dependency_fix(
        self, diagnosis: Diagnosis, job_name: str, build_number: int
    ) -> FixPlan:
        return FixPlan(
            job_name=job_name,
            build_number=build_number,
            error_type="dependency_not_found",
            root_cause=diagnosis.root_cause,
            affected_file=diagnosis.affected_file,
            proposed_change=(
                "1. Paketnamen prüfen (Tippfehler?)\n"
                "2. Falsches Paket aus requirements.txt entfernen\n"
                "3. Durch korrektes Paket ersetzen"
            ),
            safe_to_apply=False,
            requires_confirmation=True,
            explanation="Blindes Löschen kann Folgefehler erzeugen — manuell prüfen.",
        )

    def _plan_test_failure(
        self, diagnosis: Diagnosis, job_name: str, build_number: int
    ) -> FixPlan:
        return FixPlan(
            job_name=job_name,
            build_number=build_number,
            error_type="test_failure",
            root_cause=diagnosis.root_cause,
            affected_file=diagnosis.affected_file,
            proposed_change=(
                "A) Test-Erwartung korrigieren, wenn Test falsch ist\n"
                "B) Implementierung korrigieren, wenn Logik falsch ist"
            ),
            safe_to_apply=False,
            requires_confirmation=True,
            explanation="Unklar ob Test oder Implementierung geändert werden soll.",
        )

    def _plan_unknown(
        self, diagnosis: Diagnosis, job_name: str, build_number: int
    ) -> FixPlan:
        return FixPlan(
            job_name=job_name,
            build_number=build_number,
            error_type=diagnosis.error_type,
            root_cause=diagnosis.root_cause,
            affected_file=diagnosis.affected_file,
            proposed_change="Kein automatischer Fix verfügbar.",
            safe_to_apply=False,
            requires_confirmation=True,
            explanation=f"Fehlertyp '{diagnosis.error_type}' wird nicht automatisch behoben.",
        )

    def _unsafe_plan(
        self,
        diagnosis: Diagnosis,
        job_name: str,
        build_number: int,
        explanation: str,
    ) -> FixPlan:
        return FixPlan(
            job_name=job_name,
            build_number=build_number,
            error_type="syntax_error",
            root_cause=diagnosis.root_cause,
            affected_file=diagnosis.affected_file,
            proposed_change="Kein automatischer Fix möglich.",
            safe_to_apply=False,
            requires_confirmation=True,
            explanation=explanation,
        )

    # ------------------------------------------------------------------
    # Apply helpers
    # ------------------------------------------------------------------

    def _apply_fix(self, plan: FixPlan) -> None:
        if plan.line_fixes and plan.affected_file:
            file_path = self._repos_root / plan.job_name / plan.affected_file
            count = self._apply_line_fixes(file_path, plan.line_fixes)
            print(f"\n   {count} Zeile(n) in {file_path.name} korrigiert.")

    @staticmethod
    def _apply_line_fixes(
        file_path: Path, line_fixes: list[tuple[int, str, str]]
    ) -> int:
        """Replace lines in file. line_fixes = [(line_nr_1based, old_no_newline, new_no_newline)]."""
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        count = 0
        for line_nr, old, new in line_fixes:
            idx = line_nr - 1
            if idx < len(lines) and lines[idx].rstrip("\n\r") == old:
                eol = "\r\n" if lines[idx].endswith("\r\n") else "\n"
                lines[idx] = new + eol
                count += 1
        if count:
            file_path.write_text("".join(lines), encoding="utf-8")
        return count

    def _show_git_diff(self, job_name: str) -> None:
        repo_path = self._repos_root / job_name
        try:
            proc = subprocess.run(
                ["git", "diff"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                timeout=10,
            )
            diff = proc.stdout.strip()
            if diff:
                print("\n── git diff ─────────────────────────────────────────")
                print(diff)
                print("─────────────────────────────────────────────────────")
            else:
                print("\n   (kein git diff — Datei möglicherweise nicht getrackt)")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print("\n   (git diff nicht verfügbar)")

    # ------------------------------------------------------------------
    # Syntax detection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_missing_colons(content: str) -> list[tuple[int, str, str]]:
        """Return (line_nr_1based, old_line_no_newline, new_line_no_newline) for each line
        that looks like a block-opening statement without a trailing colon."""
        changes: list[tuple[int, str, str]] = []
        for i, line in enumerate(content.splitlines(), start=1):
            if _MISSING_COLON.match(line):
                old = line.rstrip()
                new = old + ":"
                changes.append((i, old, new))
        return changes

    @staticmethod
    def _detect_syntax_error(
        content: str, filename: str = "<file>"
    ) -> tuple[int, str, str] | None:
        """Run compile() and return (line_nr, full_line, error_msg) on SyntaxError, else None."""
        try:
            compile(content, filename, "exec")
            return None
        except SyntaxError as exc:
            lines = content.splitlines()
            line_nr = exc.lineno or 1
            broken = lines[line_nr - 1] if line_nr <= len(lines) else ""
            return line_nr, broken, exc.msg or "invalid syntax"

    def _llm_fix_syntax_line(
        self, broken_line: str, error_msg: str, filename: str
    ) -> str | None:
        """Ask LLM to return the corrected version of a single broken line.

        Returns the fixed line string, or None on failure.
        """
        try:
            llm = self._get_llm()
            resp = llm.invoke([
                SystemMessage(
                    content=(
                        "You are a Python expert. "
                        "Return ONLY the corrected line of code — no explanation, no backticks, "
                        "no extra text."
                    )
                ),
                HumanMessage(
                    content=(
                        f"Fix this Python syntax error.\n"
                        f"File: {filename}\n"
                        f"Error: {error_msg}\n"
                        f"Broken line: {broken_line!r}\n\n"
                        f"Return ONLY the corrected version of that single line."
                    )
                ),
            ])
            fixed = resp.content.strip().strip("`").strip()
            if fixed and fixed != broken_line:
                return fixed
        except Exception:
            pass
        return None

    def _get_llm(self):
        if self._llm is None:
            from .llm_config import get_llm
            self._llm = get_llm()
        return self._llm

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_error_type(error_type: str) -> str:
        """Map LLM-returned error_type variants to canonical snake_case keys."""
        t = error_type.lower().strip()
        if "syntax" in t:
            return "syntax_error"
        if "dependency" in t or "module" in t or "notfound" in t or "not_found" in t:
            return "dependency_not_found"
        if "test" in t and ("fail" in t or "assert" in t or "error" in t):
            return "test_failure"
        return t.replace(" ", "_").replace("-", "_")

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    @staticmethod
    def _display_plan(plan: FixPlan) -> None:
        print()
        print("━" * 54)
        print(f" FIX-PLAN: {plan.job_name} (Build #{plan.build_number})")
        print("━" * 54)
        print(f"  Fehlertyp : {plan.error_type}")
        print(f"  Ursache   : {plan.root_cause}")
        print(f"  Datei     : {plan.affected_file or '—'}")
        print()
        print("  Vorgeschlagene Änderung:")
        for line in plan.proposed_change.splitlines():
            print(f"  {line}")
        print("━" * 54)
