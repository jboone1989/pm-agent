from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
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


@router.post("/stream")
def chat_stream(payload: ChatRequest, session: Session = Depends(get_session)):
    def generate():
        reply = ""
        actions = []
        changed_ids = []
        for sse in agent_service.run_agent_stream(session, payload.message):
            # Track the final reply, actions, and ids from the done event
            if sse.startswith("event: done"):
                import json as _json
                for line in sse.split("\n"):
                    if line.startswith("data: "):
                        data = _json.loads(line[6:])
                        reply = data.get("reply", "")
                        actions = data.get("actions", [])
                        changed_ids = data.get("changed_item_ids", [])
            yield sse
        # Record operation log after streaming completes
        if reply or actions:
            op_log.record_chat(session, payload.message, reply, actions)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
