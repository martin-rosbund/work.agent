"""Explicit entity contracts; never infer an arbitrary CRM table from model output."""

TYPES = {
    "crm_ticket": {
        "entity": "ticket",
        "label": "CRM · Tickets",
        "owner": "assigneePerson",
        "body": "problemDescription",
        "due": "deadlineDate",
        "status": "status",
        "catalog": "ticketStatus",
    },
    "crm_event": {
        "entity": "event",
        "label": "CRM · Kalender",
        "owner": "assigneePerson",
        "body": "description",
        "status": "status",
        "catalog": "eventStatus",
    },
    "crm_effort": {
        "entity": "effortEstimate",
        "label": "CRM · Aufwandsschätzungen",
        "owner": "assigneePerson",
        "body": "requirementsMarkdown",
        "due": "expectedCompletionDate",
        "status": "status",
        "catalog": "effortEstimateStatus",
    },
    "crm_office": {
        "entity": "internalCase",
        "label": "CRM · Office Tasks",
        "owner": "responsiblePerson",
        "body": "requestMarkdown",
        "status": "status",
        "catalog": "internalCaseStatus",
    },
    "crm_sales": {
        "entity": "salesOpportunity",
        "label": "CRM · Verkaufschancen",
        "owner": "assigneePerson",
        "body": "description",
        "due": "closeDate",
        "status": "resultStatus",
        "catalog": "salesOpportunityResultStatus",
    },
}
TASK_KINDS = {"crm_effort", "crm_office", "crm_sales", "crm_ticket"}


def handle(value):
    return str(value.get("handle", "")) if isinstance(value, dict) else str(value or "")


def personal_filter(kind, person, *, writable=False):
    if kind == "crm_event" and not writable:
        return {
            "$or": [{"assigneePerson": person}, {"participants": {"handle": person}}]
        }
    return {TYPES[kind]["owner"]: person}


def status_closed(kind, row):
    if isinstance(row.get("isClosed"), bool):
        return row["isClosed"]
    return row.get("isOpen") is False
