import { useState, useEffect, FormEvent } from "react";
import {
  CheckCheck,
  ArrowRight,
  ShieldCheck,
  LoaderCircle,
  AlertCircle,
} from "lucide-react";
import { api, setCsrf } from "../../api";
import { Mark, Button, Badge } from "../../shared/ui";

export function Auth({
  initialized,
  onDone,
}: {
  initialized: boolean;
  onDone: () => void;
}) {
  const [password, setPassword] = useState(""),
    [demo, setDemo] = useState(true),
    [token, setToken] = useState(
      new URLSearchParams(location.hash.slice(1)).get("setup") || "",
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    if (location.hash.includes("setup="))
      history.replaceState(null, "", location.pathname);
  }, []);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await api(
        "/auth/" + (initialized ? "login" : "setup"),
        "POST",
        { password, demo },
        { "X-Setup-Token": token },
      );
      setCsrf(data.csrf);
      onDone();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="auth-page">
      <div className="auth-story">
        <div className="wordmark">
          <Mark />
          <span>
            work<span className="brand-light">agent</span>
          </span>
        </div>
        <div className="auth-copy">
          <span className="eyebrow">MEHR ÜBERBLICK. WENIGER KOPFARBEIT.</span>
          <h1>
            Dein Arbeitstag.
            <br />
            Wieder in
            <br />
            <em>deiner Hand.</em>
          </h1>
          <p>
            Nachrichten, Aufgaben und dein Wissen an einem Ort. Ein Assistent,
            der mitdenkt — und dich entscheiden lässt.
          </p>
          <div className="auth-tags">
            <span>
              <ShieldCheck size={16} /> Lokal gespeichert
            </span>
            <span>
              <CheckCheck size={16} /> Du gibst frei
            </span>
          </div>
        </div>
        <div className="auth-bottom">
          Dein persönlicher Arbeitsraum <span>01 / WORKSPACE</span>
        </div>
      </div>
      <div className="auth-form-area">
        <form className="auth-form" onSubmit={submit}>
          <Badge kind="green">
            {initialized ? "WILLKOMMEN ZURÜCK" : "DEIN NEUER ARBEITSRAUM"}
          </Badge>
          <h2>
            {initialized
              ? "Schön, dass du da bist."
              : "Lass uns Ordnung schaffen."}
          </h2>
          <p>
            {initialized
              ? "Melde dich an, um deinen Arbeitstag zu öffnen."
              : "Lege ein lokales Passwort fest. Microsoft und OpenAI verbindest du anschließend in den Einstellungen."}
          </p>
          <label>
            Dein Passwort
            <input
              type="password"
              minLength={12}
              maxLength={256}
              required
              autoComplete={initialized ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Mindestens 12 Zeichen"
            />
          </label>
          {!initialized && (
            <>
              <label>
                Einrichtungscode
                <input
                  type="password"
                  required
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  placeholder="Wird vom Startskript geöffnet"
                />
              </label>
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={demo}
                  onChange={(e) => setDemo(e.target.checked)}
                />
                <span>
                  Mit Beispieldaten starten
                  <small>
                    Den Arbeitsablauf ohne Kontoverbindung ausprobieren.
                  </small>
                </span>
              </label>
            </>
          )}
          {error && (
            <div className="error-inline">
              <AlertCircle size={16} />
              {error}
            </div>
          )}
          <Button type="submit" kind="primary full" disabled={busy}>
            {busy ? (
              <LoaderCircle className="spin" size={17} />
            ) : initialized ? (
              "Arbeitsraum öffnen"
            ) : (
              "Arbeitsraum erstellen"
            )}
            <ArrowRight size={17} />
          </Button>
          <p className="auth-footnote">
            <ShieldCheck size={15} /> Dein Passwort bleibt in dieser
            Installation.
          </p>
        </form>
      </div>
    </div>
  );
}
