import { useState } from "react";
import {
  CheckCheck,
  BookOpen,
  ArrowUpRight,
  ArrowRight,
  Sparkles,
  Link2,
  RefreshCw,
  ShieldCheck,
  LoaderCircle,
  SlidersHorizontal,
} from "lucide-react";
import { api, Source, Item } from "../../api";
import { labels, statusLabels, fmt } from "../../shared/presentation";
import { useNotice } from "../../shared/notifications";
import { Icon, Button, Badge, Empty, PageHeader } from "../../shared/ui";

export function InboxPage({
  items,
  sources,
  loaded,
  open,
  chat,
  refresh,
  settings,
}: {
  items: Item[];
  sources: Source[];
  loaded: boolean;
  open: (i: Item) => void;
  chat: (i: Item) => void;
  refresh: () => void;
  settings: () => void;
}) {
  const [filter, setFilter] = useState("all"),
    [sourceFilter, setSourceFilter] = useState("all"),
    [busy, setBusy] = useState(false);
  const notice = useNotice(),
    visible = items.filter(
      (i) =>
        (filter === "all" || i.status === filter) &&
        (sourceFilter === "all" || i.source_kind === sourceFilter),
    );
  async function sync() {
    setBusy(true);
    try {
      await Promise.all(
        sources
          .filter(
            (s) => s.enabled && ["mail", "chat", "channel"].includes(s.kind),
          )
          .map((s) => api("/sources/" + s.id + "/sync", "POST")),
      );
      notice("Aktualisierung läuft im Hintergrund.");
      refresh();
    } catch (e) {
      notice((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  const pending = items.filter((i) => i.status !== "done").length;
  return (
    <>
      <PageHeader
        eyebrow="ALLES WICHTIGE AN EINEM ORT"
        title="Dein Eingang."
        description="Weniger zwischen Apps wechseln. Mehr von dem schaffen, was zählt."
        action={
          <Button onClick={sync} disabled={busy}>
            <RefreshCw size={16} className={busy ? "spin" : ""} /> Aktualisieren
          </Button>
        }
      />
      <div className="overview-strip">
        <div className="overview-main">
          <div className="sparkle-tile">
            <Sparkles size={23} />
          </div>
          <div>
            <div className="overview-kicker">DEIN ÜBERBLICK</div>
            <h2>
              {pending
                ? `${pending} offene Nachrichten. Ein klarer nächster Schritt.`
                : "Platz für einen klaren Kopf."}
            </h2>
            <p>
              {pending
                ? "Öffne einen Vorgang und entwickle mit deinem Agenten die passende Antwort."
                : "Verbinde deine Quellen. Dein Agent hilft dir, das Wichtige im Blick zu behalten."}
            </p>
          </div>
          <span className="overview-orbit">✳</span>
        </div>
        <div className="overview-stat">
          <span className="stat-value">
            {items
              .filter((i) => i.status === "new")
              .length.toString()
              .padStart(2, "0")}
          </span>
          <span>
            Noch offen <span className="tiny-dot orange" />
          </span>
        </div>
        <div className="overview-stat">
          <span className="stat-value">
            {items
              .filter((i) => i.status === "done")
              .length.toString()
              .padStart(2, "0")}
          </span>
          <span>
            Erledigt <CheckCheck size={13} />
          </span>
        </div>
      </div>
      <div className="inbox-layout">
        <section className="inbox-card">
          <div className="list-toolbar">
            <div className="tabs">
              {[
                ["all", "Alle"],
                ["new", "Offen"],
                ["in_progress", "In Arbeit"],
                ["done", "Erledigt"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  className={filter === id ? "selected" : ""}
                  onClick={() => setFilter(id)}
                >
                  {label}
                  {id === "all" && <span>{items.length}</span>}
                </button>
              ))}
            </div>
            <label className="filter-select">
              <SlidersHorizontal size={14} />
              <select
                aria-label="Nach Quelle filtern"
                value={sourceFilter}
                onChange={(e) => setSourceFilter(e.target.value)}
              >
                <option value="all">Alle Quellen</option>
                <option value="mail">Outlook</option>
                <option value="chat">Teams-Chats</option>
                <option value="channel">Teams-Kanäle</option>
              </select>
            </label>
          </div>
          <div className="list-section-label">
            NACHRICHTEN <span>Neueste zuerst</span>
          </div>
          {!loaded ? (
            <div className="loading">
              <LoaderCircle className="spin" /> Eingang wird geladen …
            </div>
          ) : (
            visible.map((item) => (
              <article
                className={
                  "message-row " + (item.status === "done" ? "muted" : "")
                }
                key={item.id}
              >
                <div className={"source-icon " + item.source_kind}>
                  <Icon kind={item.kind} />
                </div>
                <button className="message-main" onClick={() => open(item)}>
                  <div className="message-meta">
                    <strong>{item.sender || item.source_name}</strong>
                    <span>
                      {labels[item.source_kind]}
                      {item.meta?.demo ? " · Demo" : ""}
                    </span>
                  </div>
                  <h3>{item.title}</h3>
                  <p>{item.summary || item.body.slice(0, 150)}</p>
                  <div className="message-tags">
                    <Badge
                      kind={
                        item.status === "done"
                          ? "green"
                          : item.status === "new"
                            ? "orange"
                            : ""
                      }
                    >
                      {statusLabels[item.status]}
                    </Badge>
                    {item.ai_enabled && (
                      <span className="ai-note">
                        <Sparkles size={12} /> Agent verfügbar
                      </span>
                    )}
                  </div>
                </button>
                <div className="message-side">
                  <time>{fmt(item.occurred_at)}</time>
                  <button
                    className="round-arrow"
                    title="Arbeitschat öffnen"
                    onClick={() => chat(item)}
                  >
                    <ArrowUpRight size={18} />
                  </button>
                </div>
              </article>
            ))
          )}
          {loaded && !visible.length && (
            <Empty
              title={
                items.length
                  ? "Alles in diesem Bereich ist erledigt."
                  : "Dein Eingang wartet auf dich."
              }
              text={
                items.length
                  ? "Wechsle den Filter, um andere Nachrichten zu sehen."
                  : "Verbinde Outlook und Teams, um hier deine Nachrichten zu sammeln."
              }
            >
              {!items.length && (
                <Button kind="primary" onClick={settings}>
                  <Link2 size={16} /> Quellen verbinden
                </Button>
              )}
            </Empty>
          )}
          <div className="list-end">
            <span className="tiny-dot" /> {visible.length} Nachrichten im
            Arbeitsraum{" "}
            <span>
              Neueste Inhalte zuerst · Weitere Inhalte bei Bedarf nachladen
            </span>
          </div>
        </section>
        <aside className="context-rail">
          <div className="rail-card agent-card">
            <div className="rail-title">
              <span className="agent-dot">
                <Sparkles size={17} />
              </span>
              <Badge kind="green">DEIN AGENT</Badge>
            </div>
            <h3>
              Mitdenken.
              <br />
              Du entscheidest.
            </h3>
            <p>
              Aus einer Nachricht werden ein klarer Überblick, ein
              Antwortentwurf und die nächsten Schritte.
            </p>
            <div className="agent-steps">
              <div>
                <span>01</span> Nachricht verstehen
              </div>
              <div>
                <span>02</span> Dein Wissen einbeziehen
              </div>
              <div>
                <span>03</span> Gemeinsam weiterkommen
              </div>
            </div>
            <div className="rail-foot">
              <ShieldCheck size={15} /> Versand erst nach deiner Freigabe
            </div>
          </div>
          <div className="rail-card source-card">
            <div className="rail-heading">
              <h3>Deine Verbindungen</h3>
              <Link2 size={16} />
            </div>
            {sources
              .filter((s) =>
                ["mail", "chat", "channel", "drive"].includes(s.kind),
              )
              .slice(0, 4)
              .map((s) => (
                <div className="connection-row" key={s.id}>
                  <div className={"source-icon small " + s.kind}>
                    <Icon kind={s.kind} size={15} />
                  </div>
                  <div>
                    <strong>{labels[s.kind]}</strong>
                    <small>
                      {s.config.demo
                        ? "Beispieldaten"
                        : s.last_sync
                          ? "Stand " + fmt(s.last_sync)
                          : "Noch nicht synchronisiert"}
                    </small>
                  </div>
                  <span
                    className={
                      "source-dot " +
                      (!s.enabled
                        ? "gray"
                        : ["reauth", "forbidden", "error"].includes(s.status)
                          ? "orange"
                          : "")
                    }
                  />
                </div>
              ))}
            <button className="text-link" onClick={settings}>
              Verbindungen verwalten <ArrowRight size={14} />
            </button>
          </div>
          <div className="small-note">
            <BookOpen size={19} />
            <p>
              Je mehr du deinem Wissensspeicher mitgibst, desto hilfreicher
              werden deine Antworten.
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}
