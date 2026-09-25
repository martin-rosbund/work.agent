from fastapi import APIRouter

from app.api.dependencies import DB, Auth
from app.api.schemas import *

from . import service
from .schemas import ProposalInput, VersionInput

router = APIRouter(tags=["proposals"])
PREFIX = "/api/v1"


@router.post(PREFIX + "/proposals", response_model=ProposalView)
def create_proposal(body: ProposalInput, session=Auth, db=DB):
    return service.create_proposal(body=body, session=session, db=db)


@router.get(PREFIX + "/proposals", response_model=list[ProposalView])
def proposals(session=Auth, db=DB):
    return service.proposals(session=session, db=db)


@router.put(PREFIX + "/proposals/{proposal_id}", response_model=ProposalView)
def edit_proposal(proposal_id: str, body: ProposalInput, session=Auth, db=DB):
    return service.edit_proposal(
        proposal_id=proposal_id, body=body, session=session, db=db
    )


@router.post(PREFIX + "/proposals/{proposal_id}/approve", response_model=ProposalView)
def approve_proposal(proposal_id: str, body: VersionInput, session=Auth, db=DB):
    return service.approve_proposal(
        proposal_id=proposal_id, body=body, session=session, db=db
    )


@router.post(PREFIX + "/proposals/{proposal_id}/reject", response_model=Ok)
def reject_proposal(proposal_id: str, body: VersionInput, session=Auth, db=DB):
    return service.reject_proposal(
        proposal_id=proposal_id, body=body, session=session, db=db
    )
