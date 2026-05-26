import re
from datetime import date, datetime
from typing import Optional

from sqlmodel import Session, select

from app.models import ActivityLog, ActivitySource, OperationAction, WorkItem, WorkItemStatus, WorkItemType
from app.schemas import WorkItemCreate, WorkItemUpdate
from app.services import operation_log as op_log
from app.services.operation_log import describe_update


def touch(item: WorkItem) -> None:
    item.updated_at = datetime.utcnow()


def normalize_progress(item: WorkItem) -> None:
    item.progress = max(0, min(100, item.progress or 0))
    if item.progress >= 100:
        item.progress = 100
        item.status = WorkItemStatus.done
    elif item.progress > 0 and item.status == WorkItemStatus.todo:
        item.status = WorkItemStatus.in_progress


def normalize_dates(start_date: Optional[date], due_date: Optional[date]) -> tuple[date, Optional[date]]:
    today = date.today()
    start = start_date or today
    due = due_date
    if due is not None and due < start:
        due = start
    return start, due


def create_work_item(session: Session, data: WorkItemCreate) -> WorkItem:
    start, due = normalize_dates(data.start_date, data.due_date)
    payload = data.model_copy(update={"start_date": start, "due_date": due})
    item = WorkItem.model_validate(payload)
    normalize_progress(item)
    session.add(item)
    session.commit()
    session.refresh(item)
    op_log.record_create(session, item)
    return item


def update_work_item(session: Session, item_id: int, data: WorkItemUpdate) -> Optional[WorkItem]:
    item = session.get(WorkItem, item_id)
    if not item:
        return None
    change_summary = describe_update(item, data)
    fields = data.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(item, key, value)
    if "start_date" in fields or "due_date" in fields:
        item.start_date, item.due_date = normalize_dates(item.start_date, item.due_date)
    normalize_progress(item)
    touch(item)
    session.add(item)
    session.commit()
    session.refresh(item)
    op_log.record_operation(
        session,
        OperationAction.update,
        f"更新「{item.title}」：{change_summary}",
        work_item_id=item.id,
        work_item_title=item.title,
    )
    return item


def delete_work_item(session: Session, item_id: int, log: bool = True) -> bool:
    item = session.get(WorkItem, item_id)
    if not item:
        return False
    if log:
        op_log.record_delete(session, item)
    children = session.exec(select(WorkItem).where(WorkItem.parent_id == item_id)).all()
    for child in children:
        delete_work_item(session, child.id, log=False)
    logs = session.exec(select(ActivityLog).where(ActivityLog.work_item_id == item_id)).all()
    for log in logs:
        session.delete(log)
    session.delete(item)
    session.commit()
    return True


def add_activity(
    session: Session,
    work_item_id: int,
    content: str,
    source: ActivitySource = ActivitySource.user_message,
) -> Optional[ActivityLog]:
    item = session.get(WorkItem, work_item_id)
    if not item:
        return None
    log = ActivityLog(work_item_id=work_item_id, content=content, source=source)
    touch(item)
    session.add(log)
    session.add(item)
    session.commit()
    session.refresh(log)
    return log


def search_work_items(
    session: Session,
    query: str = "",
    assignee: Optional[str] = None,
    status: Optional[WorkItemStatus] = None,
    type: Optional[WorkItemType] = None,
    limit: int = 20,
) -> list[WorkItem]:
    raw = query.strip()
    if raw:
        id_match = re.search(r"#?(\d+)", raw)
        if id_match and (raw.isdigit() or raw.startswith("#") or "「" in raw or len(raw) <= 8):
            item = session.get(WorkItem, int(id_match.group(1)))
            if item:
                return [item]

    statement = select(WorkItem)
    if raw:
        like = f"%{raw}%"
        statement = statement.where(
            (WorkItem.title.like(like)) | (WorkItem.description.like(like))
        )
    if assignee:
        statement = statement.where(WorkItem.assignee == assignee)
    if status:
        statement = statement.where(WorkItem.status == status)
    if type:
        statement = statement.where(WorkItem.type == type)
    statement = statement.order_by(WorkItem.updated_at.desc()).limit(limit)
    return list(session.exec(statement).all())


def list_all_work_items(session: Session) -> list[WorkItem]:
    return list(session.exec(select(WorkItem).order_by(WorkItem.updated_at.desc())).all())


def get_work_item(session: Session, item_id: int) -> Optional[WorkItem]:
    return session.get(WorkItem, item_id)


def list_assignees(session: Session) -> list[str]:
    items = session.exec(
        select(WorkItem.assignee)
        .where(WorkItem.assignee.is_not(None))
        .where(WorkItem.assignee != "")
        .distinct()
    ).all()
    return sorted({value for value in items if value})


def get_activity_logs(session: Session, work_item_id: int) -> list[ActivityLog]:
    statement = (
        select(ActivityLog)
        .where(ActivityLog.work_item_id == work_item_id)
        .order_by(ActivityLog.created_at.desc())
    )
    return list(session.exec(statement).all())


def get_root_item(session: Session, item: WorkItem) -> WorkItem:
    current = item
    while current.parent_id:
        parent = session.get(WorkItem, current.parent_id)
        if not parent:
            break
        current = parent
    return current


def split_work_item(session: Session, parent_id: int, children: list[WorkItemCreate]) -> list[WorkItem]:
    parent = session.get(WorkItem, parent_id)
    if not parent:
        return []
    created: list[WorkItem] = []
    for child_data in children:
        payload = child_data.model_copy(update={"parent_id": parent_id})
        created.append(create_work_item(session, payload))
    return created
