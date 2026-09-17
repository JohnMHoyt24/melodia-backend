import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.core.db import get_db
from app.models.chat import ChatThread
from app.schemas.chat import ChatMessageCreate, ChatMessageRead, ChatThreadDetail, ChatThreadSummary
from app.services.chat import create_thread, send_message

router = APIRouter(prefix="/chat", tags=["chat"])


def _get_owned_thread(db: Session, thread_id: uuid.UUID, user_id: uuid.UUID) -> ChatThread:
    thread = db.get(ChatThread, thread_id)
    if thread is None or thread.user_id != user_id:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


@router.get("/threads", response_model=list[ChatThreadSummary])
def list_threads(
    db: Session = Depends(get_db), user_id: uuid.UUID = Depends(get_current_user_id)
) -> list[ChatThread]:
    return list(
        db.query(ChatThread)
        .filter(ChatThread.user_id == user_id)
        .order_by(desc(ChatThread.updated_at))
        .all()
    )


@router.post("/threads", response_model=ChatThreadDetail, status_code=201)
def start_thread(
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> ChatThread:
    """Create a new thread and run its first turn - no empty thread exists until the

    first message is sent, matching ChatGPT/Claude. Synchronous and can take a while,
    same as the old /recommend - see app/services/gemini.py.
    """
    return create_thread(db, user_id, payload.message)


@router.get("/threads/{thread_id}", response_model=ChatThreadDetail)
def get_thread(
    thread_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> ChatThread:
    return _get_owned_thread(db, thread_id, user_id)


@router.post("/threads/{thread_id}/messages", response_model=ChatMessageRead)
def post_message(
    thread_id: uuid.UUID,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
):
    thread = _get_owned_thread(db, thread_id, user_id)
    return send_message(db, thread, payload.message)


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(
    thread_id: uuid.UUID,
    db: Session = Depends(get_db),
    user_id: uuid.UUID = Depends(get_current_user_id),
) -> None:
    thread = _get_owned_thread(db, thread_id, user_id)
    db.delete(thread)
    db.commit()
