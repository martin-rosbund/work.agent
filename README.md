# Work Agent

Persönlicher Arbeitsraum für Microsoft 365, ISB.CRM, KI-Arbeitschats und ein versioniertes Wissensarchiv. React/TypeScript und FastAPI sind getrennte Anwendungen; PostgreSQL, pgvector und ein eigener Worker halten Daten und Verarbeitung lokal.

ISB.CRM wird mit einem persönlichen API-Key als eigene Verbindung eingerichtet. Kalender, Aufwandsschätzungen, Office Tasks, Verkaufschancen und CRM-Tickets bleiben getrennte Quellen mit dynamischen CRM-Statuswerten. Einrichtung, Freigaben und Synchronisierungsumfang: [CRM-Anleitung](docs/CRM.md).

## Schnellstart unter Windows

Voraussetzung: Docker Desktop mit gestarteter Linux-Engine. Im Projektordner:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Das Skript erstellt zufällige Geheimnisse, baut die Container und öffnet [localhost:8080](http://localhost:8080) mit dem einmal benötigten Einrichtungscode. Wähle ein Passwort mit mindestens zwölf Zeichen. Optional lassen sich gekennzeichnete Beispieldaten laden. Ohne API-Schlüssel werden ausschließlich bei diesen Demo-Nachrichten Beispielantworten erzeugt; Demo-Aktionen versenden nichts.

Nur Docker wird benötigt. Der erste Build lädt Python-/Node-Pakete sowie deutsche und englische OCR-Daten. Spätere Starts verwenden vorhandene Images. `docker compose stop` hält die Anwendung an, `docker compose up -d` startet sie wieder. Niemals `docker compose down -v` verwenden, wenn die Datenbank erhalten bleiben soll.

## Neu: F5, GitHub-Issues und persönliche Issue-Fixes

Für die Entwicklung in VS Code **Ausführen und Debuggen → Gesamte Anwendung → F5** wählen. Die Entwicklungscontainer öffnen `http://localhost:5173` mit eigenen Demodaten, Geheimnissen und Datenbank. Regulärer Betrieb bleibt auf `http://localhost:8080`. Python, Node und OCR laufen auch beim Debuggen in Docker. React lädt Änderungen automatisch nach; für Python die Debugsitzung neu starten.

Die neue Seite **GitHub** bietet Repository-Auswahl, Issue-Filter, Kommentare, verknüpfte PRs und Arbeitschats. Fine-grained Tokens werden je Eigentümer verschlüsselt gespeichert. Benötigt werden ausschließlich lesende Rechte für Metadata, Issues und Pull requests. Neue Repositories sind zunächst von KI-Verarbeitung ausgeschlossen.

**Codex-Auftrag kopieren** erzeugt zum Beispiel `fix issue owner/repository#123`. Den persönlichen Ablauf bis zum Draft-PR installiert `./scripts/install-issue-skill.ps1`; der gepflegte Skill liegt unter `skills/github-issue-fix/`. Es gibt keinen Codex-Ausführungsdienst in dieser Anwendung.

Ausführlich: [F5 und Entwickleranleitung](docs/DEVELOPMENT.md), [Modulstruktur und API](docs/ARCHITECTURE.md), [Prüfprotokoll](VERIFICATION.md). Die REST-API bleibt unter `/api/v1`; [lokale API-Dokumentation](http://localhost:8080/api/v1/docs) und [OpenAPI-Vertrag](contracts/openapi.json) sind verfügbar. Ein späterer MCP-Adapter kann dieselben Services verwenden.

## Microsoft verbinden

1. In [Microsoft Entra](https://entra.microsoft.com/) eine **Single-Tenant-App** für dein Firmenkonto registrieren.
2. Eine **Web**-Redirect-URI eintragen: `http://localhost:8080/api/v1/microsoft/callback`.
3. Ein Client-Secret erstellen. **Wert**, Tenant-ID und Client-ID in Einstellungen → Verbindungen speichern.
4. Microsoft-Anmeldung durchführen. Bei „Quelle hinzufügen“ den Bereich wählen, dessen Berechtigung erteilen und konkrete Ordner, Chats, Kanäle, Kalender oder Aufgabenlisten auswählen.
5. KI-Verarbeitung und Schreibzugriff pro Quelle bewusst aktivieren. Das Schild-Symbol neben der Quelle erneuert die Zustimmung für geänderte Rechte.

Die Anwendung verwendet MSAL, Authorization Code mit PKCE, serverseitigen Tokencache und delegierte Berechtigungen. Es werden keine Application Permissions benötigt. Firmenrichtlinien, Conditional Access und Admin-Zustimmung können einzelne Bereiche sperren. Private Microsoft-Konten und fremde Postfächer sind nicht Teil dieser Version. Eine App-Registrierung ersetzt weder deine Anmeldung noch die Freigabe deiner IT.

Bei Teams-Chats zeigt die Quellenauswahl bereits die ersten 50 Chats an und lädt weitere Seiten im Hintergrund. Das Suchfeld durchsucht Chatnamen und Teilnehmernamen der bereits geladenen Chats. Alternativ lässt sich **Alle eingehenden Direktnachrichten** ohne Kontaktauswahl verbinden: Diese Sammelquelle erfasst auch neue 1:1-Kontakte, aber keine eigenen Nachrichten, Gruppenchats, Besprechungen oder Systemmeldungen. Der Erstimport umfasst standardmäßig 90 Tage und läuft in kleinen Paketen. KI-Verarbeitung und Aktionen nach Freigabe werden weiterhin für die Quelle separat aktiviert. Bereits einzeln verbundene Chats können zusätzlich dieselben Nachrichten enthalten; deaktiviere sie bei Verwendung der Sammelquelle, wenn du doppelte Einträge vermeiden möchtest.

| Bereich | Lesen / Auswahl | Zusätzliche Schreibrechte |
| --- | --- | --- |
| Profil | User.Read | – |
| E-Mail | Mail.Read | Mail.ReadWrite, Mail.Send |
| Chats | Chat.Read | ChatMessage.Send |
| Teams-Kanäle | Team.ReadBasic.All, Channel.ReadBasic.All, ChannelMessage.Read.All | ChannelMessage.Send |
| Kalender | Calendars.Read | Calendars.ReadWrite |
| To Do | Tasks.Read | Tasks.ReadWrite |
| Dateien | Files.Read.All, Sites.Read.All | – |

`openid`, `profile` und `offline_access` werden von MSAL für Anmeldung und Erneuerung ergänzt. Die Microsoft-Berechtigungen für Dateien können weiter reichen als die ausgewählten Ordner; die Anwendung beschränkt Import und KI-Kontext auf deine Auswahl. SharePoint wird über die Site-URL verbunden, nicht über eine vollständige tenantweite Site-Auflistung.

## OpenAI und Wissen

API-Schlüssel unter Verbindungen speichern; unter „Dein Agent“ ein verfügbares Responses-fähiges Textmodell und Embedding-Modell auswählen. „Speichern & Modelle testen“ sendet nur Testtext, keine Arbeitsdaten. Modellnamen werden nicht aus einem ChatGPT-Abonnement übernommen; API-Nutzung wird separat abgerechnet.

Pro Quelle entscheidet **KI erlaubt** über Analyse, Embeddings und die Aufnahme in den Chatkontext. Die globale Suche ist eine lokale Volltextsuche. Der Agent kombiniert Volltexttreffer und semantische Treffer, wenn OpenAI eingerichtet ist. `store: false` deaktiviert die Speicherung der Responses; [weitere Aufbewahrungsregeln beim Anbieter](https://developers.openai.com/api/docs/guides/your-data) bleiben davon unabhängig.

Unterstützt werden MD/TXT, textbasierte und gescannte PDFs, DOCX, XLSX, PPTX, PNG/JPEG/TIFF. Text und OCR werden lokal extrahiert. Grenzen: 25 MB pro Datei, 300 PDF-Seiten, 50.000 Zeilen pro Tabellenblatt, 180 Sekunden pro Dokument. Formeln werden nicht ausgeführt; XLSX verwendet vorhandene Ergebniswerte. Alte binäre Office-Formate und passwortgeschützte Dokumente werden nicht entschlüsselt. Handschrift, komplexe Tabellen und Bilddiagramme können unvollständig erkannt werden. Fundstellen zeigen Seite, Folie oder Tabellenzeile.

Notizen werden in PostgreSQL versioniert und atomar nach `data/knowledge/<id>.md` exportiert. Die Datenbank ist die maßgebliche Fassung: Änderungen erfolgen über den Editor; externe Änderungen an exportierten Markdown-Dateien werden nicht automatisch importiert. Originaldokumente bleiben unter `data/originals`. Der Suchindex ist daraus wiederherstellbar.

## Freigaben und Synchronisierung

Ein Vorschlag ist zuerst nur ein Entwurf. Bearbeitung erhöht seine Version. Die explizite Freigabe bindet Typ, Inhalt, Ziel und Version über einen Hash. Der Worker führt nur solche freigegebenen Vorschläge aus. Schreibzugriff pro Quelle und erlaubte Aktionen im Agentenprofil sind zusätzliche Schranken. E-Mail-Antworten gehen an den angezeigten ursprünglichen Absender; Reply-all, neue E-Mails und Anhänge beim Versand sind nicht enthalten.

Ein unklarer Netzwerk- oder Prozessfehler während einer Schreibaktion ergibt **Ergebnis unklar**. Es erfolgt kein automatisches erneutes Senden. Zuerst direkt in Outlook/Teams/To Do prüfen. Termine erhalten zusätzlich eine Graph-`transactionId`. To-Do-Änderungen prüfen die bekannte Quellversion vor dem Schreiben.

Nachrichten werden alle zwei Minuten, andere Microsoft-Quellen alle fünf Minuten aktualisiert. Mail und der Hauptkalender verwenden Delta-Cursor; weitere Kalender werden paginiert vollständig abgeglichen ([Graph unterstützt Kalender-Delta nur für den Hauptkalender](https://learn.microsoft.com/en-us/graph/api/event-delta?view=graph-rest-1.0)). Dateien verwenden Drive-Delta plus kontrollierte Ordnerabstimmung; Teams nutzt paginierte Nachrichten und Kanalantworten. Tägliche Bestandsabstimmung ergänzt inkrementelle Abfragen. Der erste Import analysiert alte Nachrichten nicht automatisch: „Vorschläge erstellen“ startet dies bewusst. Hintergrundaufrufe werden nach dem konfigurierten Tageslimit pausiert und später fortgesetzt. Erstimporte und große Dateibestände können dauern.

Die Quellsysteme bleiben maßgeblich. Entzogene Rechte sperren ihre Inhalte für Suche/KI; entfernte Inhalte werden als nicht verfügbar markiert. Bestätigte eigene Notizen bleiben bestehen. Die lokale Datenhaltung ist damit kein revisionssicheres Unternehmensarchiv. Betrieb ist für eine Worker-Instanz und einen Benutzer vorgesehen.

## Backup, Wiederherstellung, Update

```powershell
.\scripts\backup.ps1
.\scripts\restore.ps1 -BackupPath C:\Sicherungen\20260925-150000
.\scripts\update.ps1
```

Backup stoppt API und Worker kurz, sichert PostgreSQL und Dateien und startet beide wieder. Ein gleichnamiger `.keys`-Ordner enthält getrennt die Schlüssel und `.env`; bewahre ihn geschützt und möglichst auf einem separaten Medium auf. Prüfsummen erkennen beschädigte Sicherungsdateien. Restore ist ausschließlich für eine **frische Installation mit leerer Datenbank und leerem Datenordner** bestimmt und löscht keine bestehende Datenbank. `.keys` ist zum Entschlüsseln der Tokens zwingend erforderlich. Updates verwenden den aktuellen Projektstand; ein Git-Pull findet nicht automatisch statt.

Es wird nur `127.0.0.1:8080` veröffentlicht. Kein Mehrbenutzer- oder öffentlicher Hostingbetrieb. Dokumente, Suchdaten und Backups sind nicht automatisch verschlüsselt; Windows-Laufwerksverschlüsselung schützt gegen Offline-Zugriff bei Geräteverlust. Geheimnisse sind separat geschützt, entschlüsseln sich aber für den laufenden Backendprozess. Inhalte aus E-Mails werden als Text dargestellt; externe Tracking-Bilder werden nicht geladen.

## Entwicklung und Prüfungen

```powershell
# Frontend
cd frontend
npm ci
npm run build
cd ..

# Backend im Container, ohne echte Microsoft-/OpenAI-Zugangsdaten
docker compose run --rm -v "${PWD}/backend/tests:/app/tests:ro" api pytest -q

# Dieselbe Suite mit PostgreSQL und pgvector, in eigener Testdatenbank
docker compose exec db createdb -U workagent workagent_test
docker compose run --rm -v "${PWD}/backend/tests:/app/tests:ro" api python tests/run_postgres.py

# Browserprüfung in eigener Demo-Installation auf Port 8081
docker compose -p work-agent-e2e -f compose.yaml -f compose.test.yaml up -d --wait
cd frontend
npx playwright test
```

Die Browserprüfung verwendet Microsoft Edge und verändert ausschließlich die isolierten Demodaten. Die Produktionskonfiguration bleibt unberührt. `package-lock.json` und `requirements.lock.txt` halten die geprüften Paketversionen fest.

Die REST-Spezifikation liegt unter `/api/v1/openapi.json`, die vollständig lokal dargestellte API-Referenz unter `/api/v1/docs`. API-Bereiche: Auth, Einstellungen, Microsoft-Anmeldung/Auswahl, Quellen, Inhalte, Dokumente, Wissen/Versionen, Arbeitschats, Vorschläge/Freigaben, Aktivität und SSE-Ereignisse. Schreibende API-Anfragen benötigen die Sitzung und `X-CSRF-Token`; Anmelde-/Einrichtungsanfragen werden zusätzlich auf Herkunft geprüft. Der einmalige Setup-Code liegt in `.secrets/setup_token`.

Die Quellschnittstelle liegt in `backend/app/connectors.py`, der Microsoft-Adapter in `backend/app/graph.py`, Generierungs- und Embedding-Schnittstellen in `backend/app/ai.py`. Weitere Anbieter werden als eigene Adapter ergänzt; OpenAI ist die einzige implementierte Cloud-Anbindung. PostgreSQL-Migrationen liegen unter `backend/migrations`. Eine SQLite-Testdatenbank dient schnellen isolierten Tests, nicht dem produktiven Dockerbetrieb.
