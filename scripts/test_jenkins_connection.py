"""Quick smoke-test: Jenkins-Verbindung prüfen."""

import sys
from pathlib import Path

# .env aus Projekt-Root laden
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import os
import jenkins


def main() -> None:
    url   = os.getenv("JENKINS_URL")
    user  = os.getenv("JENKINS_USER")
    token = os.getenv("JENKINS_TOKEN")

    missing = [k for k, v in {"JENKINS_URL": url, "JENKINS_USER": user, "JENKINS_TOKEN": token}.items() if not v]
    if missing:
        print(f"❌ Fehlende Umgebungsvariablen in .env: {', '.join(missing)}")
        print("   → .env.example als Vorlage nutzen und .env befüllen.")
        sys.exit(1)

    print(f"🔌 Verbinde mit Jenkins: {url}")
    print(f"   Benutzer: {user}")

    try:
        server = jenkins.Jenkins(url, username=user, password=token)
        version = server.get_version()
        print(f"\n✅ Verbindung erfolgreich!")
        print(f"   Jenkins-Version: {version}")
    except jenkins.JenkinsException as exc:
        print(f"\n❌ Jenkins-Fehler: {exc}")
        _print_tips(str(exc))
        sys.exit(1)
    except Exception as exc:
        print(f"\n❌ Unerwarteter Fehler: {exc}")
        _print_tips(str(exc))
        sys.exit(1)

    print("\n📋 Alle Jobs:")
    try:
        jobs = server.get_jobs()
        if not jobs:
            print("   (keine Jobs vorhanden — Jenkins ist leer)")
        else:
            for job in jobs:
                color = job.get("color", "?")
                status = _color_to_emoji(color)
                print(f"   {status} {job['name']}")
    except Exception as exc:
        print(f"❌ Jobs konnten nicht abgerufen werden: {exc}")
        sys.exit(1)

    print("\n✅ Verbindungstest abgeschlossen.")


def _color_to_emoji(color: str) -> str:
    mapping = {
        "blue":      "✅",
        "red":       "❌",
        "yellow":    "⚠️ ",
        "grey":      "⬜",
        "disabled":  "🔇",
        "aborted":   "⛔",
        "notbuilt":  "🔘",
    }
    base = color.replace("_anime", "")  # "_anime" = läuft gerade
    return mapping.get(base, "❓")


def _print_tips(error: str) -> None:
    error_lower = error.lower()
    print("\n💡 Mögliche Ursachen:")
    if "401" in error or "unauthorized" in error_lower:
        print("   • JENKINS_TOKEN falsch oder abgelaufen")
        print("   • Token neu generieren: Jenkins → Benutzer → Configure → API Token")
    elif "403" in error or "forbidden" in error_lower:
        print("   • Benutzer hat keine ausreichenden Rechte")
        print("   • Jenkins → Manage Jenkins → Security → Matrix-based security prüfen")
    elif "connection" in error_lower or "refused" in error_lower or "timeout" in error_lower:
        print("   • Jenkins läuft nicht oder URL falsch")
        print("   • Prüfen: docker compose ps   (in jenkins/)")
        print("   • Prüfen: http://localhost:8080 im Browser erreichbar?")
    elif "404" in error:
        print("   • JENKINS_URL falsch (z.B. Pfad-Suffix /jenkins fehlt oder zuviel)")
    else:
        print("   • .env prüfen: JENKINS_URL, JENKINS_USER, JENKINS_TOKEN")
        print("   • Jenkins-Container läuft? → docker compose ps")


if __name__ == "__main__":
    main()
