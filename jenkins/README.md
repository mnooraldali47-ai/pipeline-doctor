# Jenkins — Lokale Einrichtung mit Docker

Jenkins läuft als Docker-Container auf Port 8080. Alle Daten werden im
Docker-Volume `pipeline-doctor-jenkins-home` gespeichert und bleiben bei
Neustarts erhalten.

---

## Voraussetzungen

- Docker Desktop installiert und gestartet
- Dieses Terminal ist im Ordner `jenkins/` geöffnet

---

## Schritt 1 — Jenkins starten

```bash
cd jenkins
docker compose up -d
```

`-d` startet Jenkins im Hintergrund. Beim ersten Start lädt Docker das
Jenkins-Image herunter (~500 MB), das dauert einige Minuten.

Status prüfen (warten bis "healthy" oder keine Fehlermeldung):

```bash
docker compose ps
docker compose logs -f
```

`Ctrl+C` beendet das Log-Streaming — Jenkins läuft weiter.

---

## Schritt 2 — Initial-Admin-Passwort finden

Beim allerersten Start generiert Jenkins ein einmaliges Passwort.
Es liegt im Container unter `/var/jenkins_home/secrets/initialAdminPassword`.

```bash
docker exec pipeline-doctor-jenkins \
  cat /var/jenkins_home/secrets/initialAdminPassword
```

Das ergibt eine Zeile wie: `a3f8c2d1e4b5...` — kopieren!

---

## Schritt 3 — Erster Login

1. Browser öffnen: **http://localhost:8080**
2. Das Passwort aus Schritt 2 einfügen → **Continue**
3. Seite **"Customize Jenkins"** erscheint

---

## Schritt 4 — Empfohlene Plugins installieren

Auf der "Customize Jenkins"-Seite:

- **"Install suggested plugins"** klicken

Jenkins installiert jetzt ~20 Standard-Plugins (Git, Pipeline, GitHub, etc.).
Das dauert 3–5 Minuten. Fortschrittsbalken abwarten.

Danach erscheint das Formular **"Create First Admin User"**:
- Benutzername, Passwort, Name, E-Mail eintragen
- **"Save and Continue"** → **"Save and Finish"** → **"Start using Jenkins"**

---

## Schritt 5 — API-Token erstellen (wichtig für Pipeline Doctor!)

Der API-Token ersetzt das Passwort für alle Programm-Zugriffe.

1. Oben rechts auf deinen **Benutzernamen** klicken
2. **"Configure"** wählen (oder direkt: http://localhost:8080/user/DEIN-USERNAME/configure)
3. Abschnitt **"API Token"** suchen
4. **"Add new Token"** klicken
5. Namen eingeben z.B. `pipeline-doctor`
6. **"Generate"** klicken
7. Token **sofort kopieren** — wird danach nicht mehr angezeigt!

Token in `.env` eintragen:

```env
JENKINS_URL=http://localhost:8080
JENKINS_USER=DEIN-USERNAME
JENKINS_TOKEN=DER-GERADE-KOPIERTE-TOKEN
```

---

## Jenkins stoppen / neu starten

```bash
# Stoppen (Daten bleiben im Volume erhalten)
docker compose down

# Starten
docker compose up -d

# Komplett löschen inkl. aller Daten (Vorsicht!)
docker compose down -v
```

---

## Nützliche Befehle

```bash
# Logs live verfolgen
docker compose logs -f

# In den Container wechseln
docker exec -it pipeline-doctor-jenkins bash

# Jenkins-URL im Browser
# http://localhost:8080
```
