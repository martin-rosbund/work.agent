import { useState, useEffect } from "react";
import { CalendarDays, Plus, ArrowUpRight, Clock } from "lucide-react";
import { DateTime } from "luxon";
import { api, Source, Item, Proposal } from "../../api";
import { fmt } from "../../shared/presentation";
import { useNotice } from "../../shared/notifications";
import { Button, Badge, Empty, PageHeader } from "../../shared/ui";
import { ProposalCard } from "../proposals/ProposalCard";
import { ProposalEditor } from "../proposals/ProposalEditor";

export function CalendarPage({
  items,
  sources,
  revision,
  refresh,
  open,
}: {
  items: Item[];
  sources: Source[];
  revision: number;
  refresh: () => void;
  open: (i: Item) => void;
}) {
  const [editor, setEditor] = useState<Proposal | null>(null),
    [filter, setFilter] = useState("open"),
    [proposals, setProposals] = useState<Proposal[]>([]);
  const notice = useNotice();
  useEffect(() => {
    api<Proposal[]>("/proposals")
      .then((p) =>
        setProposals(
          p.filter(
            (x) =>
              ["create_event", "update_event"].includes(x.kind) &&
              x.status !== "rejected",
          ),
        ),
      )
      .catch((e) => notice(e.message, true));
  }, [revision]);
  return (
    <>
      <PageHeader
        eyebrow="ZEIT FÜR DAS WESENTLICHE"
        title="Dein Kalender."
        description="Termine im Blick behalten und Zeit für die nächsten Schritte finden."
        action={
          <Button
            kind="primary"
            disabled={
              !sources.some(
                (s) =>
                  ["calendar", "crm_event"].includes(s.kind) &&
                  s.enabled &&
                  s.writable,
              )
            }
            onClick={() =>
              setEditor({
                id: "",
                kind: "create_event",
                payload: {
                  source_id: sources.find(
                    (s) =>
                      ["calendar", "crm_event"].includes(s.kind) &&
                      s.enabled &&
                      s.writable,
                  )?.id,
                  subject: "",
                  body: "",
                  attendees: [],
                },
                version: 1,
                status: "draft",
                result: {},
                citations: [],
              })
            }
          >
            <Plus size={16} /> Termin vorschlagen
          </Button>
        }
      />
      <div className="task-layout">
        <section className="surface">
          <div className="list-section-label">
            AGENDA <span>Europe/Berlin</span>
          </div>
          <label>
            Terminstatus
            <select value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="open">Offen</option>
              <option value="done">Abgeschlossen</option>
              <option value="all">Alle</option>
            </select>
          </label>
          {items
            .filter(
              (i) =>
                filter === "all" ||
                (filter === "done" ? i.status === "done" : i.status !== "done"),
            )
            .sort((a, b) => a.occurred_at.localeCompare(b.occurred_at))
            .map((i) => (
              <button
                className="calendar-row"
                key={i.id}
                onClick={() => {
                  if (
                    i.source_kind === "crm_event" &&
                    !i.meta.recurrence &&
                    sources.some((s) => s.id === i.source_id && s.writable)
                  ) {
                    setEditor({
                      id: "",
                      kind: "update_event",
                      payload: {
                        source_id: i.source_id,
                        item_id: i.id,
                        subject: i.title,
                        body: i.body,
                        start: i.meta.start?.dateTime,
                        end: i.meta.end?.dateTime,
                        crm_updated_at: i.meta.crm_updated_at,
                        crm_status: i.meta.crm_status,
                      },
                      version: 1,
                      status: "draft",
                      result: {},
                      citations: [],
                    });
                  } else open(i);
                }}
              >
                <div className="calendar-date">
                  <strong>
                    {
                      DateTime.fromISO(i.occurred_at, { zone: "utc" }).setZone(
                        "Europe/Berlin",
                      ).day
                    }
                  </strong>
                  <span>
                    {DateTime.fromISO(i.occurred_at, { zone: "utc" })
                      .setZone("Europe/Berlin")
                      .setLocale("de")
                      .toFormat("MMM")}
                  </span>
                </div>
                <div>
                  <h3>{i.title}</h3>
                  <p>
                    <Clock size={13} />
                    {fmt(i.meta.start?.dateTime)} – {fmt(i.meta.end?.dateTime)}
                  </p>
                  <small>{i.source_name}</small>
                  {i.meta.crm_status_label && (
                    <Badge kind={i.status === "done" ? "green" : "orange"}>
                      {i.meta.crm_status_label}
                    </Badge>
                  )}
                  {i.meta.recurrence && (
                    <small>Terminserie · im CRM bearbeiten</small>
                  )}
                </div>
                <ArrowUpRight size={18} />
              </button>
            ))}
          {!items.length && (
            <Empty
              icon={<CalendarDays />}
              title="Deine Termine kommen hier zusammen"
              text="Verbinde einen Outlook- oder CRM-Kalender in den Einstellungen. Terminvorschläge bestätigst du vor dem Anlegen."
            />
          )}
        </section>
        <aside>
          <div className="section-heading">
            <h2>Terminvorschläge</h2>
          </div>
          {proposals.map((p) => (
            <ProposalCard key={p.id} proposal={p} refresh={refresh} />
          ))}
          {!proposals.length && (
            <div className="small-note">
              <CalendarDays size={22} />
              <p>
                Aus einem Arbeitschat kann ein konkreter Terminvorschlag werden
                — mit Zeit, Teilnehmern und deiner Freigabe.
              </p>
            </div>
          )}
        </aside>
      </div>
      {editor && (
        <ProposalEditor
          proposal={editor}
          sources={sources}
          close={() => setEditor(null)}
          saved={refresh}
        />
      )}
    </>
  );
}
