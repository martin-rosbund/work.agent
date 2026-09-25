import { useState, useEffect } from "react";
import {
  Plus,
  ArrowUpRight,
  ArrowRight,
  Sparkles,
  Link2,
  RefreshCw,
  ShieldCheck,
  LoaderCircle,
  ExternalLink,
  CheckCircle2,
} from "lucide-react";
import { api, Source } from "../../api";
import { actionLabels, statusLabels, fmt } from "../../shared/presentation";
import { useNotice } from "../../shared/notifications";
import { Icon, Button, Badge, PageHeader } from "../../shared/ui";
import { SourcePicker } from "./SourcePicker";

export function SettingsPage({
  sources,
  refresh,
  revision,
}: {
  sources: Source[];
  refresh: () => void;
  revision: number;
}) {
  const [settings, setSettings] = useState<any>(null),
    [agent, setAgent] = useState<any>(null),
    [key, setKey] = useState(""),
    [ms, setMs] = useState({ tenant_id: "", client_id: "", client_secret: "" }),
    [activity, setActivity] = useState<any>(null),
    [connect, setConnect] = useState(false),
    [models, setModels] = useState<string[]>([]),
    [busy, setBusy] = useState(""),
    [tab, setTab] = useState("connections");
  const notice = useNotice();
  useEffect(() => {
    api("/settings")
      .then((s) => {
        setSettings(s);
        setAgent(s.agent);
        setMs((m) => ({
          ...m,
          tenant_id: s.microsoft.tenant_id || "",
          client_id: s.microsoft.client_id || "",
        }));
      })
      .catch((e) => notice(e.message, true));
  }, []);
  useEffect(() => {
    api("/activity")
      .then(setActivity)
      .catch((e) => notice(e.message, true));
  }, [revision]);
  async function run(id: string, fn: () => Promise<any>, message: string) {
    setBusy(id);
    try {
      const result = await fn();
      notice(message);
      refresh();
      return result;
    } catch (e) {
      notice((e as Error).message, true);
    } finally {
      setBusy("");
    }
  }
  async function authorize(kind?: string, write = false) {
    const result = await run(
      "auth",
      () => api("/microsoft/auth", "POST", { kind, write }),
      "Microsoft-Anmeldung wird geöffnet.",
    );
    if (result) location.href = result.url;
  }
  if (!settings || !agent)
    return (
      <div className="loading">
        <LoaderCircle className="spin" /> Einstellungen werden geladen …
      </div>
    );
  return (
    <>
      <PageHeader
        eyebrow="DEIN ASSISTENT. DEINE REGELN."
        title="Alles richtig verbunden."
        description="Quellen auswählen, den Agenten einrichten und jederzeit die Kontrolle behalten."
      />
      <div className="tabs standalone settings-tabs">
        {[
          ["connections", "Verbindungen"],
          ["agent", "Dein Agent"],
          ["activity", "Aktivität & Betrieb"],
        ].map(([id, name]) => (
          <button
            className={tab === id ? "selected" : ""}
            key={id}
            onClick={() => setTab(id)}
          >
            {name}
          </button>
        ))}
      </div>
      {tab === "connections" ? (
        <div className="settings-grid">
          <section className="settings-card">
            <div className="settings-title">
              <div className="source-icon mail">
                <Link2 size={21} />
              </div>
              <div>
                <h2>Microsoft 365</h2>
                <p>Ein Konto. Alle wichtigen Arbeitsquellen.</p>
              </div>
              <Badge kind={settings.account.name ? "green" : ""}>
                {settings.account.name ? "Verbunden" : "Einrichten"}
              </Badge>
            </div>
            <details
              className="help-details"
              open={!settings.microsoft_configured}
            >
              <summary>So richtest du die Microsoft-App ein</summary>
              <ol>
                <li>
                  In Microsoft Entra eine App registrieren: nur Konten deiner
                  Organisation.
                </li>
                <li>
                  Unter „Authentifizierung“ eine Web-Plattform mit dieser
                  Redirect-URI hinzufügen:<code>{settings.redirect_uri}</code>
                </li>
                <li>
                  Unter „Zertifikate & Geheimnisse“ ein Client-Secret erstellen
                  und den Wert unten eintragen.
                </li>
                <li>
                  Speichern, eine Quelle auswählen und die angeforderten
                  delegierten Rechte erlauben. Je nach Firmenrichtlinie ist die
                  Zustimmung deiner IT nötig.
                </li>
              </ol>
              <a
                href="https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app"
                target="_blank"
                rel="noreferrer"
              >
                Microsoft-Anleitung öffnen <ExternalLink size={12} />
              </a>
            </details>
            <label>
              Tenant-ID
              <input
                value={ms.tenant_id}
                onChange={(e) => setMs({ ...ms, tenant_id: e.target.value })}
                placeholder="Verzeichnis-ID deiner Organisation"
              />
            </label>
            <label>
              Client-ID
              <input
                value={ms.client_id}
                onChange={(e) => setMs({ ...ms, client_id: e.target.value })}
                placeholder="Anwendungs-ID"
              />
            </label>
            <label>
              Client-Secret
              <input
                type="password"
                autoComplete="new-password"
                value={ms.client_secret}
                onChange={(e) =>
                  setMs({ ...ms, client_secret: e.target.value })
                }
                placeholder={
                  settings.microsoft_configured
                    ? "Gespeichert · leer lassen, um es zu behalten"
                    : "Wert des Client-Secrets"
                }
              />
            </label>
            <div className="row wrap">
              <Button
                disabled={busy === "ms"}
                onClick={async () => {
                  const result = await run(
                    "ms",
                    () => api("/settings/microsoft", "PUT", ms),
                    "Microsoft-App gespeichert.",
                  );
                  if (result) {
                    setMs({ ...ms, client_secret: "" });
                    setSettings({ ...settings, microsoft_configured: true });
                  }
                }}
              >
                App speichern
              </Button>
              <Button
                kind="primary"
                onClick={() => authorize()}
                disabled={!settings.microsoft_configured || busy === "auth"}
              >
                Mit Microsoft anmelden <ArrowUpRight size={15} />
              </Button>
              <Button
                onClick={() =>
                  run(
                    "mstest",
                    () => api("/microsoft/test", "POST"),
                    "Microsoft-Verbindung funktioniert.",
                  )
                }
                disabled={!settings.account.name}
              >
                Verbindung testen
              </Button>
            </div>
            {settings.account.name && (
              <p className="connected-account">
                <CheckCircle2 size={15} />
                {settings.account.name} · {settings.account.username}
              </p>
            )}
          </section>
          <section className="settings-card">
            <div className="settings-title">
              <div className="source-icon knowledge">
                <Sparkles size={21} />
              </div>
              <div>
                <h2>OpenAI</h2>
                <p>Dein erster KI-Anbieter.</p>
              </div>
              <Badge kind={settings.openai_configured ? "green" : ""}>
                {settings.openai_configured ? "Konfiguriert" : "Einrichten"}
              </Badge>
            </div>
            <p className="settings-copy">
              Deine Chats und dein Wissen werden hier gespeichert. Für
              KI-Antworten werden freigegebene Textausschnitte an die OpenAI API
              übergeben.
            </p>
            <label>
              API-Schlüssel
              <input
                type="password"
                autoComplete="new-password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder={
                  settings.openai_configured
                    ? "Schlüssel ist verschlüsselt gespeichert"
                    : "sk-…"
                }
              />
            </label>
            <Button
              kind="primary"
              disabled={!key || busy === "key"}
              onClick={async () => {
                const result = await run(
                  "key",
                  () => api("/settings/openai", "PUT", { api_key: key }),
                  "OpenAI-Schlüssel gespeichert.",
                );
                if (result) {
                  setKey("");
                  setSettings({ ...settings, openai_configured: true });
                }
              }}
            >
              Schlüssel speichern
            </Button>
            <div className="info-box">
              <ShieldCheck size={18} />
              <p>
                Du erlaubst KI-Verarbeitung für jede Quelle einzeln. Lokale OCR
                benötigt keinen Cloud-Dienst. <code>store: false</code>{" "}
                deaktiviert die Responses-Speicherung, ist aber keine Zusage
                über sämtliche Protokolldaten des Anbieters.
              </p>
            </div>
            <a
              className="text-link"
              href="https://developers.openai.com/api/docs/guides/your-data"
              target="_blank"
              rel="noreferrer"
            >
              Datenverarbeitung bei OpenAI <ExternalLink size={13} />
            </a>
            <div className="settings-divider" />
            <h3>Danach: Modell auswählen</h3>
            <p className="settings-copy">
              Im Bereich „Dein Agent“ wählst du Text- und Embedding-Modell aus
              und prüfst die Verbindung.
            </p>
            <Button onClick={() => setTab("agent")}>
              Agent einrichten <ArrowRight size={15} />
            </Button>
          </section>
          <section className="settings-card full-width">
            <div className="section-heading">
              <div>
                <h2>Deine Quellen</h2>
                <p className="muted-text">
                  Nur aktivierte Quellen werden synchronisiert. KI-Freigabe gilt
                  auch für Embeddings und den Chatkontext.
                </p>
              </div>
              <Button
                kind="primary"
                disabled={!settings.microsoft_configured}
                onClick={() => setConnect(true)}
              >
                <Plus size={16} /> Quelle hinzufügen
              </Button>
            </div>
            <div className="source-table">
              <div className="source-table-head">
                <span>QUELLE</span>
                <span>AKTIV</span>
                <span>KI ERLAUBT</span>
                <span>SCHREIBEN</span>
                <span />
              </div>
              {sources.map((s) => (
                <div className="source-table-row" key={s.id}>
                  <div className="source-description">
                    <div className={"source-icon small " + s.kind}>
                      <Icon kind={s.kind} size={16} />
                    </div>
                    <div>
                      <strong>{s.name}</strong>
                      <small>
                        {s.error || statusLabels[s.status] || s.status}
                        {s.config.demo ? " · Demo" : ""}
                      </small>
                      {["mail", "chat", "channel"].includes(s.kind) &&
                        !s.config.demo && (
                          <label className="days-label">
                            Importtage{" "}
                            <input
                              type="number"
                              min="1"
                              max="3650"
                              defaultValue={s.config.days || 90}
                              onBlur={(e) =>
                                run(
                                  "source",
                                  () =>
                                    api("/sources/" + s.id, "PATCH", {
                                      days: Number(e.target.value),
                                    }),
                                  "Importzeitraum gespeichert.",
                                )
                              }
                            />
                          </label>
                        )}
                    </div>
                  </div>
                  {(["enabled", "ai_enabled", "writable"] as const).map(
                    (field) => (
                      <label key={field} className="switch">
                        <input
                          aria-label={`${s.name}: ${field === "enabled" ? "Aktiv" : field === "ai_enabled" ? "KI erlauben" : "Schreiben erlauben"}`}
                          type="checkbox"
                          checked={s[field]}
                          disabled={
                            field === "writable" &&
                            ![
                              "mail",
                              "chat",
                              "channel",
                              "calendar",
                              "todo",
                            ].includes(s.kind)
                          }
                          onChange={(e) =>
                            run(
                              "source",
                              () =>
                                api("/sources/" + s.id, "PATCH", {
                                  [field]: e.target.checked,
                                }),
                              "Quelle aktualisiert.",
                            )
                          }
                        />
                        <span />
                      </label>
                    ),
                  )}
                  <div className="row">
                    {!["knowledge", "uploads", "local_tasks", "github"].includes(
                      s.kind,
                    ) &&
                      !s.config.demo && (
                        <>
                          <button
                            className="icon-button"
                            title="Berechtigungen aktualisieren"
                            aria-label="Berechtigungen aktualisieren"
                            onClick={() => authorize(s.kind, s.writable)}
                          >
                            <ShieldCheck size={16} />
                          </button>
                          <button
                            className="icon-button"
                            title="Quelle synchronisieren"
                            aria-label="Quelle synchronisieren"
                            onClick={() =>
                              run(
                                "sync",
                                () => api("/sources/" + s.id + "/sync", "POST"),
                                "Synchronisierung gestartet.",
                              )
                            }
                          >
                            <RefreshCw size={16} />
                          </button>
                        </>
                      )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        </div>
      ) : tab === "agent" ? (
        <div className="settings-grid">
          <section className="settings-card">
            <h2>Wie dein Agent arbeitet</h2>
            <p className="settings-copy">
              Ein Profil für deine Arbeitsweise. Quellenrechte und Freigaben
              werden unabhängig davon durch die Anwendung durchgesetzt.
            </p>
            <label>
              Arbeitsanweisungen
              <textarea
                rows={6}
                value={agent.instructions}
                onChange={(e) =>
                  setAgent({ ...agent, instructions: e.target.value })
                }
              />
            </label>
            <label>
              Antwortstil
              <textarea
                rows={3}
                value={agent.style}
                onChange={(e) => setAgent({ ...agent, style: e.target.value })}
              />
            </label>
            <h3>Erlaubte Vorschläge</h3>
            <div className="action-checks">
              {Object.entries(actionLabels).map(([id, label]) => (
                <label className="check-label" key={id}>
                  <input
                    type="checkbox"
                    checked={agent.allowed_actions.includes(id)}
                    onChange={(e) =>
                      setAgent({
                        ...agent,
                        allowed_actions: e.target.checked
                          ? [...agent.allowed_actions, id]
                          : agent.allowed_actions.filter(
                              (x: string) => x !== id,
                            ),
                      })
                    }
                  />
                  {label}
                </label>
              ))}
            </div>
          </section>
          <section className="settings-card">
            <div className="section-heading">
              <h2>Modelle & Verarbeitung</h2>
              <Button
                disabled={!settings.openai_configured}
                onClick={async () => {
                  const result = await run(
                    "models",
                    () => api("/openai/models"),
                    "Verfügbare Modelle geladen.",
                  );
                  if (result) setModels(result);
                }}
              >
                <RefreshCw size={14} /> Modelle laden
              </Button>
            </div>
            <label>
              Textmodell (Responses API)
              <input
                list="models"
                value={agent.model}
                onChange={(e) => setAgent({ ...agent, model: e.target.value })}
                placeholder="Modellname aus deinem API-Konto"
              />
            </label>
            <datalist id="models">
              {models.map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
            <label>
              Embedding-Modell
              <input
                list="embedding-models"
                value={agent.embedding_model}
                onChange={(e) =>
                  setAgent({ ...agent, embedding_model: e.target.value })
                }
              />
            </label>
            <datalist id="embedding-models">
              {models
                .filter((m) => m.includes("embedding"))
                .map((m) => (
                  <option key={m} value={m} />
                ))}
            </datalist>
            <p className="field-help">
              Ein Wechsel des Embedding-Modells baut den semantischen Index neu
              auf. Die Volltextsuche bleibt verfügbar.
            </p>
            <label>
              Hintergrundaufrufe pro Tag
              <input
                type="number"
                min={1}
                max={10000}
                value={agent.daily_limit}
                onChange={(e) =>
                  setAgent({ ...agent, daily_limit: Number(e.target.value) })
                }
              />
            </label>
            <p className="field-help">
              Enthält Analyse und Embeddings. Zählung ab Mitternacht
              Europe/Berlin; kein Kostenlimit in Euro.
            </p>
            <label className="check-label">
              <input
                type="checkbox"
                checked={agent.paused}
                onChange={(e) =>
                  setAgent({ ...agent, paused: e.target.checked })
                }
              />
              <span>
                KI-Verarbeitung pausieren
                <small>
                  Synchronisierung und lokale Dokumentverarbeitung laufen
                  weiter.
                </small>
              </span>
            </label>
            <div className="modal-actions">
              <Button
                disabled={!settings.openai_configured || !!busy}
                onClick={() =>
                  run(
                    "test",
                    async () => {
                      await api("/settings/agent", "PUT", agent);
                      return api("/openai/test", "POST");
                    },
                    "Text- und Embedding-Modell funktionieren. Der Test enthielt keine Arbeitsdaten.",
                  )
                }
              >
                Speichern & Modelle testen
              </Button>
              <Button
                kind="primary"
                onClick={() =>
                  run(
                    "agent",
                    () => api("/settings/agent", "PUT", agent),
                    "Agentenprofil gespeichert.",
                  )
                }
              >
                Profil speichern
              </Button>
            </div>
          </section>
        </div>
      ) : (
        <>
          <div className="usage-grid">
            {[
              ["API-Aufrufe", activity?.usage.calls || 0],
              ["Eingabe-Tokens", activity?.usage.input_tokens || 0],
              ["Ausgabe-Tokens", activity?.usage.output_tokens || 0],
            ].map(([label, value]) => (
              <div className="usage-card" key={label}>
                <span>{label}</span>
                <strong>{Number(value).toLocaleString("de-DE")}</strong>
                <small>Seit Einrichtung · ohne Verbindungstests</small>
              </div>
            ))}
          </div>
          <div className="settings-grid">
            <section className="settings-card">
              <h2>Hintergrundverarbeitung</h2>
              <p className="settings-copy">
                Letztes Lebenszeichen: {fmt(activity?.worker?.heartbeat)}.
                Verarbeitung läuft bei geschlossenem Browser weiter, solange
                Docker und der Rechner laufen.
              </p>
              <Button
                onClick={() =>
                  run(
                    "reindex",
                    () => api("/knowledge/reindex/all", "POST"),
                    "Neuaufbau der Suchindizes gestartet.",
                  )
                }
              >
                <RefreshCw size={15} /> Wissen neu indexieren
              </Button>
              <div className="activity-list">
                {activity?.jobs?.slice(0, 20).map((j: any) => (
                  <div key={j.id}>
                    <span>
                      <strong>
                        {(
                          {
                            sync: "Synchronisieren",
                            extract: "Dokument lesen",
                            embed: "Semantisch indexieren",
                            chat: "Chatantwort",
                            analyze: "Analysieren",
                            execute: "Aktion ausführen",
                            export: "Markdown speichern",
                          } as any
                        )[j.kind] || j.kind}
                      </strong>
                      <small>{j.error || fmt(j.created_at)}</small>
                    </span>
                    <Badge
                      kind={
                        j.status === "failed"
                          ? "orange"
                          : j.status === "done"
                            ? "green"
                            : ""
                      }
                    >
                      {statusLabels[j.status]}
                    </Badge>
                  </div>
                ))}
              </div>
            </section>
            <section className="settings-card">
              <h2>Datensicherung & Updates</h2>
              <p className="settings-copy">
                Die mitgelieferten PowerShell-Skripte sichern Datenbank,
                Originaldokumente und Markdown-Dateien konsistent. Schlüssel
                werden separat gesichert.
              </p>
              <div className="command-line">.\scripts\backup.ps1</div>
              <div className="command-line">
                .\scripts\restore.ps1 -BackupPath &lt;Ordner&gt;
              </div>
              <div className="command-line">.\scripts\update.ps1</div>
              <div className="info-box">
                <ShieldCheck size={18} />
                <p>
                  Dokumente und Suchdaten sind auf deinem Datenträger lesbar.
                  Verwende Laufwerksverschlüsselung zum Schutz bei
                  Geräteverlust. Bewahre Backups und die separaten Schlüssel
                  geschützt auf.
                </p>
              </div>
              <h3>Aktionsprotokoll</h3>
              <div className="activity-list">
                {activity?.audit
                  ?.filter((a: any) => a.action.startsWith("action."))
                  .slice(0, 15)
                  .map((a: any) => (
                    <div key={a.id}>
                      <span>
                        <strong>{a.action}</strong>
                        <small>
                          {fmt(a.created_at)} ·{" "}
                          {a.detail.proposal_id?.slice(0, 8)}
                        </small>
                      </span>
                      <ShieldCheck size={15} />
                    </div>
                  ))}
              </div>
            </section>
          </div>
        </>
      )}
      {connect && (
        <SourcePicker
          close={() => setConnect(false)}
          saved={refresh}
          authorize={authorize}
        />
      )}
    </>
  );
}
