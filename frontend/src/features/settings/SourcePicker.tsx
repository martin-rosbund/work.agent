import { useState, useEffect, useRef } from "react";
import {
  ArrowRight,
  ArrowLeft,
  ChevronRight,
  RefreshCw,
  Check,
  ShieldCheck,
  Folder,
  AlertCircle,
} from "lucide-react";
import { api } from "../../api";
import { labels } from "../../shared/presentation";
import { useNotice } from "../../shared/notifications";
import { Icon, Button, Modal } from "../../shared/ui";

export function SourcePicker({
  close,
  saved,
  authorize,
}: {
  close: () => void;
  saved: () => void;
  authorize: (kind?: string, write?: boolean) => void;
}) {
  const [kind, setKind] = useState("mail"),
    [rows, setRows] = useState<any[]>([]),
    [path, setPath] = useState<{ id: string; name: string }[]>([]),
    [site, setSite] = useState(""),
    [drive, setDrive] = useState<any>(null),
    [selected, setSelected] = useState<any>(null),
    [name, setName] = useState(""),
    [aiConsent, setAiConsent] = useState(false),
    [write, setWrite] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const notice = useNotice();
  const [search, setSearch] = useState("");
  const [allDirect, setAllDirect] = useState(false);
  const requestId = useRef(0);
  useEffect(
    () => () => {
      requestId.current += 1;
    },
    [],
  );
  async function load(parent?: string, siteUrl?: string) {
    const current = ++requestId.current;
    setBusy(true);
    setError("");
    setSearch("");
    try {
      if (kind === "chat") {
        setRows([]);
        let continuation: string | null = null;
        const found = new Map<string, any>();
        do {
          const page: { items: any[]; continuation: string | null } = await api(
            "/microsoft/chats/page" +
              (continuation ? "?" + new URLSearchParams({ continuation }) : ""),
          );
          if (current !== requestId.current) return;
          page.items.forEach((row) => found.set(row.id, row));
          setRows([...found.values()]);
          continuation = page.continuation;
        } while (continuation);
      } else {
        const result = await api(
          "/microsoft/discover/" +
            kind +
            "?" +
            new URLSearchParams({
              ...(parent ? { parent } : {}),
              ...(siteUrl ? { site_url: siteUrl } : {}),
            }),
        );
        if (current === requestId.current) setRows(result);
      }
    } catch (e) {
      if (current === requestId.current) setError((e as Error).message);
    } finally {
      if (current === requestId.current) setBusy(false);
    }
  }
  useEffect(() => {
    requestId.current += 1;
    setBusy(false);
    setSearch("");
    setAllDirect(false);
    setRows([]);
    setPath([]);
    setDrive(null);
    setSelected(null);
    setName("");
  }, [kind]);
  function choose(row: any) {
    setSelected(row);
    setName(row.displayName || row.name || row.topic || "Teams-Unterhaltung");
  }
  async function enter(row: any) {
    setSelected(null);
    setName("");
    if (kind === "drive" && !drive) {
      setDrive(row);
      setPath([{ id: "root", name: row.name || "Dokumente" }]);
      await load(row.id + "|root");
    } else {
      const next = [
        ...path,
        { id: row.id, name: row.displayName || row.name || "Ordner" },
      ];
      setPath(next);
      await load(kind === "drive" ? drive.id + "|" + row.id : row.id);
    }
  }
  async function save() {
    if (!selected && !allDirect) return;
    let config: any = { days: 90 };
    if (kind === "mail") config.folder_id = selected.id;
    if (kind === "chat") {
      if (allDirect) config.mode = "all_direct_incoming";
      else config.chat_id = selected.id;
    }
    if (kind === "calendar") config.calendar_id = selected.id;
    if (kind === "todo") config.list_id = selected.id;
    if (kind === "channel") {
      config.team_id = path[0]?.id;
      config.channel_id = selected.id;
    }
    if (kind === "drive") {
      config.drive_id = drive.id;
      config.folder_id = selected.id;
    }
    try {
      await api("/sources", "POST", {
        kind,
        name,
        config,
        ai_enabled: aiConsent,
        writable: write,
      });
      saved();
      close();
      notice(
        write
          ? "Quelle verbunden. Falls nötig, Schreibrechte über das Schild-Symbol freigeben."
          : "Quelle verbunden. Der Erstimport startet im Hintergrund.",
      );
    } catch (e) {
      notice((e as Error).message, true);
    }
  }
  return (
    <Modal title="Eine Arbeitsquelle verbinden" onClose={close} wide>
      <label>
        Microsoft-Bereich
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          {["mail", "chat", "channel", "calendar", "todo", "drive"].map((k) => (
            <option key={k} value={k}>
              {labels[k]}
            </option>
          ))}
        </select>
      </label>
      {kind === "chat" && (
        <label className="check-label">
          <input
            type="checkbox"
            checked={allDirect}
            onChange={(event) => {
              const checked = event.target.checked;
              setAllDirect(checked);
              setSelected(null);
              setName(
                checked ? "Alle eingehenden Teams-Direktnachrichten" : "",
              );
              requestId.current += 1;
              setBusy(false);
            }}
          />
          <span>
            Alle eingehenden Direktnachrichten
            <small>
              Nachrichten anderer Personen in allen 1:1-Chats, auch von neuen
              Kontakten. Eigene Nachrichten, Gruppenchats und Besprechungen sind
              ausgeschlossen. Eine Kontaktauswahl ist nicht nötig.
            </small>
          </span>
        </label>
      )}
      <div className="row wrap">
        <Button
          onClick={() => {
            setPath([]);
            setDrive(null);
            setSelected(null);
            load();
          }}
          disabled={busy || allDirect}
        >
          <RefreshCw size={15} className={busy ? "spin" : ""} /> Quellen laden
        </Button>
        <Button onClick={() => authorize(kind, write)}>
          <ShieldCheck size={15} /> Berechtigung erteilen
        </Button>
      </div>
      {kind === "drive" && (
        <div className="site-input">
          <label>
            SharePoint-Site (optional)
            <input
              value={site}
              onChange={(e) => setSite(e.target.value)}
              placeholder="https://firma.sharepoint.com/sites/projekt"
            />
          </label>
          <Button
            onClick={() => {
              setDrive(null);
              setPath([]);
              setSelected(null);
              load(undefined, site);
            }}
            disabled={!site}
          >
            Bibliotheken laden
          </Button>
        </div>
      )}
      {error && (
        <div className="error-inline">
          <AlertCircle size={16} />
          {error}
        </div>
      )}
      {path.length > 0 && (
        <div className="picker-path">
          <Button
            onClick={() => {
              setPath([]);
              setDrive(null);
              setSelected(null);
              load();
            }}
          >
            <ArrowLeft size={14} /> Zur Auswahl
          </Button>
          {path.map((p) => (
            <span key={p.id}>
              {p.name}
              <ChevronRight size={12} />
            </span>
          ))}
        </div>
      )}
      {!allDirect && (
        <>
          <label>
            {kind === "chat"
              ? "Personen oder Chats suchen"
              : "Quellen durchsuchen"}
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Name eingeben …"
            />
          </label>
          <p className="muted-text" role="status">
            {rows.length} Quellen geladen
            {busy
              ? " · Weitere werden geladen … Du kannst bereits suchen und auswählen."
              : ""}
          </p>
          <div className="picker-list">
            {rows
              .filter((row) =>
                [
                  row.displayName,
                  row.name,
                  row.topic,
                  ...(row.participants || []),
                ]
                  .filter(Boolean)
                  .join(" ")
                  .toLocaleLowerCase()
                  .includes(search.trim().toLocaleLowerCase()),
              )
              .map((row) => (
                <div
                  key={row.id}
                  className={
                    "picker-row " + (selected?.id === row.id ? "selected" : "")
                  }
                >
                  <button
                    disabled={kind === "drive" && !!drive && !row.folder}
                    onClick={() => {
                      if (
                        (kind === "channel" && !path.length) ||
                        (kind === "drive" && !drive)
                      )
                        enter(row);
                      else choose(row);
                    }}
                  >
                    <Icon kind={kind === "drive" ? "document" : kind} />
                    <span>
                      {row.displayName ||
                        row.name ||
                        row.topic ||
                        `${row.chatType === "oneOnOne" ? "Einzelchat" : "Gruppenchat"} · ${row.id.slice(-12)}`}
                    </span>
                    {selected?.id === row.id && <Check size={16} />}
                  </button>
                  {((kind === "mail" && row.childFolderCount > 0) ||
                    (kind === "drive" && row.folder)) && (
                    <button
                      className="icon-button"
                      title="Ordner öffnen"
                      onClick={() => enter(row)}
                    >
                      <ChevronRight size={17} />
                    </button>
                  )}
                </div>
              ))}
          </div>
        </>
      )}
      {kind === "drive" && drive && path.length > 0 && (
        <Button
          onClick={() =>
            choose({
              id: path[path.length - 1].id,
              name: path[path.length - 1].name,
            })
          }
        >
          <Folder size={15} /> Diesen Ordner einschließlich Unterordner
          auswählen
        </Button>
      )}
      {(selected || allDirect) && (
        <div className="source-options">
          <label>
            Name im Arbeitsraum
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="check-label">
            <input
              type="checkbox"
              checked={aiConsent}
              onChange={(e) => setAiConsent(e.target.checked)}
            />
            <span>
              KI-Verarbeitung für diese Quelle erlauben
              <small>
                Textausschnitte werden für Analyse, Antworten und Embeddings an
                OpenAI gesendet.
              </small>
            </span>
          </label>
          {kind !== "drive" && (
            <label className="check-label">
              <input
                type="checkbox"
                checked={write}
                onChange={(e) => setWrite(e.target.checked)}
              />
              <span>
                Aktionen nach meiner Freigabe erlauben
                <small>
                  Zusätzliche Microsoft-Schreibrechte werden benötigt.
                </small>
              </span>
            </label>
          )}
        </div>
      )}
      <div className="modal-actions">
        <span className="muted-text">Nachrichten: zunächst letzte 90 Tage</span>
        <Button
          kind="primary"
          disabled={(!selected && !allDirect) || !name}
          onClick={save}
        >
          Quelle verbinden <ArrowRight size={16} />
        </Button>
      </div>
    </Modal>
  );
}
