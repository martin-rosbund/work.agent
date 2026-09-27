# ISB.CRM verbinden

Unter **Einstellungen → Verbindungen → ISB.CRM** die CRM-Adresse und den persönlichen API-Key eintragen. Die Adresse ist der Ursprung ohne `/api` oder Tabellenpfad. Wenn das Backend auf einer anderen Adresse läuft, dessen Ursprung unter **Abweichende API-Adresse** eintragen.

Für die lokale ISB.CRM-Entwicklungsumgebung:

- CRM-Adresse: `http://localhost:5173`
- API-Adresse: `http://localhost:3000`
- API-Key: persönlicher Key aus genau diesem lokalen CRM-System

In Docker übersetzt der Konnektor lokale Adressen intern auf `host.docker.internal`. Links zur CRM-Oberfläche verwenden weiterhin die eingetragene CRM-Adresse. Für entfernte Systeme ist HTTPS erforderlich. Weiterleitungen werden nicht verfolgt. Der Key wird verschlüsselt gespeichert und nie über die Einstellungs-API zurückgegeben.

**Verbinden & prüfen** prüft das persönliche Profil und die Leserechte der vier Entities. Danach gibt es vier einzeln aktivierbare Quellen:

| Quelle | CRM-Entity | Persönlicher Umfang | Datum |
|---|---|---|---|
| CRM · Kalender | `event` | Zuständiger Benutzer oder Teilnehmer | `startDate`, `endDate` |
| CRM · Aufwandsschätzungen | `effortEstimate` | `assigneePerson` | `expectedCompletionDate` |
| CRM · Office Tasks | `internalCase` | `responsiblePerson` | kein Fälligkeitsfeld |
| CRM · Verkaufschancen | `salesOpportunity` | `assigneePerson` | `closeDate` |

KI-Freigabe und Schreibzugriff sind anfangs ausgeschaltet. Beides kann pro Quelle unter **Deine Quellen** aktiviert werden. Der CRM-Key übernimmt die Rechte des jeweiligen CRM-Benutzers; Entity- und Feldrechte werden weiterhin durch das CRM geprüft. Benötigt werden Lesezugriff auf das eigene Profil, die ausgewählten Entities und ihre Status-/Auswahlkataloge. Anlegen und Bearbeiten benötigen zusätzlich die entsprechenden Insert-/Update-Rechte.

## Aufgaben und Termine

1. Unter **Aufgaben → Neue Aufgabe** die gewünschte CRM-Quelle im Feld **Ziel** auswählen. Für Verkaufschancen zusätzlich die Herkunft auswählen.
2. Alternativ unter **Kalender → Termin vorschlagen** den CRM-Kalender auswählen und Beginn/Ende eingeben.
3. **Entwurf speichern**, Vorschlag kontrollieren und **Prüfen & freigeben**. Erst **Verbindlich freigeben** erzeugt einen Schreibauftrag.
4. Bestehende CRM-Aufgaben lassen sich über **Bearbeiten** ändern. Das Häkchen öffnet einen Abschlussvorschlag, in dem ein CRM-Endstatus ausgewählt werden muss. Ein eigener, nicht wiederkehrender CRM-Termin lässt sich über den Kalendereintrag bearbeiten. Für Terminbearbeitung muss zusätzlich die Aktion **CRM-Termin bearbeiten** unter **Dein Agent** erlaubt sein.

Ein Arbeitschat kann z. B. „Erstelle einen Vorschlag für eine Aufwandsschätzung im CRM“ in einen entsprechenden Entwurf übersetzen. Die Zielquelle und notwendige CRM-Auswahlwerte bleiben vor der Freigabe bearbeitbar. Wenn die verlangte CRM-Quelle nicht schreibbar verfügbar ist, wird der Entwurf nicht automatisch in einem anderen Zielsystem angelegt.

## Dynamische Statuswerte

