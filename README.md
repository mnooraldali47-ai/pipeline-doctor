# Pipeline Doctor

> KI-Agent zur automatischen Diagnose fehlgeschlagener Jenkins-Builds.

## Überblick

Pipeline Doctor analysiert fehlgeschlagene CI/CD-Builds vollautomatisch:
1. Verbindet sich mit Jenkins und lädt Build-Logs
2. Ruft zugehörige Git-Commits und Diffs ab
3. Analysiert Fehler mit einem LLM (GWDG/KISSKI API)
4. Gibt strukturierte Diagnose + Lösungsvorschläge aus

## Tech-Stack

| Komponente | Technologie |
|-----------|-------------|
| Agent-Framework | DeepAgents |
| CI/CD-Integration | python-jenkins |
| Git-Integration | PyGithub |
| LLM-Backend | GWDG/KISSKI API (OpenAI-kompatibel) |
| Sprache | Python 3.11+ |

## Schnellstart

```bash
# 1. Repository klonen
git clone <repo-url>
cd pipeline-doctor

# 2. Abhängigkeiten installieren
pip install -r requirements.txt

# 3. Konfiguration
cp .env.example .env
# .env mit eigenen Credentials befüllen

# 4. Agent starten
python -m agent.main
```

## Konfiguration

Alle Einstellungen via `.env` (siehe `.env.example`):

| Variable | Beschreibung |
|----------|-------------|
| `JENKINS_URL` | Jenkins-Server-URL |
| `JENKINS_USER` | Jenkins-Benutzername |
| `JENKINS_TOKEN` | Jenkins API-Token |
| `GITHUB_TOKEN` | GitHub Personal Access Token |
| `GWDG_API_KEY` | GWDG/KISSKI LLM API-Schlüssel |

## Projektstruktur

```
pipeline-doctor/
  agent/        # Agentenlogik (DeepAgents)
  tools/        # Jenkins-, Git-, Log-Analysetools
  prompts/      # LLM-Prompts
  tests/        # Tests
```

## Hochschul-Kontext

Projekt im Rahmen des Moduls **Agentic AI**, M-Nour Aldali.
