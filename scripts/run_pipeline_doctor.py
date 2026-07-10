"""Pipeline Doctor — End-to-End CLI.

One command that runs the complete autonomous fix workflow:
    Jenkins log → Diagnosis → Auto-Fix → Pull Request

Usage:
    # From a saved log file (no Jenkins required):
    python scripts/run_pipeline_doctor.py --log-file logs/failing-syntax-build-2.log --dry-run
    python scripts/run_pipeline_doctor.py --log-file logs/failing-syntax-build-2.log

    # Live from Jenkins:
    python scripts/run_pipeline_doctor.py --job failing-syntax
    python scripts/run_pipeline_doctor.py --job failing-syntax --dry-run
    python scripts/run_pipeline_doctor.py --job failing-tests --build 3 --repo my-repo
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

# Ensure project root is on sys.path so pipeline_doctor is importable
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline_doctor.tools.jenkins_client import (  # noqa: E402
    JenkinsAuthError,
    JenkinsClient,
    JenkinsConnectionError,
    JenkinsNotFoundError,
    JenkinsTimeoutError,
)
from pipeline_doctor.agent.diagnosis_agent import DiagnosisAgent  # noqa: E402
from pipeline_doctor.agent.auto_fix_deep_agent import create_auto_fix_agent  # noqa: E402


def _record_stats(
    job_name: str,
    build_number: int,
    diagnosis,
    mode: str,
    elapsed: float,
    success: bool,
    pr_url: str | None = None,
) -> None:
    """Record a run in the stats tracker. Non-fatal on any error."""
    try:
        from pipeline_doctor.reporting.stats_tracker import StatsTracker
        StatsTracker().record_run(
            job_name=job_name,
            build_number=build_number,
            error_type=diagnosis.error_type,
            confidence=diagnosis.confidence,
            mode=mode,
            elapsed_seconds=elapsed,
            success=success,
            pr_url=pr_url,
        )
        print("   📊 Stats updated")
    except Exception as exc:
        print(f"   ⚠️  Stats tracking failed: {exc}")


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Pipeline Doctor — Jenkins Log → Diagnosis → Auto-Fix → PR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    source = p.add_mutually_exclusive_group()
    source.add_argument(
        "--log-file",
        metavar="PATH",
        help=(
            "Path to a saved Jenkins log file "
            "(e.g. logs/failing-syntax-build-2.log). "
            "Job name and build number are extracted from the filename."
        ),
    )
    source.add_argument(
        "--job",
        help="Jenkins job name for live fetching, e.g. 'failing-syntax'",
    )
    p.add_argument(
        "--build",
        type=int,
        default=None,
        help="Build number (only with --job; default: latest build)",
    )
    p.add_argument(
        "--repo",
        default=None,
        help=(
            "GitHub repo name (default: 'pipeline-doctor-<job>', "
            "e.g. 'pipeline-doctor-failing-syntax')"
        ),
    )
    p.add_argument(
        "--mode",
        choices=["auto", "interactive", "preview"],
        default="auto",
        help=(
            "Fix mode: auto (default, no confirmation), "
            "interactive (ask before PR), "
            "preview (diagnosis only, no fix)"
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Diagnose only — alias for --mode preview (kept for compatibility)",
    )
    return p


def main() -> int:
    args = _build_argparser().parse_args()

    if not args.log_file and not args.job:
        _build_argparser().print_help()
        print("\n❌ Provide either --log-file or --job.")
        return 1

    dry_run: bool = args.dry_run
    job_name: str
    build_number: int
    log: str

    start = time.time()

    # ── Phase 1: Fetch / load build log ──────────────────────────────────────

    if args.log_file:
        print("📄 Phase 1: Reading log from file")
        log_path = Path(args.log_file)
        if not log_path.exists():
            print(f"   ❌ Log file not found: {args.log_file}")
            return 1
        log = log_path.read_text(encoding="utf-8")
        stem = log_path.stem  # e.g. "failing-syntax-build-2"
        parts = stem.rsplit("-build-", 1)
        if len(parts) == 2:
            job_name = parts[0]
            build_number = int(parts[1])
        else:
            job_name = args.job or "unknown"
            build_number = 0
        print(f"   ✅ Log loaded: {len(log):,} chars  "
              f"(job='{job_name}', build=#{build_number})")
    else:
        job_name = args.job
        build_number = args.build  # may still be None here
        print("📡 Phase 1: Fetching build log from Jenkins")
        try:
            jenkins = JenkinsClient()

            if build_number is None:
                build_number = jenkins.get_latest_build_number(job_name)
                print(f"   ℹ️  No build number given — using latest: #{build_number}")

            log = jenkins.get_build_log(job_name, build_number)
            print(f"   ✅ Log fetched: {len(log):,} chars from build #{build_number}")

        except JenkinsConnectionError as exc:
            print(f"\n   ❌ Cannot reach Jenkins: {exc}")
            print("      → Is the server running? Check JENKINS_URL in .env")
            return 1
        except JenkinsAuthError as exc:
            print(f"\n   ❌ Authentication failed: {exc}")
            return 1
        except JenkinsNotFoundError as exc:
            print(f"\n   ❌ Job or build not found: {exc}")
            print(f"      → Check job name '{job_name}' and build #{build_number}")
            return 1
        except JenkinsTimeoutError as exc:
            print(f"\n   ❌ Jenkins request timed out: {exc}")
            return 1
        except ValueError as exc:
            print(f"\n   ❌ {exc}")
            return 1

    repo: str = args.repo or f"pipeline-doctor-{job_name}"

    print()
    print("=" * 60)
    print("🩺 Pipeline Doctor — Autonomous Fix Workflow")
    print("=" * 60)
    print(f"   Job      : {job_name}#{build_number}")
    print(f"   Repo     : {repo}")
    print(f"   Mode     : {args.mode}{' (--dry-run)' if dry_run else ''}")
    print()

    # ── Phase 2 + 3: Preprocess & Diagnose (single LLM call) ─────────────────

    print("\n🔍 Phase 2: Preprocessing log")
    print("\n🩺 Phase 3: Generating diagnosis")

    try:
        diag_agent = DiagnosisAgent()
        diagnosis, stats = diag_agent.diagnose_with_stats(log)

        preprocessed = stats["preprocessed"]
        original_bytes = preprocessed["original_size"]
        compressed_bytes = preprocessed["compressed_size"]
        reduction_pct = (1 - compressed_bytes / original_bytes) * 100 if original_bytes else 0
        llm_time = stats["llm_time"]

        print(f"   ✅ Log compressed: {reduction_pct:.0f}% reduction "
              f"({original_bytes:,} → {compressed_bytes:,} bytes)")
        print(f"   ✅ Failed stage: {preprocessed.get('failed_stage', 'unknown')}")
        print()
        print(f"   ✅ Diagnosis complete ({llm_time:.1f}s)")
        print(f"      Error type : {diagnosis.error_type}")
        print(f"      File       : {diagnosis.affected_file}:{diagnosis.affected_line}")
        print(f"      Confidence : {diagnosis.confidence:.0%}")
        print(f"      Root cause : {diagnosis.root_cause}")
        print(f"      Fix hint   : {diagnosis.fix_suggestion}")

    except ValueError as exc:
        print(f"\n   ❌ Diagnosis failed: {exc}")
        return 1
    except Exception as exc:
        print(f"\n   ❌ Unexpected error during diagnosis: {exc}")
        return 1

    # Preview mode or --dry-run: stop after diagnosis
    if args.mode == "preview" or dry_run:
        elapsed = time.time() - start
        stat_mode = "dry-run" if dry_run else "preview"
        _record_stats(job_name, build_number, diagnosis, stat_mode, elapsed, success=True)
        print("\n" + "=" * 60)
        if args.mode == "preview":
            print("👀 Preview mode — no fix applied")
        else:
            print("🔍 Dry-run complete — no fix applied")
        print(f"   Job   : {job_name}#{build_number}")
        print(f"   Error : {diagnosis.error_type}")
        print(f"   Time  : {elapsed:.1f}s")
        print("=" * 60)
        return 0

    # Interactive mode: show plan and ask for confirmation
    if args.mode == "interactive":
        print("\n" + "=" * 60)
        print("🤔 Interactive Mode — Confirm Before Fix")
        print("=" * 60)
        print(f"\n📋 Planned actions for repo '{repo}':")
        print(f"   1. Read {diagnosis.affected_file} from GitHub")
        print(f"   2. Generate fix for: {diagnosis.error_type}")
        print(f"   3. Create branch: pipeline-doctor-fix-{repo}-<timestamp>")
        print(f"   4. Commit fix to that branch")
        print(f"   5. Open Pull Request for human review")
        print(f"\n   Confidence : {int(diagnosis.confidence * 100)}%")
        print(f"   Root cause : {diagnosis.root_cause}")
        print(f"\n   ⚠️  This will create a real Pull Request on GitHub.")

        answer = input("\n👉 Proceed with auto-fix? [y/N]: ").strip().lower()

        if answer not in ("y", "yes", "j", "ja"):
            _record_stats(
                job_name, build_number, diagnosis,
                "interactive-aborted", time.time() - start, success=False,
            )
            print("\n❌ Aborted by user. No changes made.")
            return 0

        print("\n✅ Confirmed. Proceeding with auto-fix...\n")

    # ── Phase 4: Auto-Fix via DeepAgent ───────────────────────────────────────

    print("\n🤖 Phase 4: Auto-Fix via DeepAgent")
    print(f"   Invoking agent for repo '{repo}' ...")

    try:
        auto_fix = create_auto_fix_agent()

        user_message = (
            f"There is a {diagnosis.error_type} in the repo '{repo}'.\n"
            f"The file '{diagnosis.affected_file}' has a bug on line "
            f"{diagnosis.affected_line}: {diagnosis.root_cause}\n\n"
            f"Diagnosis details:\n"
            f"- Error type: {diagnosis.error_type}\n"
            f"- Root cause: {diagnosis.root_cause}\n"
            f"- Evidence: {diagnosis.root_cause_evidence}\n"
            f"- Fix hint: {diagnosis.fix_suggestion}\n"
            f"- Confidence: {diagnosis.confidence:.0%}\n\n"
            f"Please:\n"
            f"1. Read the file '{diagnosis.affected_file}' from the repo\n"
            f"2. Generate a fix\n"
            f"3. Create a new branch (include timestamp {int(time.time())} in the name)\n"
            f"4. Commit the fix to the branch\n"
            f"5. Open a pull request with the diagnosis in the body\n\n"
            f"Report each step as you complete it."
        )

        result = auto_fix.invoke({
            "messages": [{"role": "user", "content": user_message}]
        })

        messages = result.get("messages", [])
        if messages:
            last = messages[-1]
            content = last.content if hasattr(last, "content") else str(last)
            print(f"\n   ✅ Agent Response:\n{content}")

        print(f"\n   📊 Agent steps: {len(messages)}")

    except Exception as exc:
        print(f"\n   ❌ Auto-fix agent failed: {exc}")
        traceback.print_exc()
        return 1

    # ── Phase 5: Summary ──────────────────────────────────────────────────────

    elapsed = time.time() - start
    _record_stats(job_name, build_number, diagnosis, args.mode, elapsed, success=True)

    print("\n" + "=" * 60)
    print("🎉 Pipeline Doctor Complete!")
    print(f"   Job   : {job_name}#{build_number}")
    print(f"   Error : {diagnosis.error_type}")
    print(f"   Repo  : {repo}")
    print(f"   Mode  : {args.mode}")
    print(f"   Time  : {elapsed:.1f}s")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
