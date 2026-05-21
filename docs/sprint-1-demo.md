# Sprint-1-Demo — Live-Anleitung

**Datum:** 29. Mai 2026  
**Ziel:** Zeigen, dass Pipeline Doctor automatisch fehlgeschlagene Jenkins-Builds erkennt und Logs abruft.

---

## Vorbereitung (vor der Demo — nicht live)

```powershell
# 1. Jenkins-Container läuft?
docker ps | grep pipeline-doctor-jenkins

# Falls nicht:
cd "C:\Users\aldali\Documents\Agentic ai\pipeline-doctor\jenkins"
docker compose up -d

# 2. .env vorhanden und befüllt?
# JENKINS_URL, JENKINS_USER, JENKINS_TOKEN müssen gesetzt sein

# 3. venv aktiv?
.venv\Scripts\Activate.ps1
```

**Sicherstellen:** Alle 3 Jenkins-Jobs haben mindestens 1 fehlgeschlagenen Build.  
Browser-Check: http://localhost:8080 → 3 rote Kugeln sichtbar.

---

## Live-Demo-Ablauf

### Schritt 1 — Verbindungstest zeigen (30 Sek.)

```powershell
python scripts/test_jenkins_connection.py
```

**Erwartete Ausgabe:**
```
🔌 Verbinde mit: http://localhost:8080
   Benutzer: <dein-name>

✅ Verbindung erfolgreich!
   Jenkins-Version : 2.x.x
   
📋 Jobs (3 gefunden):
   • failing-dependency
   • failing-syntax
   • failing-tests

✅ Verbindungstest erfolgreich abgeschlossen.
```

**Sagen:** *"Der Agent verbindet sich mit Jenkins über die REST API und listet alle Jobs auf."*

---

### Schritt 2 — Jenkins-UI kurz zeigen (1 Min.)

Browser: http://localhost:8080

- Auf `failing-dependency` klicken → rote Build-Historie zeigen
- Console Output öffnen → langen rohen Log zeigen
- Zurück zur Übersicht

**Sagen:** *"Das ist das Problem: Entwickler müssen manuell in Jenkins gehen, den richtigen Build finden, und sich durch diesen Log durchkämpfen. Pipeline Doctor automatisiert genau das."*

---

### Schritt 3 — Logs automatisch abrufen (1 Min.)

```powershell
python scripts/fetch_failure_logs.py
```

**Erwartete Ausgabe:**
```
🔌 Jenkins: http://localhost:8080
📋 3 Job(s) gefunden: failing-dependency, failing-syntax, failing-tests

📥 Prüfe Job 'failing-dependency' ...
   💾 Build #X (FAILURE) — X,XXX bytes → logs/failing-dependency-build-X.log

📥 Prüfe Job 'failing-syntax' ...
   💾 Build #X (FAILURE) — X,XXX bytes → logs/failing-syntax-build-X.log

📥 Prüfe Job 'failing-tests' ...
   💾 Build #X (FAILURE) — X,XXX bytes → logs/failing-tests-build-X.log

────────────────────────────────────────────────────────────
📋 Zusammenfassung
   Gespeicherte Logs : 3
     ✅ logs/failing-dependency-build-X.log
     ✅ logs/failing-syntax-build-X.log
     ✅ logs/failing-tests-build-X.log

✅ Fertig — 3 Log(s) in logs/ gespeichert.
```

**Sagen:** *"Mit einem Befehl werden alle fehlgeschlagenen Builds erkannt und die Logs lokal gespeichert."*

---

### Schritt 4 — Gespeicherte Logs zeigen (30 Sek.)

```powershell
ls logs/
cat logs/failing-tests-build-X.log
```

**Sagen:** *"Diese Logs gehen in Sprint 2 direkt ans LLM. Der Agent liest sie, identifiziert die Fehlerursache, und gibt Lösungsvorschläge aus — vollautomatisch."*

---

### Schritt 5 — Code kurz zeigen (optional, 1 Min.)

`pipeline_doctor/tools/jenkins_client.py` → Klasse zeigen, auf `get_build_log()` hinweisen.

**Sagen:** *"Der Client ist modular aufgebaut. Alle Jenkins-Aufrufe laufen über typed Exceptions — wenn Jenkins nicht erreichbar ist, gibt es eine saubere Fehlermeldung statt einem Python-Traceback."*

---

## Zusammenfassung Sprint 1

| Was demonstriert | Status |
|-----------------|--------|
| Jenkins-Verbindung via REST API | ✅ |
| Automatische Job-Erkennung | ✅ |
| Fehlgeschlagene Builds identifizieren | ✅ |
| Build-Logs speichern | ✅ |
| 3 reproduzierbare Fehler-Szenarien | ✅ |

**Nächster Sprint:** LLM-Diagnose — die gespeicherten Logs werden automatisch analysiert.
