import { useEffect, useState } from "react";
import { api } from "../../api";
import type { components } from "../../api/generated";
import { Button, Badge, Modal } from "../../shared/ui";
import { useNotice } from "../../shared/notifications";
import { statusLabels } from "../../shared/presentation";
type Connection = components["schemas"]["ConnectionView"];

export function GitHubConnections({ onClose }: { onClose: () => void }) {
  const notice = useNotice();
  const [rows, setRows] = useState<Connection[]>([]);
  const [name, setName] = useState("");
  const [owner, setOwner] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const load = () =>
    api<Connection[]>("/github/connections")
      .then(setRows)
      .catch((e) => notice(e.message, true));
  useEffect(() => {
    load();
  }, []);
  return (
    <Modal title="GitHub-Verbindungen" onClose={onClose} wide>
      <div className="github-detail">
        <p>
          Je Verbindung ein Fine-grained Personal Access Token für dein Konto
          oder eine Organisation. Für neue Repositories wähle bei GitHub{" "}
          <strong>All repositories</strong>.
        </p>
        <p>
          Repository-Rechte:{" "}
          <strong>Metadata, Issues und Pull requests: Read-only</strong>. Der
          Work Agent benötigt keine Schreibrechte. Organisationsfreigaben können
          zusätzlich erforderlich sein.
        </p>
        <a
          href="https://github.com/settings/personal-access-tokens/new"
          target="_blank"
          rel="noreferrer"
        >
          Token bei GitHub erstellen ↗
        </a>
        {rows.map((row) => (
          <article className="github-repo" key={row.id}>
            <strong>
              {row.name} · {row.owner}
            </strong>
            <Badge>{row.demo ? "DEMO" : statusLabels[row.status] || row.status}</Badge>
            {row.error && <p role="alert">{row.error}</p>}
            <div className="button-row">
              <Button
                onClick={async () => {
                  try {
                    const result = await api<
                      components["schemas"]["ConnectionTest"]
                    >(`/github/connections/${row.id}/test`, "POST");
                    notice(result.message, !result.ok);
                  } catch (e) {
                    notice((e as Error).message, true);
                  }
                  await load();
                }}
              >
                Verbindung testen
              </Button>
              <Button
                onClick={async () => {
                  try {
                    await api(`/github/connections/${row.id}`, "PATCH", {
                      enabled: !row.enabled,
                    });
                    await load();
                  } catch (e) {
                    notice((e as Error).message, true);
                  }
                }}
              >
                {row.enabled ? "Deaktivieren" : "Aktivieren"}
              </Button>
              <Button onClick={() => setConfirmDelete(row.id)}>
                Löschen
              </Button>
            </div>
            {confirmDelete === row.id && (
              <div role="group" aria-label="Verbindung löschen bestätigen">
                <p>
                  Verbindung „{row.name}“ ({row.owner}) und den lokal gespeicherten
                  Token löschen? Das ist nur ohne importierte Repositories möglich.
                </p>
                <div className="button-row">
                  <Button
                    disabled={deleting === row.id}
                    onClick={async () => {
                      setDeleting(row.id);
                      try {
                        await api(`/github/connections/${row.id}`, "DELETE");
                        setConfirmDelete(null);
                        await load();
                        notice("GitHub-Verbindung gelöscht.");
                      } catch (error) {
                        notice((error as Error).message, true);
                      } finally {
                        setDeleting(null);
                      }
                    }}
                  >
                    {deleting === row.id ? "Wird gelöscht …" : "Endgültig löschen"}
                  </Button>
                  <Button disabled={deleting === row.id} onClick={() => setConfirmDelete(null)}>
                    Abbrechen
                  </Button>
                </div>
              </div>
            )}
            {!row.demo && (
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  const form = e.currentTarget;
                  const replacement = new FormData(form).get("replacement");
                  try {
                    await api(`/github/connections/${row.id}`, "PATCH", {
                      token: replacement,
                    });
                    form.reset();
                    notice("Token ersetzt.");
                    await load();
                  } catch (error) {
                    notice((error as Error).message, true);
                  }
                }}
              >
                <label>
                  Token erneuern
                  <input
                    name="replacement"
                    type="password"
                    minLength={10}
                    required
                    autoComplete="off"
                  />
                </label>
                <Button type="submit">Token ersetzen</Button>
              </form>
            )}
          </article>
        ))}
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              await api("/github/connections", "POST", { name, owner, token });
              setToken("");
              setOwner("");
              setName("");
              await load();
              notice(
                "Verbindung gespeichert. Die Repository-Erkennung läuft im Hintergrund.",
              );
            } catch (error) {
              notice((error as Error).message, true);
            } finally {
              setBusy(false);
            }
          }}
        >
          <h3>Neue Verbindung</h3>
          <label>
            Name
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z. B. Firma"
              maxLength={200}
            />
          </label>
          <label>
            GitHub-Eigentümer
            <input
              required
              value={owner}
              onChange={(e) => setOwner(e.target.value)}
              placeholder="Kontoname oder Organisation"
              pattern="[A-Za-z0-9][A-Za-z0-9-]{0,38}"
            />
          </label>
          <label>
            Fine-grained Token
            <input
              required
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              minLength={10}
            />
          </label>
          <p className="muted">
            Der Token wird verschlüsselt gespeichert und danach nicht mehr
            angezeigt.
          </p>
          <Button kind="primary" type="submit" disabled={busy}>
            {busy ? "Wird gespeichert …" : "Verbindung speichern"}
          </Button>
        </form>
      </div>
    </Modal>
  );
}
