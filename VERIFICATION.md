# Prüfprotokoll · 25. September 2026

## Ausbaustufe 0.2: erfolgreich geprüft

- **66 Backend-Tests** mit PostgreSQL und pgvector in der getrennten Datenbank `workagent_test` bestanden. Alle 49 bisherigen Tests bleiben enthalten. Microsoft, GitHub und OpenAI wurden simuliert.
- Die GitHub-Prüfungen decken mehrere Eigentümer, mehrseitige Repository-Erkennung, neue Repositories, persistente ETags/304-Antworten, Kommentare und deren Änderungen/Löschung, PR-Filterung, geschlossene/wiedereröffnete sowie gelöschte/verschobene Issues (404, 410, 301), Tokenfehler, Rechteentzug, gespeicherte Rate-Limit-Pausen und Wiederaufnahme eines unterbrochenen Imports ohne doppelte Issues ab.
- Tokenantworten sind redigiert; verschlüsselte Speicherung, getrennte lokale/GitHub-Statuswerte, Issue-Filter und idempotente Chat-Verknüpfung geprüft. Gesperrte GitHub-Quellen gelangen auch über wartende Embedding-Aufträge nicht an den Provider. Ein Tokenwechsel stellt den Zugriff nicht vor einem erfolgreichen Import wieder her.
- **Zwei durchgängige Playwright-Tests in Microsoft Edge** bestanden: bisheriger vollständiger Arbeitsablauf sowie GitHub-Filter, Detailansicht, Kommentare, verknüpfte PRs, Chat-Verknüpfung, kopierter Codex-Auftrag und Repository-Ausschluss. Desktop- und mobile Screenshots wurden geprüft.
- Der bisherige Browserablauf prüft weiter Eingang → Chat → bearbeiteter und bestätigter Demoentwurf, Demoantwort, Wissenseditor, Fundstellen, Upload, lokale Aufgabe, Kalenderentwurf und Einstellungen. Kalenderzeiten werden bei Browser-Zeitzone America/New_York auf Europe/Berlin geprüft.
- **React-Debugger-Test** in Edge erfolgreich: Haltepunkt bei einem tatsächlichen Rendern von `Workspace.tsx`, Source-Map vorhanden, Fortsetzung bis zur bedienbaren Seite erfolgreich.
- **API- und Worker-Debugger** über DAP erfolgreich: Haltepunkte in `features/system/service.py` und `worker.py` wurden mit den Windows-/Container-Pfadzuordnungen aus der VS-Code-Konfiguration erreicht und fortgesetzt. Die Prüfung wurde nach erneutem Containerstart wiederholt. Der Worker-Healthcheck prüft den geöffneten Port ohne einen zweiten Debugger-Client zu verbinden.
- `scripts/dev.ps1 up/down` geprüft. Beim Stoppen bleiben reguläre Dienste auf Port 8080 erreichbar. Nach erneutem Start sind alle vier GitHub-Demo-Issues unverändert vorhanden. Datenbank, Dateien, Schlüssel und Cookie-Namen sind getrennt. Für die Debugger-Anbindung wird nachweislich kein lokaler Python-Interpreter benötigt: Die installierte VS-Code-Erweiterung verwendet für `attach/connect` direkt einen `DebugAdapterServer`.
- **Migrationen:** frische PostgreSQL-Datenbank bis Revision `0002` einschließlich pgvector erfolgreich. Zusätzlich wurde die tatsächliche Sicherung des bisherigen Schemas vom 25.09.2026, 17:04 Uhr, in `workagent_migration_backup` auf dem Entwicklungsserver wiederhergestellt und aktualisiert. SHA-256 über sämtliche bisherigen Tabelleninhalte war vor und nach der Migration identisch. Diese reguläre Installation war noch nicht mit Benutzer-/Arbeitsdaten eingerichtet; ergänzend wurde die bereits befüllte Browser-Demo von 0001 auf 0002 aktualisiert und mit den bestehenden Inhalten getestet.
- **Neun isolierte Skill-Tests** bestanden: echte lokale Branches, Worktrees, Commits und Pushes in temporäre lokale Bare-Repositories; GitHub-Antworten einschließlich Draft-PR-Erstellung sind simuliert. Geprüft wurden fremde Änderungen, belegter Checkout, Wiederaufnahme, nicht freigegebene PR-Konstellationen, fremde gestagte Dateien, unveröffentlichte Default-Branch-Commits und unklare Push-/PR-Rückmeldungen. Keine Veröffentlichung in echten Projekten.
- Persönlicher Skill unter `%USERPROFILE%/.codex/skills/github-issue-fix` installiert, automatischer Aufruf aktiviert. Offizieller `quick_validate.py`-Validator erfolgreich. Die gepflegte Vorlage und ein gezielter Installer liegen im Projekt.
- VS-Code-Python-Debugger installiert. Docker Desktop `AutoStart` und der Windows-Benutzer-Autostarteintrag aktiviert. Es wurde kein Windows-Neustart oder Ab-/Anmelden während der Arbeit ausgelöst.
- TypeScript-Prüfung und Vite-Produktionsbuild erfolgreich. Fachansichten werden getrennt nachgeladen; das initiale JavaScript-Bündel liegt unter der Vite-Warngrenze von 500 kB vor Kompression.

## Weiterhin gültige Prüfungen der ersten Version

Sitzungen/CSRF, Quellenfreigaben und Kontextausschluss, Suchvektoren, Budgetgrenzen, Freigabeversionen, Schutz vor doppeltem Versand und unklaren Ergebnissen, Microsoft-Delta/Paginierung/Löschungen, Kalender-Endpunkte und die OneDrive-Ordnergrenze sind durch die bestehende Suite abgedeckt. DOCX, XLSX, PPTX, Text, verschlüsseltes PDF sowie tatsächliches Tesseract-OCR auf Bild und gescanntem PDF wurden geprüft. Wissensversionen, Konflikte, Export und historische Fundstellen bleiben erfolgreich.

PowerShell-Sicherung und Wiederherstellung einer Demo-Installation in eine frische Installation wurden bereits in Ausbaustufe 0.1 geprüft: Passwort, Notizversion, extrahierter Dokumenttext, Dateien und Hauptschlüssel stimmten überein. Vor dem regulären Update auf 0.2 wurde erneut das vollständige Backup-Skript ausgeführt: `backups/20260925-172923` mit separatem Schlüsselordner.

## Grenzen der Abnahme

Keine echten Microsoft-, GitHub- oder OpenAI-Zugangsdaten verwendet, keine echten Nachrichten versendet, keine echten PRs erstellt. Entra-Zustimmung, Firmenrichtlinien, Tokenrechte und Modellverfügbarkeit sind nach Eingabe der Zugangsdaten über die vorgesehenen Verbindungstests zu prüfen.

Die VS-Code-Konfiguration wurde über denselben Start-/Stop-Task, die realen Debuggerports und Edge/Source-Maps geprüft; die F5-Taste in einem interaktiven VS-Code-Fenster wurde nicht automatisiert bedient. Docker-Neustartregeln und Benutzer-Autostart sind konfiguriert; den tatsächlichen Start nach einer Windows-Anmeldung kann erst die nächste Anmeldung bestätigen.

Pytest meldet weiterhin eine Deprecation-Warnung der Starlette-Testclient/httpx-Kombination. Die ausgeführten Tests sind erfolgreich. Wiederholbare Befehle: [Entwickleranleitung](docs/DEVELOPMENT.md), [Architektur](docs/ARCHITECTURE.md).
