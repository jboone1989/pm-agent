from datetime import date, datetime
from typing import Optional

from sqlmodel import Session, select

from app.models import WorkLog
from app.schemas import WorkLogCreate, WorkLogUpdate
from app.services.operation_log import record_work_log


def create_work_log(session: Session, data: WorkLogCreate) -> WorkLog:
    log_date = data.log_date or date.today()
    work_log = WorkLog(
        content=data.content,
        duration_minutes=data.duration_minutes,
        log_date=log_date,
        work_item_id=data.work_item_id,
    )
    session.add(work_log)
    session.commit()
    session.refresh(work_log)
    record_work_log(session, work_log)
    return work_log


def get_work_log(session: Session, log_id: int) -> Optional[WorkLog]:
    return session.get(WorkLog, log_id)


def list_work_logs(
    session: Session,
    log_date: Optional[date] = None,
    limit: int = 50,
) -> list[WorkLog]:
    query = select(WorkLog)
    if log_date:
        query = query.where(WorkLog.log_date == log_date)
    query = query.order_by(WorkLog.created_at.desc()).limit(limit)
    return list(session.exec(query).all())


def update_work_log(
    session: Session, log_id: int, data: WorkLogUpdate
) -> Optional[WorkLog]:
    work_log = session.get(WorkLog, log_id)
    if not work_log:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(work_log, key, value)
    work_log.updated_at = datetime.utcnow()
    session.commit()
    session.refresh(work_log)
    return work_log


def delete_work_log(session: Session, log_id: int) -> bool:
    work_log = session.get(WorkLog, log_id)
    if not work_log:
        return False
    session.delete(work_log)
    session.commit()
    return True


def get_work_log_stats(
    session: Session, log_date: date
) -> dict:
    logs = session.exec(
        select(WorkLog).where(WorkLog.log_date == log_date)
    ).all()
    total_minutes = sum(
        wl.duration_minutes for wl in logs if wl.duration_minutes
    )
    return {
        "date": log_date.isoformat(),
        "count": len(logs),
        "total_minutes": total_minutes,
    }
