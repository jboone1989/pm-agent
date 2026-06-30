from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.schemas import WorkLogCreate, WorkLogRead, WorkLogUpdate
from app.services import work_logs as work_log_service

router = APIRouter(prefix="/api/work-logs", tags=["work-logs"])


@router.get("", response_model=list[WorkLogRead])
def list_logs(
    log_date: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    parsed_date = None
    if log_date:
        try:
            parts = [int(x) for x in log_date.split("-")]
            parsed_date = date(*parts)
        except (ValueError, TypeError):
            raise HTTPException(400, "日期格式应为 YYYY-MM-DD")
    return work_log_service.list_work_logs(session, log_date=parsed_date, limit=limit)


@router.get("/today", response_model=list[WorkLogRead])
def list_today_logs(session: Session = Depends(get_session)):
    return work_log_service.list_work_logs(session, log_date=date.today(), limit=50)


@router.get("/stats")
def get_stats(
    log_date: Optional[str] = None,
    session: Session = Depends(get_session),
):
    if not log_date:
        log_date = date.today().isoformat()
    try:
        parts = [int(x) for x in log_date.split("-")]
        parsed_date = date(*parts)
    except (ValueError, TypeError):
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD")
    return work_log_service.get_work_log_stats(session, parsed_date)


@router.get("/{log_id}", response_model=WorkLogRead)
def get_log(log_id: int, session: Session = Depends(get_session)):
    work_log = work_log_service.get_work_log(session, log_id)
    if not work_log:
        raise HTTPException(404, "日志不存在")
    return work_log


@router.post("", response_model=WorkLogRead)
def create_log(data: WorkLogCreate, session: Session = Depends(get_session)):
    return work_log_service.create_work_log(session, data)


@router.patch("/{log_id}", response_model=WorkLogRead)
def update_log(log_id: int, data: WorkLogUpdate, session: Session = Depends(get_session)):
    work_log = work_log_service.update_work_log(session, log_id, data)
    if not work_log:
        raise HTTPException(404, "日志不存在")
    return work_log


@router.delete("/{log_id}")
def delete_log(log_id: int, session: Session = Depends(get_session)):
    ok = work_log_service.delete_work_log(session, log_id)
    if not ok:
        raise HTTPException(404, "日志不存在")
    return {"ok": True}
