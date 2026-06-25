# Pipeline Doctor

> KI-Agent zur automatischen Diagnose fehlgeschlagener Jenkins-Builds.

## Sprint-Status

| Sprint | Inhalt | Status |
|--------|--------|--------|
| Sprint 1 | Jenkins-Integration + Log-Abruf | ✅ Abgeschlossen |
| Sprint 2 | LLM-Diagnose (GWDG/KISSKI API) | ✅ Abgeschlossen |
| Sprint 3 | Automatischer Fix nach Bestätigung | ✅ Abgeschlossen |

## Was funktioniert (Sprint 1)

- Jenkins-Verbindung via REST API (`pipeline_doctor/tools/jenkins_client.py`)
- Alle Jobs auflisten, Build-Status prüfen
- Build-Logs automatisch abrufen und lokal speichern
- 3 reproduzierbare Fehler-Szenarien in `test-repos/`:
  - `failing-dependency` — pip install schlägt fehl (Paket nicht gefunden)
  - `failing-tests` — pytest AssertionError (absichtlich falsche Tests)
  - `failing-syntax` — SyntaxError in Python-Datei
- 17 Unit-Tests für JenkinsClient (alle HTTP-Calls gemockt)

## Was funktioniert (Sprint 2)

- Log-Preprocessing: reduziert Logs auf relevante Zeilen vor dem LLM-Call
- LLM-Diagnose via GWDG/KISSKI API → strukturiertes `Diagnosis`-Objekt
- Felder: `error_type`, `root_cause`, `root_cause_evidence`, `fix_suggestion`, `confidence`
- Markdown-Report in `reports/sprint2-diagnoses.md`

## Was funktioniert (Sprint 3)

- `AutoFixAgent` plant Fix aus Diagnose → `FixPlan`-Objekt
- Interaktive Bestätigung: `"Möchtest du diesen Fix anwenden? [y/N]"`
- **Automatisch anwendbar:** `syntax_error` — fehlender Doppelpunkt in Funktionsdefinition
- **Bewusst nicht automatisch:** `dependency_not_found`, `test_failure` (zu ambivalent)
- Nach Bestätigung: Datei in `test-repos/` wird geändert + `git diff` wird angezeigt
- Kein Push, kein Pull Request, keine Änderungen außerhalb von `test-repos/`

## Überblick

Pipeline Doctor analysiert fehlgeschlagene CI/CD-Builds und schlägt Fixes vor:
1. Verbindet sich mit Jenkins und lädt Build-Logs
2. Analysiert Fehler mit einem LLM (GWDG/KISSKI API)
3. Gibt strukturierte Diagnose + Lösungsvorschläge aus
4. Bietet nach Bestätigung automatischen Fix im lokalen Repo an

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

# 6. LLM-Diagnose für alle Jobs
python scripts/analyze_failures.py
# → Report in reports/sprint2-diagnoses.md

# 7. Sprint 3: Diagnose + bestätigter Auto-Fix
python scripts/apply_suggested_fix.py --job failing-syntax
# → Zeigt Diagnose, fragt [y/N], fixt bei Bestätigung

# 8. Unit-Tests laufen lassen
pytest tests/ -v
```

> **Hinweis Sprint 3:** Aktuell wird nur `syntax_error` (fehlender Doppelpunkt in
> Funktionsdefinitionen) automatisch gefixt. `dependency_not_found` und `test_failure`
> werden erklärt, aber nicht automatisch angewendet.

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
    analyze_failures.py          # LLM-Diagnose + Report (Sprint 2)
    apply_suggested_fix.py       # Diagnose + bestätigter Auto-Fix (Sprint 3)
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
