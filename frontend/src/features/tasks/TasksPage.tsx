import { useState, useEffect } from "react";
import { CheckCheck, Plus, Sparkles, Check, Clock } from "lucide-react";
import { api, Source, Item, Proposal } from "../../api";
import { fmt } from "../../shared/presentation";
import { useNotice } from "../../shared/notifications";
import { Button, Badge, Empty, PageHeader } from "../../shared/ui";
import { ProposalCard } from "../proposals/ProposalCard";
import { ProposalEditor } from "../proposals/ProposalEditor";

export function TasksPage({
  items,
  sources,
  revision,
  refresh,
}: {
  items: Item[];
  sources: Source[];
  revision: number;
  refresh: () => void;
}) {
  const [filter, setFilter] = useState("open"),
    [sourceFilter, setSourceFilter] = useState(""),
    [editor, setEditor] = useState<Proposal | null>(null),
    [proposals, setProposals] = useState<Proposal[]>([]);
  const notice = useNotice();
  useEffect(() => {
    api<Proposal[]>("/proposals")
      .then((p) =>
        setProposals(
          p.filter((x) => x.kind.includes("task") && x.status !== "rejected"),
        ),
      )
      .catch((e) => notice(e.message, true));
  }, [revision]);
  const shown = items.filter(
    (i) =>
      (!sourceFilter || i.source_id === sourceFilter) &&
      (filter === "all" ||
        (filter === "done" ? i.status === "done" : i.status !== "done")),
  );
  return (
    <>
      <PageHeader
        eyebrow="VON GEDANKEN ZU NÄCHSTEN SCHRITTEN"
        title="Deine Aufgaben."
        description="Offene Punkte festhalten, Verantwortung übernehmen und Dinge abschließen."
        action={
          <Button
            kind="primary"
            onClick={() =>
              setEditor({
                id: "",
                kind: "create_task",
                payload: { title: "", body: "" },
                version: 1,
                status: "draft",
                result: {},
                citations: [],
              })
            }
          >
            <Plus size={16} /> Neue Aufgabe
          </Button>
        }
      />
      <div className="tabs standalone">
        {[
          ["open", "Offen"],
          ["done", "Erledigt"],
          ["all", "Alle Aufgaben"],
        ].map(([id, label]) => (
          <button
            key={id}
            onClick={() => setFilter(id)}
            className={filter === id ? "selected" : ""}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="task-layout">
        <section className="surface">
          <label>
            Aufgabenbereich
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
            >
              <option value="">Alle Bereiche</option>
              {sources
                .filter((s) =>
                  [
                    "todo",
                    "local_tasks",
                    "crm_effort",
                    "crm_office",
                    "crm_sales",
                    "crm_ticket",
                  ].includes(s.kind),
                )
                .map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
            </select>
          </label>
          <div className="list-section-label">
            MEINE AUFGABEN <span>{shown.length}</span>
          </div>
          {shown.map((item) => (
            <div className="task-row" key={item.id}>
              <button
                className={
                  "task-check " + (item.status === "done" ? "checked" : "")
                }
                aria-label={"Aufgabe abschließen: " + item.title}
                disabled={item.status === "done"}
                onClick={async () => {
                  if (
                    item.source_kind === "todo" ||
                    item.source_kind.startsWith("crm_")
                  ) {
                    setEditor({
                      id: "",
                      kind: "complete_task",
                      payload: {
                        source_id: item.source_id,
                        item_id: item.id,
                        title: item.title,
                        crm_updated_at: item.meta.crm_updated_at,
                      },
                      version: 1,
                      status: "draft",
                      result: {},
                      citations: [],
                    });
                    return;
                  }
                  try {
                    await api("/items/" + item.id, "PATCH", { status: "done" });
                    refresh();
                  } catch (e) {
                    notice((e as Error).message, true);
                  }
                }}
              >
                {item.status === "done" && <Check size={14} />}
              </button>
              <div>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
                <div className="row">
                  <Badge>{item.source_name}</Badge>
                  {item.meta.crm_status_label && (
                    <Badge kind={item.status === "done" ? "green" : "orange"}>
                      {item.meta.crm_status_label}
                    </Badge>
                  )}
                  {item.source_kind.startsWith("crm_") && item.web_url && (
                    <a href={item.web_url} target="_blank" rel="noreferrer">
                      Im CRM öffnen
                    </a>
                  )}
                  {item.meta.due && (
                    <span className="due">
                      <Clock size={12} />
                      {fmt(
                        typeof item.meta.due === "string"
                          ? item.meta.due
                          : item.meta.due.dateTime,
                      )}
                    </span>
                  )}
                </div>
              </div>
              {(item.source_kind === "todo" ||
                item.source_kind.startsWith("crm_")) && (
                <Button
                  onClick={() =>
                    setEditor({
                      id: "",
                      kind: "update_task",
                      payload: {
                        source_id: item.source_id,
                        item_id: item.id,
                        title: item.title,
                        body: item.body,
                        crm_updated_at: item.meta.crm_updated_at,
                        crm_status: item.meta.crm_status,
                        due:
                          item.source_kind === "crm_ticket"
                            ? typeof item.meta.due === "string"
                              ? item.meta.due
                              : item.meta.due?.dateTime
                            : (typeof item.meta.due === "string"
                                ? item.meta.due
                                : item.meta.due?.dateTime
                              )?.slice(0, 10),
                      },
                      version: 1,
                      status: "draft",
                      result: {},
                      citations: [],
                    })
                  }
                >
                  Bearbeiten
                </Button>
              )}
            </div>
          ))}
          {!shown.length && (
            <Empty
              icon={<CheckCheck />}
              title="Ein guter Platz für deine nächsten Schritte"
              text="Erstelle eine Aufgabe oder übernimm einen Vorschlag aus einem Arbeitschat."
            />
          )}
        </section>
        <aside>
          <div className="section-heading">
            <h2>Vorgeschlagene Aufgaben</h2>
            <Badge>
              {proposals.filter((p) => p.status === "draft").length}
            </Badge>
          </div>
          {proposals.slice(0, 20).map((p) => (
            <ProposalCard key={p.id} proposal={p} refresh={refresh} />
          ))}
          {!proposals.length && (
            <div className="small-note">
              <Sparkles size={22} />
              <p>
                Aufgabenvorschläge aus deinen Nachrichten warten hier auf deine
                Freigabe.
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
