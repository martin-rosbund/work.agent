# Architektur und Datenfluss

Work Agent ist eine lokale Einbenutzer-Anwendung. React spricht ausschließlich die versionierte REST-API an. FastAPI und der separate Worker verwenden dieselben Anwendungsdienste. PostgreSQL hält auch Jobs, Ereignisse, Volltextindex und Vektoren; zusätzliche Queue-Dienste sind nicht nötig.

```text
Browser / React
  → /api/v1 → Anmeldung + CSRF → Feature-Router → Anwendungsdienst
                                                   ↓
                                          PostgreSQL + Dateispeicher
                                                   ↑
                                              Job-Worker
                                                   ↓
                           Microsoft Graph / GitHub / OpenAI Adapter
```

## Backend

`backend/app/main.py` setzt die Anwendung zusammen: Middleware, Fehlerbehandlung und Router. Keine Geschäftslogik und keine Importaufträge beim Python-Import.

| Verzeichnis | Verantwortung |
|---|---|
| `core/` | Konfiguration, SQLAlchemy-Sitzungen und gemeinsame Persistenzmodelle, Geheimnisse, Einstellungen, Queue, Ereignisse, Audit und Betriebsprotokollierung |
| `api/` | HTTP-Abhängigkeiten und öffentliche Antwortverträge |
| `features/auth/` | Lokale Einrichtung, Anmeldung, Sitzungen |
| `features/connections/` | Microsoft-Verbindung, Quellenauswahl, KI-Konfiguration und Quellenfreigaben |
| `features/content/` | Eingang, Quellenzugriff, idempotenter Import, Suchabschnitte, Datei-/Quellenansicht |
| `features/chats/` | Arbeitschats, verknüpfte Inhalte und Nachrichten |
| `features/knowledge/` | Upload, lokale Extraktion/OCR, Notizen, Versionierung und Markdown-Export |
| `features/planning/` | Aufgaben- und Kalenderansichten sowie lokale Aufgabenerstellung |
| `features/proposals/` | Vorschläge, Bearbeitung, versionsgebundene Freigabe und Ausführung |
| `features/agent/` | KI-Kontext, Verbrauchslimits, Suche, Analyse und Chat-Orchestrierung |
| `features/github/` | Verbindungen, Repositories, Issues, Kommentare, Synchronisierung und Demo |
| `features/crm/` | Persönliche ISB.CRM-Verbindung und dynamische Auswahlkataloge |
| `features/system/` | Gesundheit, API-Dokumentation, Ereignisstrom und Betriebsübersicht |
| `integrations/` | Microsoft-, GitHub-, ISB.CRM- und OpenAI-Adapter; Registry der Quellkonnektoren |

Jeder HTTP-Fachbereich besitzt `router.py`, `schemas.py` und `service.py`. Die Router übernehmen Transport und Authentifizierung; Services prüfen fachliche Regeln. `storage.py`, `ingestion.py` und `execution.py` kapseln gemeinsam verwendete Abläufe. Die kleinen Dateien im bisherigen `app/`-Namensraum sind Kompatibilitätsimporte für bestehende Aufrufer und Tests.

Die Queue beansprucht Jobs transaktional mit `FOR UPDATE SKIP LOCKED`. Wiederaufnahme und Wiederholungen laufen zentral im Worker. Ein ungeklärtes Ergebnis einer externen Schreibaktion wird als `unknown` gespeichert und **nicht automatisch erneut gesendet**. GitHub stellt ausschließlich GET-Transport bereit; es existiert kein GitHub-Schreibadapter und kein Codex-Ausführungsdienst.

## Quellenfreigaben und Aktionen

Alle importierten Inhalte haben ein `Source`- und ein `Item`-Objekt. GitHub ergänzt eigene Tabellen für Verbindungen, Repositories, Issues, Kommentare und HTTP-Cache. Ein Repository entspricht einer Quelle; neue Quellen erhalten `ai_enabled=false`. `visible_item`, `allowed_chunks`, Kontextaufbau und Worker-Verarbeitung prüfen Verfügbarkeit und Zustimmung erneut. Sperren gelten auch für bereits gespeicherte Inhalte. Bestätigte eigene Wissensnotizen bleiben eigenständige Inhalte.

