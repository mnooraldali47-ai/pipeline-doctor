"""Sprint-3 CLI: diagnose a Jenkins job failure and optionally apply the fix.

Usage:
    python scripts/apply_suggested_fix.py --job failing-syntax
    python scripts/apply_suggested_fix.py --job failing-dependency
    python scripts/apply_suggested_fix.py --job failing-tests

The script:
    1. Finds the newest log file for the given job under logs/
    2. Runs DiagnosisAgent to produce a structured diagnosis
    3. Builds a FixPlan via AutoFixAgent
    4. Displays the plan and asks for confirmation
    5. Applies the fix only when safe_to_apply=True AND user answers "y"

No files outside test-repos/ are changed.
No git push, no pull requests.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path regardless of CWD
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from pipeline_doctor.agent.auto_fix_agent import AutoFixAgent
from pipeline_doctor.agent.diagnosis_agent import DiagnosisAgent
from pipeline_doctor.tools.jenkins_client import (
    JenkinsAuthError,
    JenkinsClient,
    JenkinsConnectionError,
    JenkinsError,
)

PROJECT_ROOT = Path(__file__).parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"

_KNOWN_JOBS = {"failing-dependency", "failing-syntax", "failing-tests"}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline Doctor Sprint 3 — Diagnose + bestätigter Auto-Fix"
    )
    parser.add_argument(
        "--job",
        required=True,
        help="Jenkins Job-Name, z.B. failing-syntax",
    )
    return parser.parse_args()


def _build_number_from_name(log_path: Path) -> int:
    """Extract build number from filename like 'failing-syntax-build-3.log'."""
    try:
        return int(log_path.stem.rsplit("-", 1)[-1])
    except (ValueError, IndexError):
        return 0


def find_latest_log(job: str) -> tuple[Path, int] | None:
    """Return (path, build_number) for the newest local log of *job*, or None."""
    LOGS_DIR.mkdir(exist_ok=True)
    candidates = list(LOGS_DIR.glob(f"{job}-build-*.log"))
    if not candidates:
        return None
    candidates.sort(key=_build_number_from_name)
    latest = candidates[-1]
    return latest, _build_number_from_name(latest)


def fetch_log_from_jenkins(job: str) -> tuple[str, int] | None:
    """Live-fetch the latest FAILURE log from Jenkins. Returns (text, build_nr) or None."""
    try:
        client = JenkinsClient()
        if not client.url:
            return None
        build_nr = client.get_latest_build_number(job)
        if not client.is_build_failed(job, build_nr):
            return None
        log_text = client.get_build_log(job, build_nr)
        return log_text, build_nr
    except (JenkinsAuthError, JenkinsConnectionError, JenkinsError):
        return None


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    args = _parse_args()
    job: str = args.job

    print(f"\n🔍 Pipeline Doctor — Sprint 3: Auto-Fix")
    print(f"   Job: {job}\n")

    # ── Step 1: Get log ──────────────────────────────────────────────────────
    result = find_latest_log(job)
    if result:
        log_path, build_nr = result
        print(f"   Log gefunden: {log_path.name} (Build #{build_nr})")
        try:
            raw_log = log_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"   ❌ Datei nicht lesbar: {e}")
            sys.exit(1)
    else:
        print(f"   Kein lokales Log für '{job}' — versuche Jenkins live ...")
        live = fetch_log_from_jenkins(job)
        if live is None:
            print(
                f"   ❌ Kein Log gefunden. Bitte zuerst ausführen:\n"
                f"      python scripts/fetch_failure_logs.py"
            )
            sys.exit(1)
        raw_log, build_nr = live
        saved = LOGS_DIR / f"{job}-build-{build_nr}.log"
        LOGS_DIR.mkdir(exist_ok=True)
        saved.write_text(raw_log, encoding="utf-8")
        print(f"   Log gespeichert: {saved.name}")

    # ── Step 2: Diagnose ─────────────────────────────────────────────────────
    print("\n   Analysiere Log mit LLM ...")
    try:
        agent = DiagnosisAgent()
        diagnosis, stats = agent.diagnose_with_stats(raw_log)
    except Exception as e:
        print(f"   ❌ Diagnose fehlgeschlagen: {e}")
        sys.exit(1)

    preprocessed = stats["preprocessed"]
    saved_pct = (1 - preprocessed["compression_ratio"]) * 100
    print(
        f"   Log: {preprocessed['original_size']} → {preprocessed['compressed_size']} Bytes "
        f"({saved_pct:.0f}% gespart)"
    )
    print(
        f"   Diagnose: {diagnosis.error_type} "
        f"(Konfidenz {diagnosis.confidence:.2f}, {stats['llm_time']:.1f}s)"
    )

    # ── Step 3: Fix-Workflow ─────────────────────────────────────────────────
    fix_agent = AutoFixAgent()
    applied = fix_agent.run(diagnosis, job, build_nr)

    if not applied:
        print("\n   Keine Änderungen vorgenommen.")
    print()


if __name__ == "__main__":
    main()
