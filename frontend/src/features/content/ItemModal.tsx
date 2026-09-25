import { Sparkles, ExternalLink, Download } from "lucide-react";
import { api, Item } from "../../api";
import { statusLabels, fmt } from "../../shared/presentation";
import { useNotice } from "../../shared/notifications";
import { Icon, Button, Badge, Markdown, Modal } from "../../shared/ui";

export function ItemModal({
  item,
  onClose,
  onChat,
  refresh,
}: {
  item: Item;
  onClose: () => void;
  onChat: () => void;
  refresh: () => void;
}) {
  const notice = useNotice();
  return (
    <Modal title={item.title} onClose={onClose} wide>
      <div className="item-meta">
        <Badge>
          <Icon kind={item.kind} size={13} />
          {item.source_name}
        </Badge>
        <span>{item.sender}</span>
        <time>{fmt(item.occurred_at)}</time>
      </div>
      {item.meta?.demo && (
        <div className="demo-banner">
          Beispieldaten · Keine echte Microsoft-Nachricht
        </div>
      )}
      {item.summary && (
        <div className="summary-box">
          <Sparkles size={16} />
          <p>{item.summary}</p>
        </div>
      )}
      <div className="original-content">
        {item.focus && (
          <section className="citation-focus">
            <strong>
              {item.focus.locator} · Version {item.focus.version}
            </strong>
            <p>{item.focus.text}</p>
          </section>
        )}
        {item.kind === "knowledge" ? (
          <Markdown text={item.body} />
        ) : (
          <p>{item.body || "Der Inhalt wird noch verarbeitet."}</p>
        )}
      </div>
      {item.processing_error && (
        <div className="error-inline">{item.processing_error}</div>
      )}
      <div className="modal-actions">
        <div className="row">
          {item.web_url && /^https:\/\//.test(item.web_url) && (
            <a
              className="button"
              href={item.web_url}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={15} /> Original öffnen
            </a>
          )}
          {item.kind === "document" && (
            <a className="button" href={"/api/v1/items/" + item.id + "/file"}>
              <Download size={15} /> Datei
            </a>
          )}
          {item.kind !== "task" && (
            <select
              aria-label="Bearbeitungsstatus"
              defaultValue={item.status}
              onChange={async (e) => {
                try {
                  await api("/items/" + item.id, "PATCH", {
                    status: e.target.value,
                  });
                  refresh();
                } catch (e) {
                  notice((e as Error).message, true);
                }
              }}
            >
              {["new", "in_progress", "waiting", "done"].map((s) => (
                <option key={s} value={s}>
                  {statusLabels[s]}
                </option>
              ))}
            </select>
          )}
        </div>
        <Button kind="primary" onClick={onChat}>
          <Sparkles size={16} /> Im Arbeitschat öffnen
        </Button>
      </div>
    </Modal>
  );
}
