from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from app.models import ActivityLog, OperationAction, OperationLog, WorkItem
from app.schemas import WorkItemUpdate

FIELD_LABELS = {
    "title": "标题",
    "description": "描述",
    "status": "状态",
    "assignee": "负责人",
    "start_date": "开始日期",
    "due_date": "截止日期",
    "priority": "优先级",
    "progress": "进度",
    "type": "类型",
}


def week_key_from_dt(value: datetime | None = None) -> str:
    current = value or datetime.utcnow()
    iso = current.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def parse_week_key(week_key: str) -> tuple[date, date]:
    year_str, week_str = week_key.split("-W")
    start = date.fromisocalendar(int(year_str), int(week_str), 1)
    end = start + timedelta(days=6)
    return start, end


def week_label(week_key: str) -> str:
    start, end = parse_week_key(week_key)
    return f"{week_key}（{start.month}/{start.day} - {end.month}/{end.day}）"


def shift_week_key(week_key: str, offset: int) -> str:
    start, _ = parse_week_key(week_key)
    target = datetime.combine(start, datetime.min.time()) + timedelta(weeks=offset)
    return week_key_from_dt(target)


def record_operation(
    session: Session,
    action: OperationAction,
    message: str,
    work_item_id: int | None = None,
    work_item_title: str = "",
    created_at: datetime | None = None,
) -> OperationLog:
    timestamp = created_at or datetime.utcnow()
    entry = OperationLog(
        week_key=week_key_from_dt(timestamp),
        action=action,
        work_item_id=work_item_id,
        work_item_title=work_item_title,
        message=message,
        created_at=timestamp,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def describe_update(item: WorkItem, data: WorkItemUpdate) -> str:
    parts: list[str] = []
    for key, value in data.model_dump(exclude_unset=True).items():
        old_value = getattr(item, key)
        if old_value == value:
            continue
        label = FIELD_LABELS.get(key, key)
        parts.append(f"{label} {old_value} → {value}")
    return "；".join(parts) if parts else "更新了任务信息"


def record_create(session: Session, item: WorkItem) -> None:
    parent_hint = f"（子任务）" if item.parent_id else ""
    record_operation(
        session,
        OperationAction.create,
        f"创建任务{parent_hint}：{item.title}",
        work_item_id=item.id,
        work_item_title=item.title,
    )


def record_update(session: Session, item: WorkItem, data: WorkItemUpdate) -> None:
    message = describe_update(item, data)
    record_operation(
        session,
        OperationAction.update,
        f"更新「{item.title}」：{message}",
        work_item_id=item.id,
        work_item_title=item.title,
    )


def record_delete(session: Session, item: WorkItem) -> None:
    record_operation(
        session,
        OperationAction.delete,
        f"删除任务：{item.title}",
        work_item_id=item.id,
        work_item_title=item.title,
    )


def record_chat(session: Session, user_message: str, reply: str, actions: list[str]) -> None:
    action_text = f"执行 {len(actions)} 项操作" if actions else "未改动任务"
    record_operation(
        session,
        OperationAction.chat,
        f"你说：{user_message}；Agent：{reply}（{action_text}）",
    )
    for action in actions:
        record_operation(
            session,
            OperationAction.agent,
            action,
        )


def list_operations(session: Session, week_key: str) -> list[OperationLog]:
    statement = (
        select(OperationLog)
        .where(OperationLog.week_key == week_key)
        .order_by(OperationLog.created_at.desc())
    )
    return list(session.exec(statement).all())


def list_week_keys(session: Session) -> list[str]:
    rows = session.exec(select(OperationLog.week_key).distinct()).all()
    keys = sorted(set(rows), reverse=True)
    current = week_key_from_dt()
    if current not in keys:
        keys.insert(0, current)
    return keys


def backfill_from_activity_logs(session: Session) -> int:
    existing = session.exec(select(OperationLog.id).limit(1)).first()
    if existing:
        return 0

    activities = list(session.exec(select(ActivityLog).order_by(ActivityLog.created_at)).all())
    count = 0
    for activity in activities:
        item = session.get(WorkItem, activity.work_item_id)
        title = item.title if item else f"任务#{activity.work_item_id}"
        record_operation(
            session,
            OperationAction.agent if activity.source.value == "agent_action" else OperationAction.update,
            f"「{title}」进展：{activity.content}",
            work_item_id=activity.work_item_id,
            work_item_title=title,
            created_at=activity.created_at,
        )
        count += 1
    return count
