# Pipeline Doctor

> KI-Agent zur automatischen Diagnose fehlgeschlagener Jenkins-Builds.

## Sprint-Status

| Sprint | Inhalt | Status |
|--------|--------|--------|
| Sprint 1 | Jenkins-Integration + Log-Abruf | ✅ Abgeschlossen |
| Sprint 2 | LLM-Diagnose (GWDG/KISSKI API) | 🔜 Geplant |
| Sprint 3 | Agentic Loop (DeepAgents) | 🔜 Geplant |

## Was funktioniert (Sprint 1)

- Jenkins-Verbindung via REST API (`pipeline_doctor/tools/jenkins_client.py`)
- Alle Jobs auflisten, Build-Status prüfen
- Build-Logs automatisch abrufen und lokal speichern
- 3 reproduzierbare Fehler-Szenarien in `test-repos/`:
  - `failing-dependency` — pip install schlägt fehl (Paket nicht gefunden)
  - `failing-tests` — pytest AssertionError (absichtlich falsche Tests)
  - `failing-syntax` — SyntaxError in Python-Datei
- 17 Unit-Tests für JenkinsClient (alle HTTP-Calls gemockt)

## Überblick

Pipeline Doctor analysiert fehlgeschlagene CI/CD-Builds vollautomatisch:
1. Verbindet sich mit Jenkins und lädt Build-Logs
2. Ruft zugehörige Git-Commits und Diffs ab
3. Analysiert Fehler mit einem LLM (GWDG/KISSKI API)
4. Gibt strukturierte Diagnose + Lösungsvorschläge aus

## Tech-Stack

| Komponente | Technologie |
|-----------|-------------|
| CI/CD-Integration | requests (REST API) |
| Git-Integration | PyGithub |
| LLM-Backend | GWDG/KISSKI API (OpenAI-kompatibel) |
| Agent-Framework | DeepAgents |
| Sprache | Python 3.13 (Debian Trixie) |

## Quick-Start

```powershell
# 1. Jenkins starten
cd jenkins
docker compose up -d
cd ..

# 2. venv aktivieren + Pakete installieren
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 3. .env befüllen
cp .env.example .env
# JENKINS_URL, JENKINS_USER, JENKINS_TOKEN eintragen

# 4. Verbindung testen
python scripts/test_jenkins_connection.py

# 5. Alle fehlgeschlagenen Build-Logs abrufen
python scripts/fetch_failure_logs.py
# → Logs landen in logs/

# 6. Unit-Tests laufen lassen
pytest tests/ -v
```

## Projektstruktur

```
pipeline-doctor/
  pipeline_doctor/
    tools/          # JenkinsClient, weitere Tools (Sprint 2+)
    agent/          # DeepAgents-Agentlogik (Sprint 3)
    prompts/        # LLM-Prompts (Sprint 2)
  scripts/
    test_jenkins_connection.py   # Verbindungstest
    fetch_failure_logs.py        # Log-Abruf (Sprint 1)
  tests/                         # pytest Unit-Tests
  test-repos/                    # 3 Fehler-Szenarien für Jenkins
  jenkins/                       # Docker-Setup für lokalen Jenkins
  logs/                          # Abgerufene Build-Logs (nicht versioniert)
  docs/                          # Dokumentation + Demo-Anleitungen
```

## Konfiguration

Alle Einstellungen via `.env` (siehe `.env.example`):

| Variable | Beschreibung |
|----------|-------------|
| `JENKINS_URL` | Jenkins-Server-URL (z.B. `http://localhost:8080`) |
| `JENKINS_USER` | Jenkins-Benutzername |
| `JENKINS_TOKEN` | Jenkins API-Token |
| `GITHUB_TOKEN` | GitHub Personal Access Token |
| `GWDG_API_KEY` | GWDG/KISSKI LLM API-Schlüssel |

## Hochschul-Kontext

Projekt im Rahmen des Moduls **Agentic AI**
