import { useEffect, useState } from "react";
import { api } from "../../api";

type Choice = { value: string; label: string; closed: boolean };
type Options = Record<string, Choice[]>;

export function CrmFields({
  kind,
  action,
  payload,
  change,
}: {
  kind: string;
  action: string;
  payload: Record<string, any>;
  change: (key: string, value: any) => void;
}) {
  const [options, setOptions] = useState<Options | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setOptions(null);
    setError("");
    api<Options>("/crm/options/" + kind)
      .then((o) => {
        if (active) setOptions(o);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [kind]);
  if (error) return <p className="error-inline">{error}</p>;
  if (!options) return <p>CRM-Auswahlwerte werden geladen …</p>;
  const fields = [
    ["crm_status", "statuses", "CRM-Status"],
    ["crm_category", "categories", "Kategorie"],
    [
      "crm_type",
      "types",
      kind === "crm_sales"
        ? "Vertriebsphase"
        : kind === "crm_ticket"
          ? "Ticketart"
          : "Terminart",
    ],
    ["crm_forecast", "forecasts", "Forecast"],
    [
      "crm_origin",
      "origins",
      kind === "crm_ticket"
        ? "Ticket-Herkunft"
        : "Herkunft der Verkaufschance (Pflicht beim Anlegen)",
    ],
    [
      "crm_loss_reason",
      "loss_reasons",
      "Verlustgrund (falls vom CRM-Status benötigt)",
    ],
    ["crm_priority", "priorities", "Ticket-Priorität"],
  ];
  return (
    <>
      {fields.map(([field, catalog, label]) => {
        const values = (options[catalog] || []).filter(
          (v) =>
            action !== "complete_task" || catalog !== "statuses" || v.closed,
        );
        if (
          !values.length ||
          (action === "complete_task" &&
            !["crm_status", "crm_loss_reason"].includes(field))
        )
          return null;
        return (
          <label key={field}>
            {label}
            <select
              value={payload[field] || ""}
              onChange={(e) => change(field, e.target.value || null)}
            >
              <option value="">
                {action === "complete_task"
                  ? "Bitte auswählen"
                  : "CRM-Vorgabe / unverändert"}
              </option>
              {values.map((v) => (
                <option key={v.value} value={v.value}>
                  {v.label}
                </option>
              ))}
            </select>
          </label>
        );
      })}
      {kind === "crm_office" && (
        <p className="field-help">
          Office Tasks besitzen kein Fälligkeitsdatum. Plane bei Bedarf einen
          separaten CRM-Termin.
        </p>
      )}
      {kind === "crm_event" && (
        <p className="field-help">
          Teilnehmer, Einladungen und Terminserien verwaltest du direkt im CRM.
        </p>
      )}
    </>
  );
}
