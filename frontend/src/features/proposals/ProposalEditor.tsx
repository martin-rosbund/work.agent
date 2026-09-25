import { useState, useEffect } from "react";
import { DateTime } from "luxon";
import { api, Source, Proposal } from "../../api";
import { actionLabels, localDateTime } from "../../shared/presentation";
import { useNotice } from "../../shared/notifications";
import { Button, Markdown, Modal } from "../../shared/ui";

export function ProposalEditor({
  proposal,
  close,
  saved,
  sources = [],
}: {
  proposal: Proposal;
  close: () => void;
  saved: () => void;
  sources?: Source[];
}) {
  const [payload, setPayload] = useState({ ...proposal.payload }),
    [targets, setTargets] = useState<Source[]>(sources),
    [busy, setBusy] = useState(false),
    [original, setOriginal] = useState("");
  const notice = useNotice();
  useEffect(() => {
    if (!sources.length) api<Source[]>("/sources").then(setTargets);
    if (payload.item_id && proposal.kind === "knowledge")
      api("/items/" + payload.item_id)
        .then((i) => setOriginal(i.body))
        .catch(() => {});
  }, []);
  const change = (key: string, value: any) =>
    setPayload((p: any) => ({ ...p, [key]: value }));
  async function save() {
    setBusy(true);
    try {
      await api(
        proposal.id ? "/proposals/" + proposal.id : "/proposals",
        proposal.id ? "PUT" : "POST",
        {
          kind: proposal.kind,
          payload,
          version: proposal.version,
          item_id: proposal.item_id,
          conversation_id: proposal.conversation_id,
        },
      );
      saved();
      close();
    } catch (e) {
      notice((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title={actionLabels[proposal.kind]} onClose={close} wide>
      {payload.recipient && (
        <label>
          Ziel
          <input value={payload.recipient} readOnly />
        </label>
      )}
      {["create_task", "update_task", "create_event"].includes(
        proposal.kind,
      ) && (
        <label>
          Ziel
          <select
            value={payload.source_id || ""}
            onChange={(e) => change("source_id", e.target.value || null)}
          >
            {proposal.kind === "create_task" && (
              <option value="">Nur in meinem Arbeitsraum</option>
            )}
            {targets
              .filter(
                (s) =>
                  s.enabled &&
                  s.writable &&
                  s.kind ===
                    (proposal.kind === "create_event" ? "calendar" : "todo"),
              )
              .map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
          </select>
        </label>
      )}
      {["create_task", "update_task", "knowledge"].includes(proposal.kind) && (
        <label>
          Titel
          <input
            value={payload.title || ""}
            onChange={(e) => change("title", e.target.value)}
          />
        </label>
      )}
      {proposal.kind === "create_event" && (
        <>
          <label>
            Betreff
            <input
              value={payload.subject || ""}
              onChange={(e) => change("subject", e.target.value)}
            />
          </label>
          <div className="two-columns">
            <label>
              Beginn
              <input
                type="datetime-local"
                value={localDateTime(payload.start)}
                onChange={(e) =>
                  change(
                    "start",
                    e.target.value
                      ? DateTime.fromISO(e.target.value, {
                          zone: "Europe/Berlin",
                        }).toISO()
                      : null,
                  )
                }
              />
            </label>
            <label>
              Ende
              <input
                type="datetime-local"
                value={localDateTime(payload.end)}
                onChange={(e) =>
                  change(
                    "end",
                    e.target.value
                      ? DateTime.fromISO(e.target.value, {
                          zone: "Europe/Berlin",
                        }).toISO()
                      : null,
                  )
                }
              />
            </label>
          </div>
          <label>
            Teilnehmer (E-Mail-Adressen, durch Komma getrennt)
            <input
              value={(payload.attendees || []).join(", ")}
              onChange={(e) =>
                change(
                  "attendees",
                  e.target.value
                    .split(",")
                    .map((x) => x.trim())
                    .filter(Boolean),
                )
              }
            />
          </label>
        </>
      )}
      {["create_task", "update_task"].includes(proposal.kind) && (
        <label>
          Fällig am
          <input
            type="date"
            value={(payload.due || "").slice(0, 10)}
            onChange={(e) => change("due", e.target.value || null)}
          />
        </label>
      )}
      {proposal.kind === "knowledge" && original && (
        <div className="old-version">
          <div className="eyebrow">BISHERIGE FASSUNG</div>
          <Markdown text={original} />
        </div>
      )}
      {proposal.kind !== "complete_task" && (
        <label>
          {proposal.kind === "knowledge" ? "Neue Fassung (Markdown)" : "Text"}
          <textarea
            rows={8}
            value={
              payload[proposal.kind === "knowledge" ? "content" : "body"] || ""
            }
            onChange={(e) =>
              change(
                proposal.kind === "knowledge" ? "content" : "body",
                e.target.value,
              )
            }
          />
        </label>
      )}
      <div className="modal-actions">
        <Button onClick={close}>Abbrechen</Button>
        <Button kind="primary" onClick={save} disabled={busy}>
          Entwurf speichern
        </Button>
      </div>
    </Modal>
  );
}
