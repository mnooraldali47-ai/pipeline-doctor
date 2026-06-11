"""Sprint-2 end-to-end analysis: Jenkins → preprocess → LLM → Markdown report.

Run:
    python scripts/analyze_failures.py
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

from pipeline_doctor.agent.diagnosis_agent import DiagnosisAgent
from pipeline_doctor.agent.diagnosis_schema import Diagnosis
from pipeline_doctor.tools.jenkins_client import (
    JenkinsAuthError,
    JenkinsClient,
    JenkinsConnectionError,
    JenkinsError,
)

PROJECT_ROOT = Path(__file__).parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
REPORTS_DIR = PROJECT_ROOT / "reports"

_ERROR_TYPE_LABELS: dict[str, str] = {
    "dependency_not_found": "Dependency Error",
    "test_failure": "Test Failure",
    "syntax_error": "Syntax Error",
    "build_error": "Build Error",
    "unknown": "Unknown",
}


# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class FetchedLog:
    """A FAILURE build log saved to disk.

    Attributes:
        path: Absolute path to the saved .log file.
        job: Jenkins job name.
        build_nr: Build number.
    """

    path: Path
    job: str
    build_nr: int


@dataclass
class AnalysisResult:
    """Outcome of preprocessing + LLM diagnosis for one log.

    Attributes:
        filename: Log filename (basename only).
        job: Jenkins job name.
        build_nr: Build number.
        original_size: Raw log size in bytes.
        compressed_size: Filtered log size in bytes.
        compression_ratio: compressed / original.
        diagnosis: Parsed Diagnosis, or None on failure.
        error: Human-readable error message if diagnosis failed.
        llm_time: LLM call duration in seconds.
        tokens: Total tokens consumed (0 if not reported).
    """

    filename: str
    job: str
    build_nr: int
    original_size: int = 0
    compressed_size: int = 0
    compression_ratio: float = 0.0
    diagnosis: Optional[Diagnosis] = None
    error: Optional[str] = None
    llm_time: float = 0.0
    tokens: int = 0

    @property
    def success(self) -> bool:
        return self.diagnosis is not None


# ── Phase functions ───────────────────────────────────────────────────────────


def connect_jenkins() -> tuple[JenkinsClient, str, list[str]]:
    """Create a Jenkins connection and verify reachability.

    Returns:
        Tuple of (client, jenkins_version, sorted_job_names).

    Raises:
        SystemExit: On auth failure, connection error, or missing JENKINS_URL.
    """
    print("📡 Phase 1: Verbinde mit Jenkins ...")
    client = JenkinsClient()
    if not client.url:
        print("   ❌ JENKINS_URL nicht gesetzt — .env prüfen.")
        sys.exit(1)

    try:
        info = client.get_info()
        version = info.get("_jenkins_version", "?")
        jobs = client.list_jobs()
    except JenkinsAuthError as e:
        print(f"   ❌ Auth-Fehler: {e}")
        sys.exit(1)
    except JenkinsConnectionError as e:
        print(f"   ❌ Verbindungsfehler: {e}")
        print("      → Läuft Jenkins? cd jenkins && docker compose up -d")
        sys.exit(1)
    except JenkinsError as e:
        print(f"   ❌ Jenkins-Fehler: {e}")
        sys.exit(1)

    print(f"   ✅ Verbunden (Version {version})")
    print(f"   📋 Jobs: {', '.join(jobs)}")
    return client, version, jobs


def fetch_logs(client: JenkinsClient, jobs: list[str]) -> list[FetchedLog]:
    """Fetch FAILURE build logs from Jenkins and save them to logs/.

    Skips jobs whose latest build is not FAILURE.
    Skips jobs on any Jenkins API error (prints warning, continues).

    Args:
        client: Authenticated JenkinsClient.
        jobs: List of job names to inspect.

    Returns:
        List of FetchedLog entries for every saved FAILURE log.
    """
    print("\n📥 Phase 2: Hole Fehler-Logs ...")
    LOGS_DIR.mkdir(exist_ok=True)

    fetched: list[FetchedLog] = []

    for job in jobs:
        try:
            build_nr = client.get_latest_build_number(job)
        except ValueError:
            print(f"   ⚠️  {job}: noch kein Build — übersprungen.")
            continue
        except JenkinsError as e:
            print(f"   ⚠️  {job}: Build-Nummer nicht abrufbar ({e}) — übersprungen.")
            continue

        try:
            if not client.is_build_failed(job, build_nr):
                result_str = client.get_build_info(job, build_nr).get("result", "?")
                print(f"   ⏭️  {job} Build #{build_nr}: {result_str} — übersprungen.")
                continue
        except JenkinsError as e:
            print(f"   ⚠️  {job}: Build-Status nicht abrufbar ({e}) — übersprungen.")
            continue

        try:
            log_text = client.get_build_log(job, build_nr)
        except JenkinsError as e:
            print(f"   ⚠️  {job}: Log nicht abrufbar ({e}) — übersprungen.")
            continue

        log_path = LOGS_DIR / f"{job}-build-{build_nr}.log"
        log_path.write_text(log_text, encoding="utf-8")
        fetched.append(FetchedLog(path=log_path, job=job, build_nr=build_nr))

    if fetched:
        print(f"   ✅ {len(fetched)} log(s) in logs/")
    else:
        print("   ⚠️  Keine fehlgeschlagenen Builds gefunden.")

    return fetched


def analyze_log(
    fetched: FetchedLog,
    agent: DiagnosisAgent,
    index: int,
    total: int,
) -> AnalysisResult:
    """Preprocess and diagnose a single build log.

    On any error (file unreadable, LLM failure, parse error) the error
    is captured in AnalysisResult.error and the function returns normally
    — it never raises.

    Args:
        fetched: FetchedLog to analyze.
        agent: Initialized DiagnosisAgent.
        index: 1-based position for console output.
        total: Total log count for console output.

    Returns:
        AnalysisResult with diagnosis or error information.
    """
    result = AnalysisResult(
        filename=fetched.path.name,
        job=fetched.job,
        build_nr=fetched.build_nr,
    )

    print(f"\n   [{index}/{total}] {fetched.path.name}")

    try:
        raw_log = fetched.path.read_text(encoding="utf-8")
    except OSError as e:
        result.error = f"Datei nicht lesbar: {e}"
        print(f"       ❌ {result.error}")
        return result

    try:
        diagnosis, stats = agent.diagnose_with_stats(raw_log)
    except Exception as e:
        first_line = str(e).splitlines()[0]
        result.error = first_line
        print(f"       ❌ LLM-Fehler: {first_line}")
        return result

    preprocessed = stats["preprocessed"]
    result.original_size = preprocessed["original_size"]
    result.compressed_size = preprocessed["compressed_size"]
    result.compression_ratio = preprocessed["compression_ratio"]
    result.diagnosis = diagnosis
    result.llm_time = stats["llm_time"]
    result.tokens = stats["tokens"]

    saved_pct = (1 - result.compression_ratio) * 100
    label = _ERROR_TYPE_LABELS.get(diagnosis.error_type, diagnosis.error_type)
    tokens_str = str(result.tokens) if result.tokens else "?"

    print(
        f"       ⚙️  Aufbereitung: {result.original_size} → "
        f"{result.compressed_size} Bytes ({saved_pct:.0f}% gespart)"
    )
    print(
        f"       🤖 LLM: {label} "
        f"(conf={diagnosis.confidence:.2f}, {result.llm_time:.1f}s, {tokens_str} tokens)"
    )

    return result


def write_report(
    results: list[AnalysisResult],
    model: str,
    wall_time: float,
) -> Path:
    """Write a Markdown diagnosis report to reports/sprint2-diagnoses.md.

    Args:
        results: Ordered list of AnalysisResult objects.
        model: GWDG model name (from GWDG_MODEL env var).
        wall_time: Total wall-clock duration in seconds.

    Returns:
        Absolute path to the written report file.
    """
    print("\n📝 Phase 4: Schreibe Report ...")
    REPORTS_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    successful = [r for r in results if r.success]
    failed_results = [r for r in results if not r.success]
    total_tokens = sum(r.tokens for r in results)
    total_llm_time = sum(r.llm_time for r in results)

    lines: list[str] = [
        "# Pipeline Doctor — Diagnose-Report",
        f"Erstellt: {timestamp}  ",
        f"Modell: `{model}`  ",
        "",
        "## Zusammenfassung",
        f"- Analysierte Logs: {len(results)}",
        f"- Erfolgreiche Diagnosen: {len(successful)}",
        f"- Fehlgeschlagene Diagnosen: {len(failed_results)}",
        f"- Tokens verbraucht: {total_tokens}",
        f"- LLM-Zeit gesamt: {total_llm_time:.1f}s",
        f"- Gesamtzeit: {wall_time:.1f}s",
        "",
        "## Diagnosen",
        "",
    ]

    for i, res in enumerate(results, start=1):
        lines.append(f"### {i}. {res.filename}")
        lines.append("")

        if res.success:
            d = res.diagnosis
            kept_pct = res.compression_ratio * 100
            lines += [
                "| Feld | Wert |",
                "|------|------|",
                f"| Fehlertyp | {_md(d.error_type)} |",
                f"| Fehlgeschlagene Stage | {_md(d.failed_stage or '—')} |",
                f"| Ursache | {_md(d.root_cause)} |",
                f"| Beleg | `{_md(d.root_cause_evidence)}` |",
                f"| Fix-Vorschlag | {_md(d.fix_suggestion)} |",
                f"| Konfidenz | {d.confidence:.2f} |",
                f"| Betroffene Datei | {_md(d.affected_file or '—')} |",
                f"| Betroffene Zeile | {d.affected_line if d.affected_line is not None else '—'} |",
                "",
                f"**Original-Größe:** {res.original_size} Bytes  ",
                f"**Komprimierte Größe:** {res.compressed_size} Bytes ({kept_pct:.0f}% behalten)  ",
                f"**LLM-Zeit:** {res.llm_time:.1f}s  ",
                f"**Tokens:** {res.tokens or '?'}",
            ]
        else:
            lines += [
                "| Feld | Wert |",
                "|------|------|",
                "| Status | ❌ Fehlgeschlagen |",
                f"| Fehler | {_md(res.error or 'Unbekannter Fehler')} |",
                "",
                f"**LLM-Zeit:** {res.llm_time:.1f}s  ",
                f"**Tokens:** {res.tokens or '—'}",
            ]

        lines.append("")

    report_path = REPORTS_DIR / "sprint2-diagnoses.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"   ✅ {report_path.relative_to(PROJECT_ROOT)}")
    return report_path


def _md(text: str) -> str:
    """Escape pipe characters for Markdown table cells."""
    return str(text).replace("|", "\\|")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    """Orchestrate the full Pipeline Doctor analysis pipeline."""
    wall_start = time.perf_counter()
    model = os.environ.get("GWDG_MODEL", "unknown")

    print("🚀 Pipeline Doctor — End-to-End Analyse\n")

    # Phase 1
    client, _version, jobs = connect_jenkins()

    # Phase 2
    fetched_logs = fetch_logs(client, jobs)
    if not fetched_logs:
        print("\n⚠️  Keine Failure-Logs — nichts zu analysieren.")
        sys.exit(0)

    # Phase 3
    print(f"\n🔍 Phase 3: Analysiere jeden Fehler")
    agent = DiagnosisAgent()
    results: list[AnalysisResult] = []
    for i, fetched in enumerate(fetched_logs, start=1):
        results.append(analyze_log(fetched, agent, i, len(fetched_logs)))

    # Phase 4
    wall_time = time.perf_counter() - wall_start
    write_report(results, model, wall_time)

    # Summary
    total_tokens = sum(r.tokens for r in results)
    total_llm_time = sum(r.llm_time for r in results)
    successful = sum(1 for r in results if r.success)

    print("\n📊 Zusammenfassung:")
    print(f"   Analysierte Logs:  {len(results)}")
    print(f"   Erfolgreich:       {successful}/{len(results)}")
    print(f"   Tokens verbraucht: {total_tokens}")
    print(f"   LLM-Zeit:          {total_llm_time:.1f}s")
    print(f"   Gesamtzeit:        {wall_time:.1f}s")
    print("\n✅ Fertig.")


if __name__ == "__main__":
    main()
