import { useState, useEffect } from "react";
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
  async function load(parent?: string, siteUrl?: string) {
    setBusy(true);
    setError("");
    try {
      setRows(
        await api(
          "/microsoft/discover/" +
            kind +
            "?" +
            new URLSearchParams({
              ...(parent ? { parent } : {}),
              ...(siteUrl ? { site_url: siteUrl } : {}),
            }),
        ),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
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
    if (!selected) return;
    let config: any = { days: 90 };
    if (kind === "mail") config.folder_id = selected.id;
    if (kind === "chat") config.chat_id = selected.id;
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
      <div className="row wrap">
        <Button
          onClick={() => {
            setPath([]);
            setDrive(null);
            setSelected(null);
            load();
          }}
          disabled={busy}
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
      <div className="picker-list">
        {rows.map((row) => (
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
      {selected && (
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
        <Button kind="primary" disabled={!selected || !name} onClick={save}>
          Quelle verbinden <ArrowRight size={16} />
        </Button>
      </div>
    </Modal>
  );
}
