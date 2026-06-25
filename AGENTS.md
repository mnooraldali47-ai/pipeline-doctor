# Pipeline Doctor — AGENTS.md

## Projekt
KI-Agent zur automatischen Analyse fehlgeschlagener Jenkins-Builds.
Hochschul-Modul: Agentic AI.

## Tech-Stack
- Python 3.11+
- DeepAgents (Agentic-AI-Framework)
- Jenkins (via python-jenkins API)
- Git / GitHub (via PyGithub)
- GWDG/KISSKI LLM API (OpenAI-kompatibler Endpunkt)
- python-dotenv, requests

## Architektur
```
pipeline-doctor/
  agent/          # DeepAgents-Agentlogik
  tools/          # Jenkins-, Git-, Log-Tools
  prompts/        # System- und Analyse-Prompts
  tests/          # Unit- und Integrationstests
  .env.example    # Konfigurationsvorlage
  requirements.txt
```

## Konventionen
- Alle Umgebungsvariablen aus `.env` laden (python-dotenv)
- LLM-Aufrufe immer über `agent/llm_client.py` (GWDG/KISSKI-Endpunkt)
- Keine Secrets in Code oder Git

## Wichtige Befehle
```bash
pip install -r requirements.txt
cp .env.example .env   # dann .env befüllen
python -m agent.main   # Agent starten
pytest tests/
```
