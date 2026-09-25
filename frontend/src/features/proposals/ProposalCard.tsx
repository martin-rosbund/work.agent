import { useState } from "react";
import { Sparkles, FileText, Check, LoaderCircle } from "lucide-react";
import { api, Proposal } from "../../api";
import { actionLabels, statusLabels, fmt } from "../../shared/presentation";
import { useNotice } from "../../shared/notifications";
import { Button, Badge, Markdown, Modal } from "../../shared/ui";
import { ProposalEditor } from "./ProposalEditor";

export function ProposalCard({
  proposal,
  refresh,
  openItem,
}: {
  proposal: Proposal;
  refresh: () => void;
  openItem?: (id: string, locator?: string, version?: number) => void;
}) {
  const [editing, setEditing] = useState(false),
    [confirm, setConfirm] = useState(false),
    [busy, setBusy] = useState(false);
  const notice = useNotice();
  async function approve() {
    setBusy(true);
    try {
      await api("/proposals/" + proposal.id + "/approve", "POST", {
        version: proposal.version,
      });
      setConfirm(false);
      refresh();
      notice("Freigabe gespeichert. Die Aktion wird jetzt verarbeitet.");
    } catch (e) {
      notice((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  const p = proposal.payload;
  return (
    <div
      className={
        "proposal-card " + (proposal.status === "draft" ? "" : "completed")
      }
    >
      <div className="proposal-top">
        <strong>
          <Sparkles size={15} />
          {actionLabels[proposal.kind]}
        </strong>
        <Badge
          kind={
            ["done", "demo_done"].includes(proposal.status)
              ? "green"
              : ["failed", "unknown"].includes(proposal.status)
                ? "orange"
                : ""
          }
        >
          {statusLabels[proposal.status]}
        </Badge>
      </div>
      {p.recipient && (
        <div className="proposal-target">
          An: <strong>{p.recipient}</strong>
        </div>
      )}
      {p.title && <h4>{p.title}</h4>}
      {p.subject && <h4>{p.subject}</h4>}
      {p.start && (
        <div className="proposal-target">
          {fmt(p.start)} – {fmt(p.end)}
          {(p.attendees?.length ?? 0) > 0 && (
            <p>Teilnehmer: {p.attendees?.join(", ")}</p>
          )}
        </div>
      )}
      {p.due && <div className="proposal-target">Fällig: {p.due}</div>}
      {(p.body || p.content) && <Markdown text={p.body || p.content || ""} />}
      {proposal.result?.message && (
        <p className="result-message">{proposal.result.message}</p>
      )}
      {proposal.result?.error && (
        <p className="error-inline">{proposal.result.error}</p>
      )}
      {openItem && proposal.citations.length > 0 && (
        <div className="citations">
          {proposal.citations.map((c, n) => (
            <button
              key={n}
              onClick={() => openItem(c.item_id, c.locator, c.version)}
            >
              <FileText size={12} />
              {c.title || "Quelle"} · {c.locator}
            </button>
          ))}
        </div>
      )}
      {proposal.status === "draft" && (
        <div className="proposal-actions">
          <Button onClick={() => setEditing(true)}>Bearbeiten</Button>
          <button
            className="text-link muted-text"
            onClick={async () => {
              try {
                await api("/proposals/" + proposal.id + "/reject", "POST", {
                  version: proposal.version,
                });
                refresh();
              } catch (e) {
                notice((e as Error).message, true);
              }
            }}
          >
            Verwerfen
          </button>
          <Button kind="primary" onClick={() => setConfirm(true)}>
            <Check size={15} /> Prüfen & freigeben
          </Button>
        </div>
      )}
      {editing && (
        <ProposalEditor
          proposal={proposal}
          close={() => setEditing(false)}
          saved={refresh}
        />
      )}
      {confirm && (
        <Modal title="Diese Aktion freigeben" onClose={() => setConfirm(false)}>
          <p className="muted-text">
            Du bestätigst Version {proposal.version} dieses Vorschlags.
            Änderungen danach benötigen eine neue Freigabe.
          </p>
          <div className="approval-preview">
            <strong>{actionLabels[proposal.kind]}</strong>
            {p.recipient && <p>An: {p.recipient}</p>}
            {p.title && <h3>{p.title}</h3>}
            {p.subject && <h3>{p.subject}</h3>}
            {p.start && (
              <p>
                {fmt(p.start)} – {fmt(p.end)}
              </p>
            )}
            {(p.attendees?.length ?? 0) > 0 && (
              <p>Teilnehmer: {p.attendees?.join(", ")}</p>
            )}
            {p.due && <p>Fällig: {p.due}</p>}
            <Markdown
              text={
                p.body || p.content || "Diese Aufgabe als erledigt markieren."
              }
            />
          </div>
          <div className="modal-actions">
            <Button onClick={() => setConfirm(false)}>Zurück</Button>
            <Button kind="primary" disabled={busy} onClick={approve}>
              {busy ? (
                <LoaderCircle className="spin" size={16} />
              ) : (
                <Check size={16} />
              )}{" "}
              Verbindlich freigeben
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
