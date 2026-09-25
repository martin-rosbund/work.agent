import { DateTime } from "luxon";

export const labels: Record<string, string> = {
  github: "GitHub",
  github_issue: "GitHub-Issue",
  mail: "Outlook",
  chat: "Teams",
  channel: "Teams-Kanal",
  calendar: "Kalender",
  todo: "Microsoft To Do",
  drive: "OneDrive / SharePoint",
  knowledge: "Wissen",
  document: "Dokument",
  uploads: "Dokumente",
  local_tasks: "Lokale Aufgaben",
  task: "Aufgabe",
};

export const actionLabels: Record<string, string> = {
  reply_email: "E-Mail-Antwort",
  reply_teams: "Teams-Antwort",
  create_event: "Termin anlegen",
  create_task: "Aufgabe anlegen",
  update_task: "Aufgabe bearbeiten",
  complete_task: "Aufgabe abschließen",
  knowledge: "Wissen speichern",
};

export const statusLabels: Record<string, string> = {
  new: "Offen",
  in_progress: "In Arbeit",
  waiting: "Wartet",
  done: "Erledigt",
  draft: "Entwurf",
  approved: "Freigegeben",
  executing: "Wird ausgeführt",
  failed: "Fehlgeschlagen",
  unknown: "Ergebnis unklar",
  rejected: "Verworfen",
  demo_done: "Simuliert",
  pending: "Ausstehend",
  running: "Läuft",
  ready: "Bereit",
  error: "Fehler",
  unsupported: "Nicht unterstützt",
  ok: "Verbunden",
  reauth: "Anmeldung nötig",
  forbidden: "Zugriff fehlt",
  disabled: "Deaktiviert",
  rate_limited: "GitHub-Wartezeit",
};

export const fmt = (value?: string | null) =>
  value
    ? DateTime.fromISO(value, { zone: "utc" })
        .setZone("Europe/Berlin")
        .setLocale("de")
        .toLocaleString({
          day: "2-digit",
          month: "short",
          hour: "2-digit",
          minute: "2-digit",
        })
    : "—";

export const localDateTime = (value?: string | null) =>
  value
    ? DateTime.fromISO(value, { zone: "utc" })
        .setZone("Europe/Berlin")
        .toFormat("yyyy-MM-dd'T'HH:mm")
    : "";
