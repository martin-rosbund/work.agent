import { useEffect, useState } from "react";
import {
  Github,
  RefreshCw,
  Plus,
  Copy,
  MessageSquare,
  ExternalLink,
  ShieldCheck,
} from "lucide-react";
import { api } from "../../api";
import type { components } from "../../api/generated";
import {
  Button,
  Badge,
  Empty,
  Markdown,
  Modal,
  PageHeader,
} from "../../shared/ui";
import { useNotice } from "../../shared/notifications";
import { fmt, statusLabels } from "../../shared/presentation";
import { GitHubConnections } from "./GitHubConnections";
import { labelColor, localStatusColor } from "./issueBadges";
import "./issueBadges.css";

type Repository = components["schemas"]["RepositoryView"];
type Issue = components["schemas"]["IssueDetail"];
type IssuePage = components["schemas"]["IssuePage"];

export function GitHubPage({
  revision,
  openChat,
  onChange,
}: {
  revision: number;
  openChat: (id: string) => void;
  onChange: () => void;
}) {
  const notice = useNotice();
  const [repos, setRepos] = useState<Repository[]>([]);
  const [labels, setLabels] = useState<string[]>([]);
  const [page, setPage] = useState<IssuePage>({ items: [], total: 0 });
  const [filter, setFilter] = useState({
    owner: "",
    repository_id: "",
    state: "open",
    label: "",
    assignee: "",
    local_status: "",
  });
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Issue | null>(null);
  const [connections, showConnections] = useState(false);
  const [version, refresh] = useState(0);
  const [error, setError] = useState("");
  const [busyRepos, setBusyRepos] = useState<Record<string, boolean>>({});
  const [progress, setProgress] = useState("");
  useEffect(() => {
    const update = (event: Event) => {
      const data = (event as CustomEvent).detail;
      if (data.kind === "github.progress")
        setProgress(
          data.payload.phase === "discovery"
            ? "Repositories werden gesucht …"
            : `${data.payload.repository}: ${data.payload.imported} Issues verarbeitet …`,
        );
      if (
        ["github.synced", "github.discovered", "github.error"].includes(
          data.kind,
        )
      )
        setProgress("");
    };
    window.addEventListener("workagent-event", update);
    return () => window.removeEventListener("workagent-event", update);
  }, []);
  useEffect(() => {
    let cancelled = false;
    const query = new URLSearchParams(
      Object.entries(filter).filter(([, v]) => v),
    );
    query.set("offset", String(offset));
    Promise.all([
      api<Repository[]>("/github/repositories"),
      api<IssuePage>("/github/issues?" + query),
      api<string[]>("/github/labels"),
    ])
      .then(([r, p, availableLabels]) => {
        if (!cancelled) {
          setRepos(r);
          setPage(p);
          setLabels(availableLabels);
          setError("");
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [revision, version, filter, offset]);
  const updateFilter = (key: keyof typeof filter, value: string) => {
    setFilter((old) => ({
      ...old,
      [key]: value,
      ...(key === "owner" ? { repository_id: "" } : {}),
    }));
    setOffset(0);
  };
  async function updateRepo(
    repo: Repository,
    change: { enabled?: boolean; ai_enabled?: boolean },
  ) {
    setBusyRepos((old) => ({ ...old, [repo.id]: true }));
    setRepos((old) =>
      old.map((row) => (row.id === repo.id ? { ...row, ...change } : row)),
    );
    try {
      await api(`/github/repositories/${repo.id}`, "PATCH", change);
      onChange();
    } catch (e) {
      setRepos((old) => old.map((row) => (row.id === repo.id ? repo : row)));
      notice((e as Error).message, true);
    } finally {
      setBusyRepos((old) => ({ ...old, [repo.id]: false }));
    }
  }
  async function detail(id: string) {
    try {
      setSelected(await api<Issue>(`/github/issues/${id}`));
    } catch (e) {
      notice((e as Error).message, true);
    }
  }
  async function synchronize() {
    try {
      await api("/github/sync", "POST", {});
      notice("Aktualisierung vorgemerkt. Demodaten bleiben lokal.");
    } catch (e) {
      notice((e as Error).message, true);
    }
  }
  async function linkChat(issue: Issue) {
    try {
      const chat = await api<components["schemas"]["ConversationView"]>(
        `/github/issues/${issue.id}/conversation`,
        "POST",
      );
      openChat(chat.id);
    } catch (e) {
      notice((e as Error).message, true);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="DEINE ENTWICKLUNGSARBEIT"
        title="GitHub"
        description="Issues im Blick. Nächste Schritte an einem Ort."
        action={
          <div className="button-row">
            <Button onClick={synchronize}>
              <RefreshCw size={16} /> Aktualisieren
            </Button>
            <Button onClick={() => showConnections(true)}>
              <Plus size={16} /> Verbindungen
            </Button>
          </div>
        }
      />
      <div className="github-note">
        <ShieldCheck size={18} />
        <span>
          GitHub wird ausschließlich gelesen. KI-Zugriff gibst du je Repository
          frei. Ein Codex-Auftrag wird nur kopiert.
        </span>
      </div>
      {progress && (
        <p role="status" className="github-note">
          {progress}
        </p>
      )}
      {error && (
        <p role="alert" className="error-box">
          {error}
        </p>
      )}
      <details className="github-repositories" open={repos.length === 0}>
        <summary>
          Repositories & KI-Freigaben <Badge>{repos.length}</Badge>
        </summary>
        <div className="github-repo-grid">
          {repos.map((repo) => (
            <article key={repo.id} className="github-repo">
              <strong>
                <Github size={16} /> {repo.full_name}
              </strong>
              <div className="button-row">
                {repo.demo && <Badge>DEMO</Badge>}
                <Badge>{statusLabels[repo.status] || repo.status}</Badge>
                {repo.archived && <Badge>Archiviert</Badge>}
              </div>
              {repo.error && <p role="alert">{repo.error}</p>}
              <label className="check">
                <input
                  type="checkbox"
                  checked={repo.enabled}
                  disabled={busyRepos[repo.id]}
                  onChange={(e) =>
                    updateRepo(repo, { enabled: e.target.checked })
                  }
                />{" "}
                Repository überwachen
              </label>
              <label className="check">
                <input
                  type="checkbox"
                  checked={repo.ai_enabled}
                  disabled={busyRepos[repo.id]}
                  onChange={(e) =>
                    updateRepo(repo, { ai_enabled: e.target.checked })
                  }
                />{" "}
                KI-Verarbeitung erlauben
              </label>
              <small>
                Letzte Aktualisierung:{" "}
                {repo.last_sync
                  ? fmt(repo.last_sync)
                  : "Noch nicht synchronisiert"}
              </small>
            </article>
          ))}
        </div>
        {!repos.length && (
          <p>
            Verbinde ein GitHub-Konto oder eine Organisation mit einem
            Fine-grained Token.
          </p>
        )}
      </details>
      <div className="github-filters">
        <label>
          Eigentümer
          <select
            aria-label="Eigentümer"
            value={filter.owner}
            onChange={(e) => updateFilter("owner", e.target.value)}
          >
            <option value="">Alle Eigentümer</option>
            {[...new Set(repos.map((r) => r.owner))].map((o) => (
              <option key={o}>{o}</option>
            ))}
          </select>
        </label>
        <label>
          Repository
          <select
            aria-label="Repository"
            value={filter.repository_id}
            onChange={(e) => updateFilter("repository_id", e.target.value)}
          >
            <option value="">Alle Repositories</option>
            {repos
              .filter((r) => !filter.owner || r.owner === filter.owner)
              .map((r) => (
                <option value={r.id} key={r.id}>
                  {r.full_name}
                </option>
              ))}
          </select>
        </label>
        <label>
          GitHub-Status
          <select
            aria-label="GitHub-Status"
            value={filter.state}
            onChange={(e) => updateFilter("state", e.target.value)}
          >
            <option value="open">Offen</option>
            <option value="closed">Geschlossen</option>
            <option value="">Alle</option>
          </select>
        </label>
        <label>
          Typ / Label
          <select
            aria-label="Typ / Label"
            value={filter.label}
            onChange={(e) => updateFilter("label", e.target.value)}
          >
            <option value="">Alle Labels</option>
            {labels.map((label) => (
              <option key={label} value={label}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Lokaler Status
          <select
            aria-label="Lokaler Status"
            value={filter.local_status}
            onChange={(e) => updateFilter("local_status", e.target.value)}
          >
            <option value="">Alle Bearbeitungsstände</option>
            <option value="new">Neu</option>
            <option value="in_progress">In Arbeit</option>
            <option value="done">Erledigt</option>
            <option value="archived">Archiviert</option>
          </select>
        </label>
        <label>
          Zuständig
          <input
            aria-label="Zuständig"
            value={filter.assignee}
            onChange={(e) => updateFilter("assignee", e.target.value)}
            placeholder="GitHub-Name"
          />
        </label>
      </div>
      <div className="github-list-heading">
        <h2>Issues</h2>
        <span>{page.total} Ergebnisse</span>
      </div>
      <div className="github-issues">
        {page.items.map((issue) => (
          <button
            className="github-issue"
            key={issue.id}
            onClick={() => detail(issue.id)}
          >
            <div className="github-issue-symbol">
              <Github size={21} />
            </div>
            <div>
              <small>
                {issue.repository} · #{issue.number} {issue.demo && "· DEMO"}
              </small>
              <h3>{issue.title}</h3>
              <div className="button-row">
                <Badge
                  kind={
                    issue.state === "open" ? "github-green" : "github-purple"
                  }
                >
                  {issue.state === "open" ? "Offen" : "Geschlossen"}
                </Badge>
                {issue.labels.map((l) => (
                  <Badge key={l} kind={labelColor(l)}>
                    {l}
                  </Badge>
                ))}
                <Badge kind={localStatusColor(issue.local_status)}>
                  Lokal:{" "}
                  {statusLabels[issue.local_status] || issue.local_status}
                </Badge>
              </div>
            </div>
            <time>{fmt(issue.updated_at)}</time>
          </button>
        ))}
      </div>
      {!page.items.length && (
        <Empty
          icon={<Github />}
          title="Keine passenden Issues"
          text="Passe die Filter an oder verbinde deine Repositories."
        />
      )}
      <div className="button-row github-pagination">
        <Button
          disabled={offset === 0}
          onClick={() => setOffset((n) => Math.max(0, n - 50))}
        >
          Zurück
        </Button>
        <Button
          disabled={offset + 50 >= page.total}
          onClick={() => setOffset((n) => n + 50)}
        >
          Weitere Issues
        </Button>
      </div>
      {selected && (
        <Modal
          title={`${selected.repository} #${selected.number}`}
          onClose={() => setSelected(null)}
          wide
        >
          <div className="github-detail">
            <div className="button-row">
              {selected.demo && <Badge>DEMO</Badge>}
              <Badge
                kind={
                  selected.state === "open" ? "github-green" : "github-purple"
                }
              >
                {selected.state === "open"
                  ? "GitHub: Offen"
                  : "GitHub: Geschlossen"}
              </Badge>
              <Badge kind={localStatusColor(selected.local_status)}>
                Lokal:{" "}
                {statusLabels[selected.local_status] || selected.local_status}
              </Badge>
              {selected.labels.map((label) => (
                <Badge key={label} kind={labelColor(label)}>
                  {label}
                </Badge>
              ))}
              <Badge>
                {selected.ai_enabled ? "KI freigegeben" : "Nur lokal"}
              </Badge>
            </div>
            <h2>{selected.title}</h2>
            <div className="button-row">
              <Button
                kind="primary"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(selected.codex_prompt);
                    notice("Codex-Auftrag kopiert.");
                  } catch {
                    notice(
                      "Kopieren nicht verfügbar. Auftrag unten markieren und kopieren.",
                      true,
                    );
                  }
                }}
              >
                <Copy size={16} /> Codex-Auftrag kopieren
              </Button>
              <Button onClick={() => linkChat(selected)}>
                <MessageSquare size={16} /> Arbeitschat öffnen
              </Button>
              <a href={selected.web_url} target="_blank" rel="noreferrer">
                <ExternalLink size={15} /> Auf GitHub
              </a>
            </div>
            <code className="github-command">{selected.codex_prompt}</code>
            <label>
              Lokale Bearbeitung
              <select
                aria-label="Lokale Bearbeitung"
                value={selected.local_status}
                onChange={async (e) => {
                  try {
                    setSelected(
                      await api<Issue>(
                        `/github/issues/${selected.id}`,
                        "PATCH",
                        { status: e.target.value },
                      ),
                    );
                    refresh((v) => v + 1);
                  } catch (err) {
                    notice((err as Error).message, true);
                  }
                }}
              >
                <option value="new">Offen</option>
                <option value="in_progress">In Arbeit</option>
                <option value="done">Erledigt</option>
                <option value="archived">Archiviert</option>
              </select>
            </label>
            <p className="muted">
              Von {selected.author} · Zuständig:{" "}
              {selected.assignees.join(", ") || "Niemand"} · Meilenstein:{" "}
              {selected.milestone || "Keiner"}
            </p>
            <Markdown text={selected.description} />
            {selected.pull_requests.length > 0 && (
              <section>
                <h3>Verknüpfte Pull Requests</h3>
                {selected.pull_requests.map((pr) => (
                  <p key={pr.url}>
                    <a href={pr.url} target="_blank" rel="noreferrer">
                      #{pr.number} {pr.title}
                    </a>{" "}
                    · {pr.state === "open" ? "Offen" : "Geschlossen"}
                  </p>
                ))}
              </section>
            )}
            <h3>Kommentare ({selected.comments.length})</h3>
            {selected.comments.map((c) => (
              <article className="github-comment" key={c.id}>
                <small>
                  {c.author} · {fmt(c.updated_at)}
                </small>
                <Markdown text={c.body} />
              </article>
            ))}
            {selected.conversations.length > 0 && (
              <p>{selected.conversations.length} verknüpfte Arbeitschats</p>
            )}
          </div>
        </Modal>
      )}
      {connections && (
        <GitHubConnections
          onClose={() => {
            showConnections(false);
            onChange();
          }}
        />
      )}
    </>
  );
}
