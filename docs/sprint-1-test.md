# Sprint 1 — Manueller Test

Schritt-für-Schritt-Anleitung zum vollständigen Test von Sprint 1.  
Ziel: 3 Jenkins-Jobs anlegen, alle fehlschlagen lassen, Logs automatisch abrufen.

---

## Voraussetzungen

- Docker Desktop läuft
- PowerShell im Projekt-Root: `C:\Users\aldali\Documents\Agentic ai\pipeline-doctor`
- `.env` befüllt (kopiere `.env.example` und trage Credentials ein)
- venv aktiviert: `.venv\Scripts\Activate.ps1`

---

## Schritt 1 — Jenkins starten

```powershell
cd jenkins
docker compose up -d
```

Status prüfen (warten bis Jenkins bereit):

```powershell
docker compose logs -f
# Warten bis: "Jenkins is fully up and running"
# Ctrl+C um Logs zu beenden
```

Browser öffnen: **http://localhost:8080**

Falls erster Start → Initial-Admin-Passwort holen:

```powershell
docker exec pipeline-doctor-jenkins cat /var/jenkins_home/secrets/initialAdminPassword
```

Login → "Install suggested plugins" → Admin-User anlegen → API-Token erstellen und in `.env` eintragen.

Zurück ins Projekt-Root:

```powershell
cd ..
```

---

## Schritt 2 — Jenkins-Verbindung testen

```powershell
python scripts/test_jenkins_connection.py
```

**Erwartete Ausgabe:**

```
🔌 Verbinde mit: http://localhost:8080
   Benutzer: admin

✅ Verbindung erfolgreich!
   Jenkins-Version : 2.x.x

📋 Jobs (0 gefunden):
   (noch keine Jobs — Jenkins ist leer)

✅ Verbindungstest erfolgreich abgeschlossen.
```

Falls `❌ Authentifizierungsfehler` → API-Token in `.env` prüfen.  
Falls `❌ Verbindungsfehler` → `docker compose ps` in `jenkins/` prüfen.

---

## Schritt 3 — 3 Pipeline-Jobs in Jenkins anlegen

Für **jeden** der drei Jobs folgende Schritte wiederholen.

### Browser: http://localhost:8080

**Job 1: `failing-dependency`**

1. "New Item" klicken
2. Name: `failing-dependency`
3. Typ: **Pipeline** → OK
4. Scroll zu **Pipeline** (ganz unten)
5. Definition: `Pipeline script from SCM`
6. SCM: `Git`
7. Repository URL:
   ```
   file:///C:/Users/aldali/Documents/Agentic%20ai/pipeline-doctor/test-repos/failing-dependency
   ```
8. Branch Specifier: `*/master`
9. Script Path: `Jenkinsfile`
10. **Save**

**Job 2: `failing-tests`**

Gleiche Schritte, Repository URL:
```
file:///C:/Users/aldali/Documents/Agentic%20ai/pipeline-doctor/test-repos/failing-tests
```

**Job 3: `failing-syntax`**

Gleiche Schritte, Repository URL:
```
file:///C:/Users/aldali/Documents/Agentic%20ai/pipeline-doctor/test-repos/failing-syntax
```

---

## Schritt 4 — Alle 3 Jobs bauen (sollten fehlschlagen)

Für jeden Job im Jenkins-UI:

1. Job anklicken
2. **"Build Now"** klicken
3. Unter "Build History" erscheint `#1`
4. Auf `#1` klicken → **"Console Output"** — Fehler sichtbar

### Erwartete Fehler

| Job | Fehlschlägt in Stage | Fehlermeldung |
|-----|---------------------|---------------|
| `failing-dependency` | Install Dependencies | `ERROR: No matching distribution found for this-package-does-not-exist-12345==1.0` |
| `failing-tests` | Test | `FAILED test_main.py::test_add_intentionally_wrong` / `assert 2 == 3` |
| `failing-syntax` | Syntax Check | `SyntaxError: expected ':'` |

Alle 3 zeigen nach dem Build ein **rotes Kugel-Symbol** (●) in der Build-Liste.

---

## Schritt 5 — Logs automatisch abrufen

```powershell
python scripts/fetch_failure_logs.py
```

**Erwartete Ausgabe:**

```
🔌 Jenkins: http://localhost:8080
📋 3 Job(s) gefunden: failing-dependency, failing-syntax, failing-tests

📥 Prüfe Job 'failing-dependency' ...
   💾 Build #1 (FAILURE) — 3,241 bytes → logs\failing-dependency-build-1.log

📥 Prüfe Job 'failing-syntax' ...
   💾 Build #1 (FAILURE) — 1,876 bytes → logs\failing-syntax-build-1.log

📥 Prüfe Job 'failing-tests' ...
   💾 Build #1 (FAILURE) — 4,102 bytes → logs\failing-tests-build-1.log

────────────────────────────────────────────────────────────
📋 Zusammenfassung
   Gespeicherte Logs : 3
     ✅ logs\failing-dependency-build-1.log
     ✅ logs\failing-syntax-build-1.log
     ✅ logs\failing-tests-build-1.log

✅ Fertig — 3 Log(s) in logs/ gespeichert.
```

---

## Schritt 6 — Logs prüfen

```powershell
ls logs/
```

Ausgabe:
```
.gitkeep
failing-dependency-build-1.log
failing-syntax-build-1.log
failing-tests-build-1.log
```

Log-Inhalt ansehen:

```powershell
# Dependency-Fehler
cat logs\failing-dependency-build-1.log | Select-String "ERROR"

# Test-Fehler
cat logs\failing-tests-build-1.log | Select-String "FAILED"

# Syntax-Fehler
cat logs\failing-syntax-build-1.log | Select-String "SyntaxError"
```

**Erwartete Treffer:**

```
# failing-dependency
ERROR: No matching distribution found for this-package-does-not-exist-12345==1.0

# failing-tests
FAILED test_main.py::test_add_intentionally_wrong - AssertionError: assert 2 == 3
FAILED test_main.py::test_multiply_intentionally_wrong - AssertionError: assert 10 == 99

# failing-syntax
SyntaxError: expected ':'
```

---

## Schritt 7 — Unit-Tests bestätigen

```powershell
pytest tests/ -v
```

**Erwartete Ausgabe:** 17 Tests, alle grün (`passed`), kein echter Jenkins nötig.

---

## Checkliste Sprint 1

- [ ] Jenkins läuft auf http://localhost:8080
- [ ] Verbindungstest zeigt Version + Jobs
- [ ] 3 Jobs angelegt, alle fehlgeschlagen (rote Kugeln)
- [ ] `fetch_failure_logs.py` speichert 3 Log-Dateien
- [ ] Log-Inhalte enthalten den erwarteten Fehlertext
- [ ] 17 Unit-Tests grün

✅ Sprint 1 vollständig demonstriert.
