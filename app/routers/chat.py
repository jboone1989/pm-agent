from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.schemas import ChatRequest, ChatResponse
from app.services import agent as agent_service
from app.services import operation_log as op_log

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, session: Session = Depends(get_session)):
    reply, actions, changed_ids = agent_service.run_agent(session, payload.message)
    op_log.record_chat(session, payload.message, reply, actions)
    return ChatResponse(reply=reply, actions=actions, changed_item_ids=changed_ids)
