import { useState, useEffect, useRef, FormEvent } from "react";
import {
  MessageSquare,
  ArrowUpRight,
  ChevronRight,
  Sparkles,
  FileText,
  Link2,
  Send,
  ShieldCheck,
  LoaderCircle,
} from "lucide-react";
import { api, Item, Proposal } from "../../api";
import { labels, fmt } from "../../shared/presentation";
import { useNotice } from "../../shared/notifications";
import {
  Icon,
  Button,
  Empty,
  Markdown,
  Modal,
  PageHeader,
} from "../../shared/ui";
import { ProposalCard } from "../proposals/ProposalCard";
import { EmailReplyDraft } from "./EmailReplyDraft";

export function ChatsPage({
  selected,
  select,
  revision,
  openItem,
  allItems,
}: {
  selected: string | null;
  select: (id: string) => void;
  revision: number;
  openItem: (id: string, locator?: string, version?: number) => void;
  allItems: Item[];
}) {
  const [chats, setChats] = useState<any[]>([]),
    [detail, setDetail] = useState<any>(null),
    [input, setInput] = useState(""),
    [stream, setStream] = useState(""),
    [sending, setSending] = useState(false),
    [link, setLink] = useState(false),
    [linkId, setLinkId] = useState("");
  const notice = useNotice(),
    bottom = useRef<HTMLDivElement>(null);
  const [replyMessage, setReplyMessage] = useState<{
    id: string;
    content: string;
  } | null>(null);
  const emailItems: Item[] = (detail?.items || []).filter(
    (item: Item) => item.kind === "mail" && item.available,
  );
  const load = () => {
    api<any[]>("/conversations")
      .then(setChats)
      .catch((e) => notice(e.message, true));
    if (selected)
      api("/conversations/" + selected)
        .then(setDetail)
        .catch((e) => notice(e.message, true));
  };
  useEffect(() => {
    load();
  }, [selected, revision]);
  useEffect(() => {
    if (!selected && chats.length) select(chats[0].id);
  }, [chats]);
  useEffect(() => {
    setStream("");
    setSending(false);
    setReplyMessage(null);
  }, [selected]);
  useEffect(() => {
    const listen = (event: Event) => {
      const data = (event as CustomEvent).detail;
      if (data.payload.conversation_id !== selected) return;
      if (data.kind === "chat.delta") {
        setSending(true);
        setStream((v) => v + data.payload.text);
      }
      if (data.kind === "chat.done") {
        setStream("");
        setSending(false);
        load();
      }
    };
    window.addEventListener("workagent-event", listen);
    return () => window.removeEventListener("workagent-event", listen);
  }, [selected]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [detail?.messages?.length, stream]);
  async function send(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || !selected) return;
    setSending(true);
    try {
      await api("/conversations/" + selected + "/messages", "POST", {
        content: input,
      });
      setInput("");
      load();
    } catch (e) {
      setSending(false);
      notice((e as Error).message, true);
    }
  }
  async function analyze(item: Item) {
    try {
      await api("/items/" + item.id + "/analyze", "POST");
      notice("Zusammenfassung und Vorschläge werden erstellt.");
    } catch (e) {
      notice((e as Error).message, true);
    }
  }
  return (
    <>
      <PageHeader
        eyebrow="GEMEINSAM WEITERDENKEN"
        title="Deine Arbeitschats."
        description="Ein eigener Raum für jeden Vorgang. Mit deinem Wissen im richtigen Moment."
      />
      <div className="chat-layout">
        <div className="chat-list">
          <div className="list-section-label">
            VORGÄNGE <span>{chats.length}</span>
          </div>
          {chats.map((c) => (
            <button
              key={c.id}
              className={
                "chat-list-item " + (c.id === selected ? "active" : "")
              }
              onClick={() => select(c.id)}
            >
              <MessageSquare size={17} />
              <span>
                <strong>{c.title}</strong>
                <small>{fmt(c.created_at)}</small>
              </span>
              <ChevronRight size={14} />
            </button>
          ))}
          {!chats.length && (
            <p className="padded muted-text">
              Öffne einen Vorgang aus dem Eingang oder starte einen neuen
              Arbeitschat.
            </p>
          )}
        </div>
        <div className="chat-panel">
          {!detail ? (
            <Empty
              icon={<MessageSquare />}
              title="Raum für den nächsten Schritt"
              text="Wähle einen Arbeitschat aus oder starte eine neue Unterhaltung."
            />
          ) : (
            <>
              <div className="chat-panel-head">
                <div>
                  <h2>{detail.conversation.title}</h2>
                  <span>{detail.items.length} verknüpfte Quellen</span>
                </div>
                <Button onClick={() => setLink(true)}>
                  <Link2 size={15} /> Verknüpfen
                </Button>
              </div>
              <div className="chat-scroll">
                <div className="linked-items">
                  {detail.items.map((item: Item) => (
                    <div key={item.id} className="linked-item">
                      <button onClick={() => openItem(item.id)}>
                        <Icon kind={item.kind || "document"} size={16} />
                        <span>{item.title}</span>
                        <ArrowUpRight size={14} />
                      </button>
                      {item.available && (
                        <button
                          className="text-link"
                          onClick={() => analyze(item)}
                          disabled={!item.ai_enabled}
                        >
                          <Sparkles size={14} /> Vorschläge erstellen
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                {!detail.messages.length && !detail.proposals.length && (
                  <div className="chat-intro">
                    <div className="sparkle-tile">
                      <Sparkles size={25} />
                    </div>
                    <h3>Was möchtest du voranbringen?</h3>
                    <p>
                      Stelle eine Frage, lass dir einen Entwurf erstellen oder
                      kläre die nächsten Schritte.
                    </p>
                    <div className="prompt-chips">
                      {[
                        "Was sind die nächsten Schritte?",
                        "Formuliere eine kurze Antwort.",
                        "Welches Wissen hilft mir hier?",
                      ].map((p) => (
                        <button key={p} onClick={() => setInput(p)}>
                          {p}
                          <ArrowUpRight size={14} />
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {detail.messages.map((message: any) => (
                  <div
                    key={message.id}
                    className={"chat-message " + message.role}
                  >
                    <div className="message-avatar">
                      {message.role === "assistant" ? (
                        <Sparkles size={17} />
                      ) : (
                        "DU"
                      )}
                    </div>
                    <div>
                      <div className="chat-message-label">
                        {message.role === "assistant" ? "Work Agent" : "Du"}
                        <time>{fmt(message.created_at)}</time>
                      </div>
                      <Markdown text={message.content} />
                      {message.role === "assistant" &&
                        emailItems.length > 0 && (
                          <Button onClick={() => setReplyMessage(message)}>
                            Als E-Mail-Entwurf übernehmen
                          </Button>
                        )}
                      {message.citations.length > 0 && (
                        <div className="citations">
                          {message.citations.map((c: any, n: number) => (
                            <button
                              key={n}
                              onClick={() =>
                                openItem(c.item_id, c.locator, c.version)
                              }
                            >
                              <FileText size={12} />
                              {c.title} · {c.locator}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
                {stream && (
                  <div className="chat-message assistant">
                    <div className="message-avatar">
                      <Sparkles size={17} />
                    </div>
                    <div>
                      <div className="chat-message-label">
                        Work Agent <LoaderCircle size={13} className="spin" />
                      </div>
                      <Markdown text={stream} />
                    </div>
                  </div>
                )}
                {sending && !stream && (
                  <div className="thinking">
                    <LoaderCircle size={15} className="spin" /> Dein Agent
                    arbeitet …{" "}
                    <button onClick={() => setSending(false)}>
                      Eingabe freigeben
                    </button>
                  </div>
                )}
                {detail.proposals.length > 0 && (
                  <div className="chat-proposals">
                    <div className="eyebrow">VORSCHLÄGE ZUR FREIGABE</div>
                    {detail.proposals.map((p: Proposal) => (
                      <ProposalCard
                        key={p.id}
                        proposal={p}
                        refresh={load}
                        openItem={openItem}
                      />
                    ))}
                  </div>
                )}
                <div ref={bottom} />
              </div>
              <form className="chat-composer" onSubmit={send}>
                <textarea
                  aria-label="Nachricht an den Agenten"
                  placeholder="Nachfragen, gemeinsam formulieren, weiterdenken …"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send(e);
                    }
                  }}
                />
                <div>
                  <span>
                    <ShieldCheck size={13} /> Aktionen werden erst nach deiner
                    Freigabe ausgeführt.
                  </span>
                  <Button
                    kind="primary"
                    type="submit"
                    disabled={!input.trim() || sending}
                  >
                    <Send size={16} />
                    <span>Senden</span>
                  </Button>
                </div>
              </form>
            </>
          )}
        </div>
      </div>
      {replyMessage && selected && (
        <EmailReplyDraft
          conversationId={selected}
          message={replyMessage}
          items={emailItems}
          close={() => setReplyMessage(null)}
          saved={load}
        />
      )}
      {link && (
        <Modal
          title="Quelle mit diesem Vorgang verknüpfen"
          onClose={() => setLink(false)}
        >
          <label>
            Nachricht oder Dokument
            <select value={linkId} onChange={(e) => setLinkId(e.target.value)}>
              <option value="">Bitte auswählen</option>
              {allItems
                .filter((i) => !detail.items.some((j: Item) => j.id === i.id))
                .map((i) => (
                  <option key={i.id} value={i.id}>
                    {labels[i.kind]} · {i.title}
                  </option>
                ))}
            </select>
          </label>
          <div className="modal-actions">
            <Button
              kind="primary"
              disabled={!linkId}
              onClick={async () => {
                try {
                  await api("/conversations/" + selected, "PATCH", {
                    title: detail.conversation.title,
                    item_ids: [linkId],
                  });
                  setLink(false);
                  load();
                } catch (e) {
                  notice((e as Error).message, true);
                }
              }}
            >
              Verknüpfen
            </Button>
          </div>
        </Modal>
      )}
    </>
  );
}
