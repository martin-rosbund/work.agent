from fastapi import APIRouter

from app.api.dependencies import DB, Auth
from app.api.schemas import *

from . import service
from .schemas import ChatInput, ConversationInput

router = APIRouter(tags=["chats"])
PREFIX = "/api/v1"


@router.get(PREFIX + "/conversations", response_model=list[ConversationView])
def conversations(session=Auth, db=DB):
    return service.conversations(session=session, db=db)


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
