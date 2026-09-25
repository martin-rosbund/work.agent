from fastapi import HTTPException
from sqlalchemy import select

from app import actions
from app.models import (
    Proposal,
)
from app.services import (
    serialize,
    visible_item,
)

from .schemas import ProposalInput, VersionInput

PREFIX = "/api/v1"


def create_proposal(body: ProposalInput, session=None, db=None):
    if body.item_id:
        visible_item(db, body.item_id)
    row = Proposal(
        kind=body.kind,
        payload=actions.validate_payload(body.kind, body.payload),
        item_id=body.item_id,
        conversation_id=body.conversation_id,
    )
    db.add(row)
    db.commit()
    return serialize(row)


def proposals(session=None, db=None):
    return [
        serialize(p)
        for p in db.scalars(
            select(Proposal).order_by(Proposal.created_at.desc()).limit(200)
        )
    ]


def edit_proposal(proposal_id: str, body: ProposalInput, session=None, db=None):
    row = db.scalar(
        select(Proposal).where(Proposal.id == proposal_id).with_for_update()
    )
    if not row or row.status != "draft" or row.version != body.version:
        raise HTTPException(
            409, "Vorschlag ist nicht mehr in dieser Version bearbeitbar."
        )
    if row.kind != body.kind:
        raise HTTPException(400, "Aktionstyp kann nicht geändert werden.")
    row.payload = actions.validate_payload(row.kind, body.payload)
    row.version += 1
    row.approved_hash = None
    db.commit()
    return serialize(row)


def approve_proposal(proposal_id: str, body: VersionInput, session=None, db=None):
    row = actions.approve(db, proposal_id, body.version)
    db.commit()
    return serialize(row)


def reject_proposal(proposal_id: str, body: VersionInput, session=None, db=None):
    row = db.scalar(
        select(Proposal).where(Proposal.id == proposal_id).with_for_update()
    )
    if not row or row.status != "draft" or row.version != body.version:
        raise HTTPException(409, "Vorschlag ist nicht mehr verwerfbar.")
    row.status = "rejected"
    db.commit()
    return {"ok": True}
