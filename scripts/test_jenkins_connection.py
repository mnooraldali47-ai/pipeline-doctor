"""Smoke-test: verify Jenkins connectivity using JenkinsClient."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline_doctor.tools.jenkins_client import (
    JenkinsAuthError,
    JenkinsClient,
    JenkinsConnectionError,
    JenkinsError,
    JenkinsTimeoutError,
)


def main() -> None:
    client = JenkinsClient()

    if not client.url:
        print("❌ JENKINS_URL nicht gesetzt — .env prüfen (.env.example als Vorlage).")
        sys.exit(1)

    print(f"🔌 Verbinde mit: {client.url}")
    print(f"   Benutzer     : {client.user}")

    # ── Schritt 1: Server-Info ────────────────────────────────────────────────
    try:
        info = client.get_info()
    except JenkinsAuthError as exc:
        print(f"\n❌ Authentifizierungsfehler: {exc}")
        print("   → API-Token neu generieren:")
        print("     Jenkins → [Benutzername] → Configure → API Token → Add new Token")
        sys.exit(1)
    except JenkinsConnectionError as exc:
        print(f"\n❌ Verbindungsfehler: {exc}")
        print("   → Jenkins starten: cd jenkins && docker compose up -d")
        print("   → Browser-Check  : http://localhost:8080")
        sys.exit(1)
    except JenkinsTimeoutError as exc:
        print(f"\n❌ Timeout: {exc}")
        print("   → Netzwerk / Firewall prüfen")
        sys.exit(1)
    except JenkinsError as exc:
        print(f"\n❌ Unerwarteter Jenkins-Fehler: {exc}")
        sys.exit(1)

    version = info.get("_jenkins_version", "?")
    description = info.get("description") or "(keine)"
    print(f"\n✅ Verbindung erfolgreich!")
    print(f"   Jenkins-Version : {version}")
    print(f"   Beschreibung    : {description}")

    # ── Schritt 2: Jobs ───────────────────────────────────────────────────────
    try:
        jobs = client.list_jobs()
    except JenkinsError as exc:
        print(f"\n❌ Jobs konnten nicht abgerufen werden: {exc}")
        sys.exit(1)

    print(f"\n📋 Jobs ({len(jobs)} gefunden):")
    if not jobs:
        print("   (noch keine Jobs — Jenkins ist leer)")
    else:
        for name in jobs:
            print(f"   • {name}")

    print("\n✅ Verbindungstest erfolgreich abgeschlossen.")


if __name__ == "__main__":
    main()
