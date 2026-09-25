import { useState, useRef } from "react";
import {
  BookOpen,
  Plus,
  ArrowUpRight,
  Sparkles,
  Upload,
  Check,
  ShieldCheck,
  LoaderCircle,
  History,
} from "lucide-react";
import { api, Source, Item } from "../../api";
import { statusLabels, fmt } from "../../shared/presentation";
import { useNotice } from "../../shared/notifications";
import {
  Icon,
  Button,
  Badge,
  Empty,
  Markdown,
  Modal,
  PageHeader,
} from "../../shared/ui";

export function KnowledgePage({
  items,
  sources,
  refresh,
  open,
}: {
  items: Item[];
  sources: Source[];
  refresh: () => void;
  open: (i: Item) => void;
}) {
  const [note, setNote] = useState<Partial<Item> | null>(null),
    [versions, setVersions] = useState<any[] | null>(null),
    [uploading, setUploading] = useState(false),
    [tab, setTab] = useState("all");
  const notice = useNotice(),
    file = useRef<HTMLInputElement>(null);
  async function upload(files: FileList | null) {
    if (!files) return;
    setUploading(true);
    try {
      for (const file of Array.from(files)) {
        const body = new FormData();
        body.append("file", file);
        await api("/documents", "POST", body);
      }
      refresh();
      notice(
        "Dokumente hinzugefügt. Die Verarbeitung läuft lokal im Hintergrund.",
      );
    } catch (e) {
      notice((e as Error).message, true);
    } finally {
      setUploading(false);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="DEIN WISSEN WÄCHST MIT DIR"
        title="Dein zweites Gedächtnis."
        description="Dokumente, Erfahrungen und Entscheidungen. Wiederfinden, was du schon weißt."
        action={
          <div className="row">
            <Button onClick={() => file.current?.click()} disabled={uploading}>
              {uploading ? (
                <LoaderCircle size={16} className="spin" />
              ) : (
                <Upload size={16} />
              )}{" "}
              Dokumente hinzufügen
            </Button>
            <Button
              kind="primary"
              onClick={() => setNote({ title: "", body: "" })}
            >
              <Plus size={16} /> Neue Notiz
            </Button>
          </div>
        }
      />
      <input
        type="file"
        hidden
        ref={file}
        multiple
        accept=".md,.txt,.pdf,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.tif,.tiff"
        onChange={(e) => {
          upload(e.target.files);
          e.target.value = "";
        }}
      />
      <div className="knowledge-banner">
        <div className="sparkle-tile">
          <BookOpen size={23} />
        </div>
        <div>
          <h3>Dein Wissen. Deine Handschrift.</h3>
          <p>
            Dein Agent schlägt neue Erkenntnisse vor. Du entscheidest, was
            dauerhaft bleibt.
          </p>
        </div>
        <Badge kind="green">
          {items.filter((i) => i.kind === "knowledge").length} Notizen ·{" "}
          {items.filter((i) => i.kind === "document").length} Dokumente
        </Badge>
      </div>
      <div className="tabs standalone">
        {[
          ["all", "Alles"],
          ["knowledge", "Meine Notizen"],
          ["document", "Dokumente"],
        ].map(([id, label]) => (
          <button
            key={id}
            className={tab === id ? "selected" : ""}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="knowledge-grid">
        {items
          .filter((i) => tab === "all" || i.kind === tab)
          .map((item) => (
            <article className="knowledge-card" key={item.id}>
              <div className="knowledge-card-top">
                <div
                  className={
                    "source-icon " +
                    (item.kind === "knowledge" ? "knowledge" : "document")
                  }
                >
                  <Icon kind={item.kind} />
                </div>
                <Badge kind={item.processing === "ready" ? "green" : "orange"}>
                  {item.kind === "knowledge"
                    ? "Markdown · v" + item.version
                    : statusLabels[item.processing]}
                </Badge>
              </div>
              <button
                className="knowledge-card-body"
                onClick={() =>
                  item.kind === "knowledge" ? setNote(item) : open(item)
                }
              >
                <h3>{item.title}</h3>
                <p>
                  {item.processing_error ||
                    item.body.replace(/[#*\n]/g, " ").slice(0, 180) ||
                    "Wird für deinen Wissensspeicher aufbereitet …"}
                </p>
              </button>
              <div className="knowledge-card-bottom">
                <span>
                  {item.ai_enabled ? (
                    <>
                      <Sparkles size={12} /> Für den Agenten freigegeben
                    </>
                  ) : (
                    <>
                      <ShieldCheck size={12} /> Nur lokal
                    </>
                  )}
                </span>
                {item.kind === "knowledge" ? (
                  <button
                    className="icon-button"
                    aria-label={"Versionen: " + item.title}
                    onClick={async () => {
                      setNote(item);
                      setVersions(
                        await api("/knowledge/" + item.id + "/versions"),
                      );
                    }}
                  >
                    <History size={16} />
                  </button>
                ) : (
                  <button
                    className="icon-button"
                    onClick={() => open(item)}
                    aria-label="Dokument öffnen"
                  >
                    <ArrowUpRight size={17} />
                  </button>
                )}
              </div>
            </article>
          ))}
      </div>
      {!items.length && (
        <Empty
          icon={<BookOpen />}
          title="Hier entsteht dein Arbeitswissen"
          text="Beginne mit einer Notiz oder lade ein Dokument hoch. Dein Wissen bleibt exportierbar und unabhängig vom KI-Anbieter."
        />
      )}
      {note && (
        <Modal
          title={note.id ? "Notiz bearbeiten" : "Eine neue Notiz"}
          onClose={() => {
            setNote(null);
            setVersions(null);
          }}
          wide
        >
          {versions ? (
            <>
              <p className="muted-text">
                Eine frühere Fassung wird als neue Version wiederhergestellt.
                Die Historie bleibt erhalten.
              </p>
              {versions.map((v) => (
                <div className="version-row" key={v.id}>
                  <div>
                    <strong>
                      Version {v.version} · {v.title}
                    </strong>
                    <small>{fmt(v.created_at)}</small>
                    <details>
                      <summary>Inhalt anzeigen</summary>
                      <Markdown text={v.content} />
                    </details>
                  </div>
                  <Button
                    disabled={v.version === note.version}
                    onClick={async () => {
                      try {
                        await api(
                          "/knowledge/" + note.id + "/restore",
                          "POST",
                          {
                            version: v.version,
                            expected_version: note.version,
                          },
                        );
                        setNote(null);
                        setVersions(null);
                        refresh();
                        notice("Frühere Fassung als neue Version gespeichert.");
                      } catch (e) {
                        notice((e as Error).message, true);
                      }
                    }}
                  >
                    Wiederherstellen
                  </Button>
                </div>
              ))}
              <Button onClick={() => setVersions(null)}>
                Zurück zum Editor
              </Button>
            </>
          ) : (
            <>
              <label>
                Titel
                <input
                  value={note.title || ""}
                  onChange={(e) => setNote({ ...note, title: e.target.value })}
                />
              </label>
              <label>
                Deine Notiz · Markdown
                <textarea
                  className="note-editor"
                  rows={13}
                  value={note.body || ""}
                  onChange={(e) => setNote({ ...note, body: e.target.value })}
                  placeholder="# Was ich festhalten möchte …"
                />
              </label>
              {(note.meta?.citations?.length ?? 0) > 0 && (
                <div className="muted-text">
                  {note.meta?.citations?.map((citation: any, index: number) => (
                    <div key={index}>
                      {citation.title || "Quelle"} ·{" "}
                      {citation.locator || "Original"}
                      {citation.available === false
                        ? " · Nicht mehr verfügbar"
                        : " · Quelle verfügbar"}
                    </div>
                  ))}
                </div>
              )}
              <div className="modal-actions">
                <div>
                  {note.id && (
                    <Button
                      onClick={async () =>
                        setVersions(
                          await api("/knowledge/" + note.id + "/versions"),
                        )
                      }
                    >
                      <History size={15} /> Versionen
                    </Button>
                  )}
                </div>
                <Button
                  kind="primary"
                  disabled={!note.title?.trim()}
                  onClick={async () => {
                    try {
                      await api(
                        note.id ? "/knowledge/" + note.id : "/knowledge",
                        note.id ? "PUT" : "POST",
                        {
                          title: note.title,
                          content: note.body || "",
                          expected_version: note.version,
                        },
                      );
                      setNote(null);
                      refresh();
                      notice(
                        "Notiz gespeichert. Markdown-Datei wird aktualisiert.",
                      );
                    } catch (e) {
                      notice((e as Error).message, true);
                    }
                  }}
                >
                  <Check size={15} /> Notiz speichern
                </Button>
              </div>
            </>
          )}
        </Modal>
      )}
    </>
  );
}
