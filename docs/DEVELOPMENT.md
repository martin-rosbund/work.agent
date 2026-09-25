# Entwicklung mit F5

Benötigt werden Docker Desktop mit Linux-Containern und VS Code. Python, Node, PostgreSQL und Tesseract laufen in Docker. Die empfohlenen VS-Code-Erweiterungen stehen in `.vscode/extensions.json`; Python Debugger (`ms-python.debugpy`) ist erforderlich, der Edge-Debugger gehört zu VS Code.

1. Projektordner in VS Code öffnen.
2. **Ausführen und Debuggen → Gesamte Anwendung → F5** wählen.
3. Beim ersten Start öffnet das Startskript den geschützten Einrichtungslink. Ein eigenes lokales Passwort festlegen; Demo aktiviert lassen. Falls nötig: `powershell -ExecutionPolicy Bypass -File scripts/dev-setup.ps1`.
4. Im vom Debugger geöffneten Edge unter `http://localhost:5173` mit diesem Passwort anmelden.
5. Haltepunkte in `frontend/src/...`, `backend/app/features/.../service.py` und `backend/app/worker.py` setzen.

Einzelkonfigurationen **Frontend**, **Backend** und **Worker** starten dieselbe Entwicklungsumgebung. **Gesamte Anwendung** startet die Container einmal und verbindet alle drei Debugger. Keine Konfiguration wartet beim Containerstart auf den Debugger; die Healthchecks können deshalb ohne gegenseitiges Warten erfolgreich werden. Beim Stoppen der Gesamtsitzung werden die Debugger getrennt und die Entwicklungscontainer gestoppt. Volumes und Dateien bleiben erhalten.

React lädt Änderungen automatisch nach. Bei Python-Änderungen die Debugsitzung beenden und erneut starten oder den Task **Work Agent: Python neu starten** ausführen und die Debugger neu verbinden. Bewusst kein zusätzlicher Python-Reload-Prozess: Haltepunkte bleiben einem eindeutigen API-/Worker-Prozess zugeordnet.

## Getrennte Umgebungen

| | Regulär | Entwicklung |
|---|---|---|
| Compose-Projekt | `work-agent` | `work-agent-dev` |
| Browser | `http://localhost:8080` | `http://localhost:5173` |
| Dateien | `data/` | `.local/dev/data/` |
| Geheimnisse | `.secrets/`, `.env` | `.local/dev/secrets/`, `.local/dev/environment` |
| DB-Volume | `work-agent_database` | `work-agent-dev_database` |
| Debugger | keine veröffentlichten Ports | `127.0.0.1:5678` API, `127.0.0.1:5679` Worker |
| Neustart | `unless-stopped` | über F5/Entwicklungsskript |

GitHub-Demodaten werden idempotent ergänzt und niemals mit echten Konten synchronisiert. Anmeldungen, Kennwörter und Cookie-Namen sind pro Umgebung getrennt. Beide Umgebungen können parallel unter `localhost` verwendet werden; ihre Sitzungen überschreiben sich nicht.

```powershell
./scripts/dev.ps1 up
./scripts/dev.ps1 down
./scripts/dev.ps1 restart -NoBrowser
./scripts/generate-api.ps1
```

`down` stoppt ausschließlich Entwicklungsdienste und löscht keine Volumes. Die reguläre Installation startet nach der Windows-Anmeldung mit Docker Desktop wieder, sofern sie nicht ausdrücklich per `docker compose stop` angehalten wurde. `scripts/enable-docker-autostart.ps1` aktiviert den Benutzer-Autostart. Ein Windows-Neustarttest muss auf dem tatsächlichen Rechner durchgeführt werden; es wird kein Dienst vor der Anmeldung eingerichtet.

## GitHub einrichten

In der GitHub-Seite **Verbindungen** öffnen. Einen Fine-grained PAT pro Eigentümer eintragen: eigener Kontoname oder Organisation. Repository-Berechtigungen: Metadata, Issues und Pull requests jeweils **Read-only**. Für automatische Aufnahme neuer Repositories muss der Token auf **All repositories** stehen. Firmen können eine zusätzliche Freigabe verlangen.

Die Verbindung wird alle 15 Minuten auf Repositories geprüft, die Issue-Quellen alle fünf Minuten. Manuelle Aktualisierung läuft über dieselbe Queue. Ausgeschlossene Repositories und entzogene Rechte sperren Suche und KI-Kontext. Repositories lassen sich unabhängig zur KI-Verarbeitung freigeben. Das lokale Bearbeitungskennzeichen verändert den GitHub-Status nicht.

Der Erstimport umfasst alle offenen und die in 90 Tagen aktualisierten geschlossenen Issues. Kommentare und PR-Verweise werden mit importiert; Pull Requests aus Issue-Listen werden herausgefiltert. Überlappende Änderungsfenster, ein täglicher Bestandsabgleich und ein persistenter ETag-/Seitencache ermöglichen Wiederaufnahme ohne doppelte Issues. API-Limits pausieren die Verbindung bis zur gespeicherten Wiederaufnahmezeit. Zwischenstände werden pro Seite/Issue gesichert; der fachliche Cursor wird erst nach einem vollständig erfolgreichen Lauf vorgezogen.

**Codex-Auftrag kopieren** kopiert `fix issue owner/repository#123`. Der Button startet keinen Agenten. Der persönliche Skill verwendet später die Git-/GitHub-Anmeldung des Entwicklungsprojekts und kann daher andere Rechte als der ausschließlich lesende Work-Agent-Token besitzen.

## Persönlichen Skill aktualisieren

```powershell
./scripts/install-issue-skill.ps1
```

Die gepflegte Vorlage liegt unter `skills/github-issue-fix/`. Der Installer aktualisiert ausschließlich die drei Dateien dieses Skills in `$CODEX_HOME/skills/github-issue-fix` beziehungsweise `%USERPROFILE%/.codex/skills/github-issue-fix`. Automatische Auswahl ist aktiviert. Beispiel: `$github-issue-fix fix issue #123`. Neue Codex-Aufgaben laden die neu installierte Skill-Version.

## Prüfungen

- Backend: `docker compose run --rm -v "${PWD}/backend/tests:/app/tests:ro" api python tests/run_postgres.py` (ausschließlich Datenbank `workagent_test`; bei Bedarf vorher im regulären DB-Container mit `createdb -U workagent workagent_test` anlegen).
- Browser: getrennte Installation mit `docker compose -p work-agent-e2e -f compose.yaml -f compose.test.yaml up -d --build --wait`, danach im Frontend `npx playwright test github.spec.ts workspace.spec.ts`.
- Debugger: bei laufender Entwicklung `node tests/debug-smoke.mjs`; für React im Frontend `$env:DEBUG_SMOKE='1'; npx playwright test frontend-debug.spec.ts`.
- Skill: `python tests/test_issue_workflow.py` nutzt lokale Bare-Repositories und simuliertes `gh`. Es veröffentlicht nichts in echten Projekten.
- Migration: `backend/scripts/verify_migrations.py` läuft ausschließlich im Entwicklungscontainer und prüft frische Datenbanken bzw. einen dort separat wiederhergestellten Datenbankdump. Details und Ergebnisse stehen in `VERIFICATION.md`.

Die Prüfwerkzeuge dürfen einen auf dem Entwicklerrechner vorhandenen Node-/Python-Runtime verwenden; der normale F5-Betrieb setzt diese nicht voraus. Echte Microsoft-, GitHub- und OpenAI-Tests werden erst durch die jeweiligen Verbindungstest-Buttons nach Eingabe echter Zugangsdaten ausdrücklich ausgelöst.
