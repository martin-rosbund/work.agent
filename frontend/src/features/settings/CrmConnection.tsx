import { useEffect, useState } from "react";
import { api } from "../../api";
import { Button, Badge } from "../../shared/ui";
import { useNotice } from "../../shared/notifications";

type Connection = {
  url: string;
  api_url: string;
  name: string;
  configured: boolean;
};

export function CrmConnection({ refresh }: { refresh: () => void }) {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [url, setUrl] = useState("");
  const [apiUrl, setApiUrl] = useState("");
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const notice = useNotice();
  useEffect(() => {
    api<Connection>("/crm")
      .then((c) => {
        setConnection(c);
        setUrl(c.url);
        setApiUrl(c.api_url);
      })
      .catch((e) => notice(e.message, true));
  }, []);
  async function run(method: string, path = "/crm") {
    setBusy(true);
    try {
      const c = await api<Connection>(
        path,
        method,
        method === "PUT" ? { url, api_url: apiUrl, token } : undefined,
      );
      setConnection(c);
      setToken("");
      refresh();
      notice(
        method === "DELETE"
          ? "CRM-Verbindung getrennt. API-Key entfernt."
          : "CRM-Verbindung geprüft.",
      );
    } catch (e) {
      notice((e as Error).message, true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="settings-card">
      <div className="settings-title">
        <div>
          <h2>ISB.CRM</h2>
          <p>Dein Kalender und vier getrennte Aufgabenbereiche.</p>
        </div>
        <Badge kind={connection?.configured ? "green" : ""}>
          {connection?.configured ? "Verbunden" : "Einrichten"}
        </Badge>
      </div>
      <p className="settings-copy">
        Persönlichen API-Key im CRM erstellen. Es werden deine zugewiesenen
        Events, Aufwandsschätzungen, Office Tasks (interne Vorgänge) und
        Verkaufschancen sowie CRM-Tickets synchronisiert.
      </p>
      <label>
        CRM-Adresse
        <input
          placeholder="https://crm.example.de oder http://localhost:5173"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      </label>
      <label>
        Abweichende API-Adresse (optional)
        <input
          placeholder="Lokal: http://localhost:3000 · ohne /api"
          value={apiUrl}
          onChange={(e) => setApiUrl(e.target.value)}
        />
      </label>
      <label>
        Persönlicher API-Key
        <input
          type="password"
          autoComplete="new-password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          placeholder={
            connection?.configured
              ? "Gespeichert · leer lassen zum Beibehalten"
              : "Personal Access Token"
          }
        />
      </label>
      <div className="row wrap">
        <Button
          kind="primary"
          disabled={busy || !url}
          onClick={() => run("PUT")}
        >
          Verbinden & prüfen
        </Button>
        <Button
          disabled={busy || !connection?.configured}
          onClick={() => run("POST", "/crm/test")}
        >
          Verbindung testen
        </Button>
        <Button
          disabled={busy || !connection?.configured}
          onClick={() => run("DELETE")}
        >
          Verbindung trennen
        </Button>
      </div>
      {connection?.configured && (
        <p className="connected-account">{connection.name}</p>
      )}
      <p className="field-help">
        Jeder Bereich erscheint unten als eigene Quelle. KI-Zugriff und
        Schreibzugriff schaltest du einzeln frei. Änderungen werden alle fünf
        Minuten eingelesen. Schreibaktionen benötigen deine Freigabe. Nach
        erneutem Verbinden getrennte Quellen wieder aktivieren.
      </p>
    </section>
  );
}
