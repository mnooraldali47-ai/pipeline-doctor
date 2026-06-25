"""AutoFixAgent — proposes and (with confirmation) applies fixes to test-repos.

Workflow:
    1. plan_fix()  — analyse Diagnosis, build FixPlan
    2. run()       — display plan, ask [y/N], apply only on "y"

Only syntax_error is automatically applied (regex, deterministic).
dependency_not_found and test_failure are shown but deliberately blocked.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

from .diagnosis_schema import Diagnosis
from .fix_plan_schema import FixPlan

# Matches a function def that has NO colon at the end, e.g. "def foo(x, y)"
_DEF_WITHOUT_COLON = re.compile(r"^(\s*def\s+\w+\s*\([^)]*\))\s*$")


class AutoFixAgent:
    """Plans and (after confirmation) applies fixes to test-repo source files.

    Args:
        test_repos_root: Override the default test-repos/ directory.
            Useful in tests; defaults to <project_root>/test-repos/.
    """

    def __init__(self, test_repos_root: Optional[Path] = None) -> None:
        if test_repos_root is None:
            self._repos_root = Path(__file__).parent.parent.parent / "test-repos"
        else:
            self._repos_root = Path(test_repos_root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plan_fix(
        self,
        diagnosis: Diagnosis,
        job_name: str,
        build_number: int,
    ) -> FixPlan:
        """Derive a FixPlan from a Diagnosis.

        Args:
            diagnosis: Structured diagnosis from DiagnosisAgent.
            job_name: Jenkins job name (= directory under test-repos/).
            build_number: Build number used for reporting.

        Returns:
            FixPlan describing what would be changed and whether it is safe.
        """
        if diagnosis.error_type == "syntax_error":
            return self._plan_syntax_fix(diagnosis, job_name, build_number)
        if diagnosis.error_type == "dependency_not_found":
            return self._plan_dependency_fix(diagnosis, job_name, build_number)
        if diagnosis.error_type == "test_failure":
            return self._plan_test_failure(diagnosis, job_name, build_number)
        return self._plan_unknown(diagnosis, job_name, build_number)

    def run(
        self,
        diagnosis: Diagnosis,
        job_name: str,
        build_number: int,
    ) -> bool:
        """Full interactive workflow: show plan, ask, apply if confirmed.

        Args:
            diagnosis: Structured diagnosis from DiagnosisAgent.
            job_name: Jenkins job name.
            build_number: Build number.

        Returns:
            True if the fix was applied, False otherwise.
        """
        plan = self.plan_fix(diagnosis, job_name, build_number)
        self._display_plan(plan)

        if not plan.safe_to_apply:
            print("\n⛔  Dieser Fix wird nicht automatisch angewendet.")
            print(f"   Grund: {plan.explanation}")
            return False

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
            return FixPlan(
                job_name=job_name,
                build_number=build_number,
                error_type="syntax_error",
                root_cause=diagnosis.root_cause,
                affected_file=None,
                proposed_change="Keine betroffene Datei identifiziert.",
                safe_to_apply=False,
                requires_confirmation=True,
                explanation="Datei unbekannt — Fix kann nicht automatisch angewendet werden.",
            )

        file_path = self._repos_root / job_name / affected_file
        if not file_path.exists():
            return FixPlan(
                job_name=job_name,
                build_number=build_number,
                error_type="syntax_error",
                root_cause=diagnosis.root_cause,
                affected_file=affected_file,
                proposed_change=f"Datei {affected_file} nicht gefunden unter test-repos/{job_name}/",
                safe_to_apply=False,
                requires_confirmation=True,
                explanation="Datei existiert nicht im lokalen test-repo.",
            )

        content = file_path.read_text(encoding="utf-8")
        changes = self._find_missing_colons(content)

        if not changes:
            return FixPlan(
                job_name=job_name,
                build_number=build_number,
                error_type="syntax_error",
                root_cause=diagnosis.root_cause,
                affected_file=affected_file,
                proposed_change="Kein automatisch erkennbares Syntaxproblem (fehlender Doppelpunkt) gefunden.",
                safe_to_apply=False,
                requires_confirmation=True,
                explanation=(
                    "Automatische Erkennung deckt nur fehlende Doppelpunkte in "
                    "Funktionsdefinitionen ab. Bitte manuell prüfen."
                ),
            )

        change_lines = "\n".join(
            f"   Zeile {ln}: {old!r}  →  {new!r}" for ln, old, new in changes
        )
        return FixPlan(
            job_name=job_name,
            build_number=build_number,
            error_type="syntax_error",
            root_cause=diagnosis.root_cause,
            affected_file=affected_file,
            proposed_change=change_lines,
            safe_to_apply=True,
            requires_confirmation=True,
            explanation=(
                "Fehlender Doppelpunkt in Funktionsdefinition erkannt. "
                "Fix ist deterministisch und sicher."
            ),
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
                "Mögliche Maßnahmen:\n"
                "   1. Paketnamen prüfen (Tippfehler?)\n"
                "   2. Falsches Paket aus requirements.txt entfernen\n"
                "   3. Durch korrektes Paket ersetzen"
            ),
            safe_to_apply=False,
            requires_confirmation=True,
            explanation=(
                "Dependency-Fehler sind nicht automatisch sicher behebbar — "
                "blindes Löschen kann andere Fehler erzeugen. Bitte manuell prüfen."
            ),
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
                "Assertion stimmt nicht mit tatsächlichem Ergebnis überein.\n"
                "   Optionen (manuell entscheiden):\n"
                "   A) Test-Erwartung korrigieren, wenn Test falsch ist\n"
                "   B) Implementierung korrigieren, wenn Logik falsch ist"
            ),
            safe_to_apply=False,
            requires_confirmation=True,
            explanation=(
                "Test-Failures erfordern menschliches Urteil: "
                "unklar ob Test oder Implementierung geändert werden soll."
            ),
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
            proposed_change="Kein automatischer Fix für diesen Fehlertyp verfügbar.",
            safe_to_apply=False,
            requires_confirmation=True,
            explanation=f"Fehlertyp '{diagnosis.error_type}' wird in Sprint 3 nicht automatisch behoben.",
        )

    # ------------------------------------------------------------------
    # Apply helpers
    # ------------------------------------------------------------------

    def _apply_fix(self, plan: FixPlan) -> None:
        if plan.error_type == "syntax_error" and plan.affected_file:
            file_path = self._repos_root / plan.job_name / plan.affected_file
            count = self._apply_syntax_colon_fix(file_path)
            print(f"\n   {count} Zeile(n) in {file_path.name} korrigiert.")

    def _apply_syntax_colon_fix(self, file_path: Path) -> int:
        """Add missing colons to function defs in file. Returns count fixed."""
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines(keepends=True)
        fixed_count = 0
        result: list[str] = []
        for line in lines:
            if _DEF_WITHOUT_COLON.match(line):
                new_line = line.rstrip("\n\r").rstrip() + ":\n"
                result.append(new_line)
                fixed_count += 1
            else:
                result.append(line)
        if fixed_count:
            file_path.write_text("".join(result), encoding="utf-8")
        return fixed_count

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
                print("\n── git diff ────────────────────────────────────────")
                print(diff)
                print("────────────────────────────────────────────────────")
            else:
                print("\n   (kein git diff — Datei möglicherweise nicht getrackt)")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print("\n   (git diff nicht verfügbar)")

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_missing_colons(content: str) -> list[tuple[int, str, str]]:
        """Return (line_nr, original_stripped, fixed_stripped) for each def missing ':'."""
        changes: list[tuple[int, str, str]] = []
        for i, line in enumerate(content.splitlines(), start=1):
            if _DEF_WITHOUT_COLON.match(line):
                original = line.strip()
                fixed = original + ":"
                changes.append((i, original, fixed))
        return changes

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    @staticmethod
    def _display_plan(plan: FixPlan) -> None:
        safety = "✅ Sicher (nach Bestätigung)" if plan.safe_to_apply else "⛔ Nicht automatisch"
        print()
        print("━" * 54)
        print(" DIAGNOSE & FIX-PLAN")
        print("━" * 54)
        print(f"  Job             : {plan.job_name}")
        print(f"  Build           : #{plan.build_number}")
        print(f"  Fehlertyp       : {plan.error_type}")
        print(f"  Ursache         : {plan.root_cause}")
        print(f"  Betroffene Datei: {plan.affected_file or '—'}")
        print(f"  Sicherheit      : {safety}")
        print()
        print("  Vorgeschlagene Änderung:")
        for line in plan.proposed_change.splitlines():
            print(f"  {line}")
        print()
        print(f"  Erklärung: {plan.explanation}")
        print("━" * 54)
