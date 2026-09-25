import { Github } from "lucide-react";
import { useState, useEffect, FormEvent, lazy, Suspense } from "react";
import {
  Inbox,
  MessageSquare,
  CheckCheck,
  CalendarDays,
  BookOpen,
  Settings,
  Search,
  Plus,
  ArrowUpRight,
  ChevronRight,
  ChevronDown,
  FileText,
  Link2,
  X,
  LogOut,
  ShieldCheck,
  AlertCircle,
  Menu,
  CheckCircle2,
} from "lucide-react";
import { api, setCsrf, Source, Item } from "../api";
import { Notice, NoticeContext } from "../shared/notifications";
import { Mark, Button, Empty, PageHeader } from "../shared/ui";
import { Auth } from "../features/auth/Auth";
import { InboxPage } from "../features/inbox/InboxPage";
import { ItemModal } from "../features/content/ItemModal";
const GitHubPage = lazy(() =>
  import("../features/github/GitHubPage").then((module) => ({
    default: module.GitHubPage,
  })),
);
const ChatsPage = lazy(() =>
  import("../features/chats/ChatsPage").then((module) => ({
    default: module.ChatsPage,
  })),
);
const TasksPage = lazy(() =>
  import("../features/tasks/TasksPage").then((module) => ({
    default: module.TasksPage,
  })),
);
const CalendarPage = lazy(() =>
  import("../features/calendar/CalendarPage").then((module) => ({
    default: module.CalendarPage,
  })),
);
const KnowledgePage = lazy(() =>
  import("../features/knowledge/KnowledgePage").then((module) => ({
    default: module.KnowledgePage,
  })),
);
const SettingsPage = lazy(() =>
  import("../features/settings/SettingsPage").then((module) => ({
    default: module.SettingsPage,
  })),
);

