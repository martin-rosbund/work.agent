import { useState } from "react";
import { api, Item } from "../../api";
import { Button, Modal } from "../../shared/ui";
import { useNotice } from "../../shared/notifications";

export function EmailReplyDraft({
  conversationId,
  message,
  items,
  close,
  saved,
}: {
  conversationId: string;
  message: { id: string; content: string };
  items: Item[];
  close: () => void;
  saved: () => void;
}) {
  const [itemId, setItemId] = useState(items.length === 1 ? items[0].id : "");
  const [body, setBody] = useState(message.content);
  const [busy, setBusy] = useState(false);
  const notice = useNotice();
  const item = items.find((candidate) => candidate.id === itemId);
  return (
    <Modal title="E-Mail-Entwurf übernehmen" onClose={close} wide>
      <label>
        Auf diese E-Mail antworten
        <select
          value={itemId}
          onChange={(event) => setItemId(event.target.value)}
        >
          <option value="">E-Mail auswählen</option>
          {items.map((mail) => (
            <option key={mail.id} value={mail.id}>
              {mail.title} · {mail.sender}
            </option>
          ))}
        </select>
      </label>
      {item && (
        <p>
          An: <strong>{typeof item.meta.email === "string" ? item.meta.email : item.sender}</strong>
        </p>
      )}
      <label>
        Antworttext
        <textarea
          rows={12}
          maxLength={30000}
          value={body}
          onChange={(event) => setBody(event.target.value)}
        />
      </label>
      <p className="muted-text">
        Prüfe den übernommenen Text und entferne gegebenenfalls Einleitungen des
        Agenten. Gesendet wird erst nach deiner anschließenden Freigabe.
      </p>
      <div className="modal-actions">
        <Button disabled={busy} onClick={close}>
          Abbrechen
        </Button>
        <Button
          kind="primary"
          disabled={busy || !itemId || !body.trim()}
          onClick={async () => {
            setBusy(true);
            try {
              await api(
                `/conversations/${conversationId}/email-reply-draft`,
                "POST",
                {
                  message_id: message.id,
                  item_id: itemId,
                  body,
                },
              );
              saved();
              close();
              notice(
                "E-Mail-Entwurf erstellt. Du kannst ihn jetzt prüfen und freigeben.",
              );
            } catch (error) {
              notice((error as Error).message, true);
            } finally {
              setBusy(false);
            }
          }}
        >
          {busy ? "Wird gespeichert …" : "Entwurf zur Freigabe erstellen"}
        </Button>
      </div>
    </Modal>
  );
}
