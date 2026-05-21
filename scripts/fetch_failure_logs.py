"""Fetch and save build logs for all failed Jenkins jobs."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from pipeline_doctor.tools.jenkins_client import (
    JenkinsAuthError,
    JenkinsClient,
    JenkinsConnectionError,
    JenkinsError,
    JenkinsNotFoundError,
)

LOGS_DIR = Path(__file__).parent.parent / "logs"


def main() -> None:
    LOGS_DIR.mkdir(exist_ok=True)

    client = JenkinsClient()
    if not client.url:
        print("❌ JENKINS_URL nicht gesetzt — .env prüfen.")
        sys.exit(1)

    print(f"🔌 Jenkins: {client.url}")

    # ── Jobs abrufen ──────────────────────────────────────────────────────────
    try:
        jobs = client.list_jobs()
    except JenkinsAuthError as exc:
        print(f"❌ Auth-Fehler: {exc}")
        sys.exit(1)
    except JenkinsConnectionError as exc:
        print(f"❌ Verbindungsfehler: {exc}")
        print("   → Läuft Jenkins? cd jenkins && docker compose up -d")
        sys.exit(1)
    except JenkinsError as exc:
        print(f"❌ Jenkins-Fehler: {exc}")
        sys.exit(1)

    print(f"📋 {len(jobs)} Job(s) gefunden: {', '.join(jobs)}\n")

    saved: list[str] = []
    skipped: list[str] = []

    # ── Pro Job: letzten Build prüfen + Log speichern ─────────────────────────
    for job in jobs:
        print(f"📥 Prüfe Job '{job}' ...")

        try:
            build_nr = client.get_latest_build_number(job)
        except ValueError:
            print(f"   ⚠️  Noch kein Build vorhanden — übersprungen.\n")
            skipped.append(f"{job} (kein Build)")
            continue
        except JenkinsNotFoundError:
            print(f"   ❌ Job nicht gefunden — übersprungen.\n")
            skipped.append(f"{job} (nicht gefunden)")
            continue
        except JenkinsError as exc:
            print(f"   ❌ Fehler beim Abrufen: {exc}\n")
            skipped.append(f"{job} (Fehler)")
            continue

        try:
            failed = client.is_build_failed(job, build_nr)
        except JenkinsError as exc:
            print(f"   ❌ Build-Status nicht abrufbar: {exc}\n")
            skipped.append(f"{job} (Status unbekannt)")
            continue

        if not failed:
            build_info = client.get_build_info(job, build_nr)
            result = build_info.get("result", "IN_PROGRESS")
            print(f"   ✅ Build #{build_nr} = {result} — kein Log nötig.\n")
            skipped.append(f"{job} Build #{build_nr} ({result})")
            continue

        # Build ist FAILURE → Log holen
        try:
            log = client.get_build_log(job, build_nr)
        except JenkinsError as exc:
            print(f"   ❌ Log nicht abrufbar: {exc}\n")
            skipped.append(f"{job} Build #{build_nr} (Log-Fehler)")
            continue

        log_file = LOGS_DIR / f"{job}-build-{build_nr}.log"
        log_file.write_text(log, encoding="utf-8")

        size = len(log.encode("utf-8"))
        rel = log_file.relative_to(Path(__file__).parent.parent)
        print(f"   💾 Build #{build_nr} (FAILURE) — {size:,} bytes → {rel}\n")
        saved.append(str(rel))

    # ── Zusammenfassung ───────────────────────────────────────────────────────
    print("─" * 60)
    print(f"📋 Zusammenfassung")
    print(f"   Gespeicherte Logs : {len(saved)}")
    for path in saved:
        print(f"     ✅ {path}")

    if skipped:
        print(f"   Übersprungen      : {len(skipped)}")
        for entry in skipped:
            print(f"     ⏭️  {entry}")

    if not saved:
        print("\n❌ Keine fehlgeschlagenen Builds gefunden.")
        sys.exit(1)

    print(f"\n✅ Fertig — {len(saved)} Log(s) in logs/ gespeichert.")


if __name__ == "__main__":
    main()
