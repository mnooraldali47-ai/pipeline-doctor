# Sprint 3 — Automatischer Fix nach Bestätigung

## Ziel

Nach der Diagnose eines fehlgeschlagenen Jenkins-Builds (Sprint 2) geht Sprint 3 einen Schritt weiter:
Der Agent schlägt einen konkreten Fix vor und wendet ihn **nach expliziter Nutzerbestätigung** direkt im lokalen Test-Repo an.

Sicherheit hat Vorrang vor Automatisierung: Kein Fix ohne `[y/N]`-Bestätigung.

---

## Was automatisch gefixt wird

### `syntax_error` — fehlender Doppelpunkt in Funktionsdefinition

**Erkennungsmuster:** Zeilen der Form `def foo(x, y)` (ohne abschließenden `:`)

**Angewendeter Fix:** Doppelpunkt wird ans Ende der Zeile angefügt.

**Beispiel:**

```python
# vorher (fehlerhaft)
def multiply(x, y)
    return x * y

# nachher (korrigiert)
def multiply(x, y):
    return x * y
```

**Warum sicher?** Der Fix ist deterministisch: Regex erkennt das Muster eindeutig,
keine Interpretation nötig, kein semantischer Eingriff in die Logik.

---

## Was bewusst NICHT automatisch gefixt wird

### `dependency_not_found` — fehlendes Paket in requirements.txt

**Warum nicht?** Blindes Löschen eines Pakets kann Folgefehler erzeugen.
Es ist unklar, ob das Paket falsch geschrieben, veraltet oder durch ein anderes zu ersetzen ist.

**Was der Agent zeigt:**
- Mögliche Ursachen (Tippfehler, veraltetes Paket)
- Handlungsoptionen (prüfen, ersetzen, entfernen)

**Entscheidung:** Manuell.

---

### `test_failure` — fehlschlagende Assertion

**Warum nicht?** Eine falsche Assertion kann bedeuten:
- A) Der **Test** ist falsch (falsche Erwartung)
- B) Die **Implementierung** ist falsch (falsche Logik)

Keiner der beiden Fälle kann automatisch entschieden werden.

**Was der Agent zeigt:**
- Welche Assertion fehlschlägt
- Beide Handlungsoptionen

**Entscheidung:** Manuell.

---

## Ablauf mit Bestätigung

```
Pipeline Doctor fragt immer: "Möchtest du diesen Fix anwenden? [y/N]"

safe_to_apply=True  + Nutzer sagt "y" → Fix wird angewendet
safe_to_apply=True  + Nutzer sagt "n" → keine Änderung
safe_to_apply=False + Nutzer sagt "y" → keine Änderung (abgewiesen)
```

---

## Demo-Ablauf

### Voraussetzung

```powershell
# venv aktivieren
.venv\Scripts\Activate.ps1

# Jenkins starten (falls noch nicht läuft)
cd jenkins && docker compose up -d && cd ..

# Logs holen (falls noch nicht vorhanden)
python scripts/fetch_failure_logs.py
```

### Syntax-Fehler automatisch fixen

```powershell
python scripts/apply_suggested_fix.py --job failing-syntax
```

Ausgabe (gekürzt):

```
🔍 Pipeline Doctor — Sprint 3: Auto-Fix
   Job: failing-syntax

   Log gefunden: failing-syntax-build-2.log (Build #2)
   Analysiere Log mit LLM ...
   Log: 3421 → 812 Bytes (76% gespart)
   Diagnose: syntax_error (Konfidenz 0.92, 3.1s)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 DIAGNOSE & FIX-PLAN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Job             : failing-syntax
  Build           : #2
  Fehlertyp       : syntax_error
  Sicherheit      : ✅ Sicher (nach Bestätigung)

  Vorgeschlagene Änderung:
     Zeile 4: 'def multiply(x, y)'  →  'def multiply(x, y):'

  Erklärung: Fehlender Doppelpunkt in Funktionsdefinition erkannt.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Möchtest du diesen Fix anwenden? [y/N] y

   1 Zeile(n) in main.py korrigiert.

── git diff ──────────────────────────────────────────
-def multiply(x, y)
+def multiply(x, y):
──────────────────────────────────────────────────────

✅  Fix erfolgreich angewendet.
```

### Dependency-Fehler (nicht automatisch)

```powershell
python scripts/apply_suggested_fix.py --job failing-dependency
```

```
⛔  Dieser Fix wird nicht automatisch angewendet.
   Grund: Dependency-Fehler sind nicht automatisch sicher behebbar ...
```

### Test-Fehler (nicht automatisch)

```powershell
python scripts/apply_suggested_fix.py --job failing-tests
```

```
⛔  Dieser Fix wird nicht automatisch angewendet.
   Grund: Test-Failures erfordern menschliches Urteil ...
```

---

## Projektstruktur Sprint 3

```
pipeline_doctor/agent/
  fix_plan_schema.py     # FixPlan Pydantic-Schema
  auto_fix_agent.py      # AutoFixAgent: plan_fix(), run()
scripts/
  apply_suggested_fix.py # CLI-Einstiegspunkt
tests/
  test_auto_fix_agent.py # pytest-Tests (kein Jenkins, kein LLM)
```

---

## Tests ausführen

```powershell
pytest tests/test_auto_fix_agent.py -v
```

Alle Tests laufen ohne Jenkins, ohne GWDG API, ohne GitHub.