Die Integration liest `eventStatus`, `effortEstimateStatus`, `internalCaseStatus` und `salesOpportunityResultStatus`. Anzeigenamen und erlaubte Werte stammen aus diesen Datensätzen; es gibt keine feste Liste von Status-Handles. Ein vorhandenes boolesches `isClosed` bestimmt den Abschluss. Sonst bedeutet `isOpen=false` abgeschlossen. Unbekannte Kennzeichen gelten nicht als Abschluss. Das ist insbesondere für Sales-Statuswerte wichtig, die beide Kennzeichen haben können.

Statuskataloge werden bei jeder Synchronisierung und beim Öffnen der CRM-Auswahlfelder neu geladen. Unmittelbar vor einer Statusänderung wird der gewählte Status erneut geprüft. Ein inzwischen als offen konfigurierter Status kann einen Abschlussvorschlag nicht mehr ausführen. Aufgaben- und Kalenderansichten zeigen den CRM-Status und bieten Offen-/Abgeschlossen-Filter.

## Synchronisierung und Grenzen

- Aktive Quellen werden alle fünf Minuten eingelesen; der Synchronisieren-Knopf startet einen sofortigen Lauf. Nach bestätigtem Schreiben wird ebenfalls ein Lauf eingeplant.
- Die Generic API wird vollständig paginiert. Erst nach erfolgreichem Laden aller Seiten werden entfernte oder nicht mehr zugeordnete Datensätze lokal ausgeblendet. Wiederholte Läufe erzeugen keine doppelten Items.
- Änderungen laufen über das CRM-Feld `updatedAt` und den atomaren Parameter `expectedUpdatedAt`. Bei einem Konflikt zuerst synchronisieren und einen neuen Vorschlag prüfen.
- Ein unklarer Schreibausgang wird als **Ergebnis unklar** markiert und niemals automatisch wiederholt. Zuerst im CRM nachsehen, bevor ein neuer Vorschlag freigegeben wird.
- Die Synchronisierung verbindet Work Agent mit CRM. Sie kopiert nicht automatisch Outlook-Kalender oder Microsoft-To-Do-Aufgaben ins CRM.
- Importierte Terminserien werden als Serien-Datensatz angezeigt, nicht in einzelne Wiederholungen aufgelöst. Serien, Teilnehmer und Einladungseinstellungen werden im CRM verwaltet. Neue CRM-Termine werden ohne Einladungsversand, Online-Meeting-Erstellung und Outlook-Freigabe erstellt. Termine, bei denen du nur Teilnehmer bist, können gelesen werden; Bearbeitung bleibt auf dir zugeordnete Termine begrenzt.
- Aufwandsschätzungspositionen, Umsatzberechnung, Kunden-/Firmenzuordnungen und andere Fachdetails bleiben im CRM. Der Work Agent bearbeitet Titel, Beschreibung, Datum und die angebotenen Klassifikations-/Statusfelder. CRM-Regeln können weitere Eingaben erfordern.

**Verbindung trennen** entfernt den Key und deaktiviert die Quellen einschließlich KI- und Schreibfreigabe. Beim Wiederverbinden mit demselben Benutzer/System bleiben Quellidentitäten erhalten; getrennte Quellen müssen wieder aktiviert werden. Ein anderes CRM-System oder ein anderer Benutzer kann nach dem Trennen verbunden werden. Dafür entstehen neue Quellen; alte Vorschläge und Importdaten werden nicht dem neuen System zugeordnet.

## Prüfstand

Automatisierte Tests prüfen Zuordnung der vier Entities, persönliche Filter, dynamische Statuswerte, Änderungen der Abschlusskennzeichen, Pagination, verschlüsselte Tokenablage, Verbindungswechsel, Konflikte und Freigabeschutz. Der lokale API-Port wurde aus Docker erfolgreich erreicht. Ein authentifizierter Test und echte CRM-Schreibaktionen stehen bis zur Einrichtung des persönlichen API-Keys noch aus.