export function App() {
  const [auth, setAuth] = useState<
      import("../api/generated").components["schemas"]["AuthStatus"] | null
    >(null),
    [route, setRoute] = useState(location.hash.slice(1) || "inbox"),
    [toast, setToast] = useState<{ text: string; error: boolean } | null>(null),
    [sources, setSources] = useState<Source[]>([]),
    [items, setItems] = useState<Item[]>([]),
    [itemPages, setItemPages] = useState(1),
    [hasMore, setHasMore] = useState(false),
    [loadingItems, setLoadingItems] = useState(false),
    [revision, setRevision] = useState(0),
    [query, setQuery] = useState(""),
    [searchResults, setSearchResults] = useState<any[] | null>(null),
    [selected, setSelected] = useState<Item | null>(null),
    [conversation, setConversation] = useState<string | null>(null),
    [mobile, setMobile] = useState(false),
    [error, setError] = useState(""),
    [loaded, setLoaded] = useState(false);
  const notice: Notice = (text, error = false) => setToast({ text, error });
  const refresh = () => setRevision((v) => v + 1);
  const navigate = (page: string) => {
    location.hash = page;
    setMobile(false);
    setQuery("");
    setSearchResults(null);
  };
  async function loadAuth() {
    try {
      const data = await api("/auth/status");
      setAuth(data);
      setCsrf(data.csrf || "");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    loadAuth();
    const hash = () => setRoute(location.hash.slice(1) || "inbox");
    const expired = () => loadAuth();
    window.addEventListener("hashchange", hash);
    window.addEventListener("session-expired", expired);
    return () => {
      window.removeEventListener("hashchange", hash);
      window.removeEventListener("session-expired", expired);
    };
  }, []);
  useEffect(() => {
    if (!auth?.authenticated) return;
    let cancelled = false;
    setLoadingItems(true);
    Promise.all([
      api<Source[]>("/sources"),
      Promise.all(
        Array.from({ length: itemPages }, (_, page) =>
          api<Item[]>(`/items?limit=200&offset=${page * 200}`),
        ),
      ),
    ])
      .then(([s, batches]) => {
        if (cancelled) return;
        setSources(s);
        setItems([
          ...new Map(batches.flat().map((item) => [item.id, item])).values(),
        ]);
        setHasMore(batches[batches.length - 1].length === 200);
        setLoaded(true);
        setError("");
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoadingItems(false);
      });
    return () => {
      cancelled = true;
    };
  }, [auth, revision, itemPages]);
  useEffect(() => {
    if (!auth?.authenticated) return;
    let cursor = 0;
    const events = new EventSource("/api/v1/events");
    events.onmessage = (e) => {
      cursor = Number(e.lastEventId);
      const data = JSON.parse(e.data);
      window.dispatchEvent(
        new CustomEvent("workagent-event", { detail: data }),
      );
      if (data.kind !== "chat.delta") refresh();
      if (data.kind === "job.error") notice(data.payload.error, true);
    };
    return () => events.close();
  }, [auth?.authenticated]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 7000);
    return () => clearTimeout(timer);
  }, [toast]);
  async function runSearch(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) {
      setSearchResults(null);
      return;
    }
    try {
      setSearchResults(await api("/search?q=" + encodeURIComponent(query)));
    } catch (e) {
      notice((e as Error).message, true);
    }
  }
  async function openChat(item?: Item) {
    try {
      const c = await api("/conversations", "POST", {
        title: item?.title || "Neuer Arbeitschat",
        item_ids: item ? [item.id] : [],
      });
      setConversation(c.id);
      setSelected(null);
      navigate("chats");
    } catch (e) {
      notice((e as Error).message, true);
    }
  }
  async function openItem(id: string, locator?: string, version?: number) {
    try {
      const item = await api<Item>("/items/" + id);
      if (locator)
        item.focus = await api(
          "/items/" +
            id +
            "/citation?" +
            new URLSearchParams({
              locator,
              version: String(version || item.version),
            }),
        );
      setSelected(item);
    } catch (e) {
      notice((e as Error).message, true);
    }
  }
  const inbox = items.filter((i) =>
      ["mail", "chat", "channel"].includes(i.kind),
    ),
    tasks = items.filter((i) => i.kind === "task");
  const navigation = [
    ["inbox", "Eingang", Inbox, inbox.filter((i) => i.status === "new").length],
    ["chats", "Arbeitschats", MessageSquare, 0],
    [
      "tasks",
      "Aufgaben",
      CheckCheck,
      tasks.filter((i) => i.status !== "done").length,
    ],
    ["calendar", "Kalender", CalendarDays, 0],
    ["knowledge", "Wissen", BookOpen, 0],
    ["github", "GitHub", Github, 0],
  ] as const;
  if (!auth)
    return (
      <div className="startup">
        <Mark />
        <p>{error || "Dein Arbeitsraum wird geöffnet …"}</p>
        {error && <Button onClick={loadAuth}>Erneut versuchen</Button>}
      </div>
    );
  if (!auth.authenticated)
    return (
      <Auth
        initialized={auth.initialized}
        onDone={() => {
          navigate("inbox");
          loadAuth();
        }}
      />
    );
  return (
    <NoticeContext.Provider value={notice}>
      <div className="app-shell">
        <aside className={"sidebar " + (mobile ? "open" : "")}>
          <a className="wordmark" href="#inbox">
            <Mark />
            <span>
              work<span className="brand-light">agent</span>
              <small>DEIN PERSÖNLICHER ARBEITSRAUM</small>
            </span>
          </a>
          <Button kind="new-chat" onClick={() => openChat()}>
            <Plus size={17} /> Neuer Arbeitschat{" "}
            <span className="shortcut">↗</span>
          </Button>
          <div className="nav-label">ARBEITSRAUM</div>
          <nav>
            {navigation.map(([id, label, C, count]) => (
              <button
                key={id}
                className={"nav-link " + (route === id ? "active" : "")}
                onClick={() => navigate(id)}
              >
                <C size={19} />
                <span>{label}</span>
                {count > 0 && <b>{count}</b>}
              </button>
            ))}
          </nav>
          <div className="sidebar-sources">
            <div className="nav-label">
              VERBUNDENE QUELLEN{" "}
              <button
                onClick={() => navigate("settings")}
                aria-label="Quelle hinzufügen"
              >
                <Plus size={15} />
              </button>
            </div>
            {sources
              .filter(
                (s) =>
                  !["knowledge", "uploads", "local_tasks"].includes(s.kind),
              )
              .slice(0, 5)
              .map((s) => (
                <div className="sidebar-source" key={s.id}>
                  <span
                    className={
                      "source-dot " +
                      (!s.enabled
                        ? "gray"
                        : ["error", "forbidden", "reauth"].includes(s.status)
                          ? "orange"
                          : "")
                    }
                  />
                  <span>{s.name.replace(" · Demo", "")}</span>
                </div>
              ))}
            {!sources.some((s) => s.kind === "mail") && (
              <button
                className="connect-mini"
                onClick={() => navigate("settings")}
              >
                <Link2 size={14} /> Microsoft verbinden
              </button>
            )}
          </div>
          <div className="sidebar-bottom">
            <div className="local-note">
              <span className="live-dot" />
              <span>
                Lokal auf deinem Rechner
                <small>
                  {auth.demo
                    ? "Demodaten sind gekennzeichnet"
                    : "Du behältst die Kontrolle."}
                </small>
              </span>
              <ShieldCheck size={17} />
            </div>
            <button
              className={"nav-link " + (route === "settings" ? "active" : "")}
              onClick={() => navigate("settings")}
            >
              <Settings size={19} />
              <span>Einstellungen</span>
            </button>
            <div className="profile">
              <div className="avatar">DU</div>
              <div>
                Mein Arbeitsraum<small>Persönlich · Europe/Berlin</small>
              </div>
              <button
                className="icon-button"
                title="Abmelden"
                aria-label="Abmelden"
                onClick={async () => {
                  await api("/auth/logout", "POST");
                  loadAuth();
                }}
              >
                <LogOut size={17} />
              </button>
            </div>
          </div>
        </aside>
        <div className="main-shell">
          <header className="topbar">
            <button
              className="icon-button mobile-toggle"
              onClick={() => setMobile(!mobile)}
              aria-label="Menü"
            >
              <Menu size={20} />
            </button>
            <div className="breadcrumb">
              Arbeitsraum <ChevronRight size={14} />
              <strong>
                {navigation.find((n) => n[0] === route)?.[1] || "Einstellungen"}
              </strong>
            </div>
            <form className="global-search" onSubmit={runSearch}>
              <Search size={16} />
              <input
                aria-label="Alles durchsuchen"
                placeholder="Nachrichten und Wissen durchsuchen …"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  if (!e.target.value) setSearchResults(null);
                }}
              />
              <kbd>↵</kbd>
            </form>
            <span className="topbar-date">
              {new Date().toLocaleDateString("de-DE", {
                day: "numeric",
                month: "short",
              })}
            </span>
            <div className="avatar small">DU</div>
          </header>
          <main>
            <Suspense fallback={<p role="status">Ansicht wird geladen …</p>}>
              {error && (
                <div className="error-inline page-error">
                  {error}
                  <Button onClick={refresh}>Erneut laden</Button>
                </div>
              )}
              {searchResults !== null ? (
                <>
                  <PageHeader
                    eyebrow="DEIN ARBEITSWISSEN"
                    title="Suchergebnisse"
                    description={`${searchResults.length} Fundstellen für „${query}“ · Suche lokal ohne KI-Aufruf`}
                    action={
                      <Button
                        onClick={() => {
                          setSearchResults(null);
                          setQuery("");
                        }}
                      >
                        <X size={16} /> Suche schließen
                      </Button>
                    }
                  />
                  <div className="search-results">
                    {searchResults.map((r) => (
                      <button
                        key={r.chunk_id}
                        className="search-result"
                        onClick={() =>
                          openItem(r.item_id, r.locator, r.version)
                        }
                      >
                        <span className="result-locator">
                          <FileText size={15} />
                          {r.locator}
                        </span>
                        <h3>{r.title}</h3>
                        <p>{r.text.slice(0, 350)}</p>
                        <ArrowUpRight size={18} />
                      </button>
                    ))}
                    {!searchResults.length && (
                      <Empty
                        icon={<Search />}
                        title="Noch keine passende Fundstelle"
                        text="Versuche andere Begriffe oder füge deinem Wissensspeicher Dokumente hinzu."
                      />
                    )}
                  </div>
                </>
              ) : route === "inbox" ? (
                <InboxPage
                  items={inbox}
                  sources={sources}
                  loaded={loaded}
                  open={setSelected}
                  chat={openChat}
                  refresh={refresh}
                  settings={() => navigate("settings")}
                />
              ) : route === "chats" ? (
                <ChatsPage
                  selected={conversation}
                  select={setConversation}
                  revision={revision}
                  openItem={openItem}
                  allItems={items}
                />
              ) : route === "tasks" ? (
                <TasksPage
                  items={tasks}
                  sources={sources}
                  revision={revision}
                  refresh={refresh}
                />
              ) : route === "calendar" ? (
                <CalendarPage
                  items={items.filter((i) => i.kind === "calendar")}
                  sources={sources}
                  revision={revision}
                  refresh={refresh}
                  open={setSelected}
                />
              ) : route === "github" ? (
                <GitHubPage
                  revision={revision}
                  openChat={(id) => {
                    setConversation(id);
                    navigate("chats");
                  }}
                />
              ) : route === "knowledge" ? (
                <KnowledgePage
                  items={items.filter((i) =>
                    ["knowledge", "document"].includes(i.kind),
                  )}
                  sources={sources}
                  refresh={refresh}
                  open={setSelected}
                />
              ) : (
                <SettingsPage
                  sources={sources}
                  refresh={refresh}
                  revision={revision}
                />
              )}
              {hasMore &&
                !searchResults &&
                !["settings", "github"].includes(route) && (
                  <div className="load-more">
                    <Button
                      disabled={loadingItems}
                      onClick={() => setItemPages((p) => p + 1)}
                    >
                      <ChevronDown size={16} />{" "}
                      {loadingItems
                        ? "Inhalte werden geladen …"
                        : "Weitere gespeicherte Inhalte laden"}
                    </Button>
                  </div>
                )}
            </Suspense>
          </main>
          <footer className="page-footer">
            <span>
              <ShieldCheck size={13} /> Dein Wissen bleibt in deinem
              Arbeitsraum.
            </span>
            <span>
              WORK AGENT <span className="footer-dot">·</span> v0.2
            </span>
          </footer>
        </div>
        {selected && (
          <ItemModal
            item={selected}
            onClose={() => setSelected(null)}
            onChat={() => openChat(selected)}
            refresh={refresh}
          />
        )}
        {toast && (
          <div
            className={"toast " + (toast.error ? "error" : "")}
            role="status"
          >
            {toast.error ? (
              <AlertCircle size={18} />
            ) : (
              <CheckCircle2 size={18} />
            )}
            <span>{toast.text}</span>
            <button
              onClick={() => setToast(null)}
              aria-label="Meldung schließen"
            >
              <X size={16} />
            </button>
          </div>
        )}
      </div>
    </NoticeContext.Provider>
  );
}