Microsoft-Schreibaktionen gehen ausschließlich durch den Vorschlagsdienst: Entwurf → bearbeitete Version → Freigabe des Inhalts-Hashes → Ausführung. Ein späterer MCP-Adapter kann diese Services nutzen, muss jedoch eine eigene Maschinenanmeldung und Autorisierungsgrenze ergänzen. Ein HTTP-Cookie darf dafür nicht einfach als dauerhafter API-Schlüssel verwendet werden. MCP ist hier noch nicht implementiert.

## Öffentliche API

- Basis: `/api/v1`, Vertrag: `/api/v1/openapi.json`, lokale Dokumentation: `/api/v1/docs`.
- JSON-Antworten besitzen explizite Pydantic-Modelle. Persistenzobjekte werden vom Antwortmodell gefiltert; Tokens und lokale Dateipfade gehören nicht zum Vertrag.
- Kalender, Aufgaben und Vorschläge: `/calendar`, `/tasks`, `/proposals`. Bestehende `/items`-Abfragen bleiben kompatibel.
- GitHub: `/github/connections`, `/{id}/test`, `/github/repositories`, `/github/issues`, `/github/issues/{id}`, `/{id}/conversation`, `/github/sync`.
- Fortschritt und Chat-Text: `/events` als Server-Sent Events. Verbraucher laden nach einer Änderung die betroffene Ansicht neu.
- Dynamische Quellmetadaten dürfen anbieterspezifische Zusatzfelder enthalten. Die im UI verwendeten Felder sind im öffentlichen Vertrag beschrieben.

Der exportierte Vertrag liegt unter `contracts/openapi.json`; `frontend/src/api/generated.ts` wird daraus erzeugt. `scripts/generate-api.ps1` führt beide Schritte mit Docker aus. Generierte Dateien werden nicht von Hand bearbeitet.

## Frontend

`src/App.tsx` ist der Einstieg. `app/Workspace.tsx` hält Anmeldung, Navigation, globale Suche und Zusammensetzung der Seiten. `features/` enthält die fachlichen Ansichten; `shared/` enthält Darstellung, Dialoge, Buttons und Meldungen. `api/client.ts` kapselt Fetch/CSRF, `api/types.ts` verwendet die generierten Verträge. Der frühere `api.ts`-Import bleibt als kleiner Kompatibilitätsexport bestehen.

## Eine weitere Quelle ergänzen

1. Transport unter `integrations/<anbieter>/` implementieren. Zugangsdaten verschlüsseln und niemals als Teil einer öffentlichen Antwort zurückgeben.
2. Fachkonfiguration, Eingabe-/Ausgabemodelle und dünne Routen unter `features/<quelle>/` hinzufügen.
3. Eine `Source` je separat freigebbarem Bereich erzeugen; KI standardmäßig deaktivieren.
4. Daten über `features/content/ingestion.upsert` importieren, stabile externe IDs und Inhaltsversionen verwenden. Vollständige Paginierung vor Bestandsabgleich abschließen.
5. Adapter in `integrations/registry.py` registrieren; dieselbe Synchronisierung aus Worker und manuellen Jobs aufrufen.
6. Rechteentzug, Löschungen, Cursorverlust, Drosselung und Wiederholungen simuliert testen. Generierte API-Typen aktualisieren und die Feature-Seite hinzufügen.
7. Neue Tabellen mit einer neuen Alembic-Revision ergänzen. Historische Schema-Schnappschüsse niemals aus aktuellen ORM-Modellen ableiten oder nachträglich erweitern.

Die Revisionen `0001` und `0002` verwenden getrennte, eingefrorene Schemata. Damit erzeugt eine frische Installation genau denselben Verlauf wie das Upgrade einer vorhandenen Datenbank.
