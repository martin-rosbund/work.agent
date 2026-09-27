from fastapi import APIRouter

from app.api.dependencies import DB, Auth
from app.api.schemas import *

from . import service
from .schemas import ChatInput, ConversationInput, EmailReplyDraftInput, ArchiveInput

router = APIRouter(tags=["chats"])
PREFIX = "/api/v1"


@router.post(PREFIX + "/conversations/{conversation_id}/email-reply-draft", response_model=ProposalView)
def email_reply_draft(conversation_id: str, body: EmailReplyDraftInput, session=Auth, db=DB):
    from .email_reply import create_email_reply

    return create_email_reply(db, conversation_id, body)


@router.get(PREFIX + "/conversations", response_model=list[ConversationView])
def conversations(archived: bool = False, session=Auth, db=DB):
    return service.conversations(session=session, db=db, archived=archived)


@router.patch(PREFIX + "/conversations/{conversation_id}/archive", response_model=ConversationView)
def archive_conversation(conversation_id: str, body: ArchiveInput, session=Auth, db=DB):
    return service.archive_conversation(conversation_id, body.archived, db)


@router.delete(PREFIX + "/conversations/{conversation_id}", response_model=Ok)
def delete_conversation(conversation_id: str, session=Auth, db=DB):
    return service.delete_conversation(conversation_id, db)


@router.post(PREFIX + "/conversations", response_model=ConversationView)
def create_conversation(body: ConversationInput, session=Auth, db=DB):
    return service.create_conversation(body=body, session=session, db=db)


@router.patch(
    PREFIX + "/conversations/{conversation_id}", response_model=ConversationView
)
def link_conversation(
    conversation_id: str, body: ConversationInput, session=Auth, db=DB
):
    return service.link_conversation(
        conversation_id=conversation_id, body=body, session=session, db=db
    )


@router.get(
    PREFIX + "/conversations/{conversation_id}", response_model=ConversationDetail
)
def conversation_detail(conversation_id: str, session=Auth, db=DB):
    return service.conversation_detail(
        conversation_id=conversation_id, session=session, db=db
    )


@router.post(PREFIX + "/conversations/{conversation_id}/messages", response_model=Ok)
def chat_message(conversation_id: str, body: ChatInput, session=Auth, db=DB):
    return service.chat_message(
        conversation_id=conversation_id, body=body, session=session, db=db
    )
