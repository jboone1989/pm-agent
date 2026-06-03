from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from app.models import ActivityLog, ActivitySource, WorkItem, WorkItemStatus, WorkItemType
from app.services.worklog_client import WorklogClient, WorklogError


def pull_projects(session: Session) -> dict:
    client = WorklogClient()
    remote_projects = client.get_projects()

    created = 0
    updated = 0

    for rp in remote_projects:
        existing = session.exec(
            select(WorkItem).where(WorkItem.remote_id == rp["id"])
        ).first()

        if existing:
            existing.title = rp["project_name"]
            existing.description = rp.get("description") or ""
            existing.updated_at = None
            session.add(existing)
            updated += 1
        else:
            item = WorkItem(
                title=rp["project_name"],
                description=rp.get("description") or "",
                type=WorkItemType.planned,
                status=WorkItemStatus.todo,
                remote_id=rp["id"],
                start_date=date.today(),
            )
            session.add(item)
            created += 1

    session.commit()
    return {"created": created, "updated": updated, "total": len(remote_projects)}


def push_tasks(session: Session, project_item_id: int) -> dict:
    project = session.get(WorkItem, project_item_id)
    if not project or not project.remote_id:
        raise WorklogError("该项目未关联 Worklog 项目")

    children = session.exec(
        select(WorkItem).where(WorkItem.parent_id == project_item_id)
    ).all()

    if not children:
        return {"created": 0, "updated": 0}

    client = WorklogClient()
    created = 0
    updated = 0

    for child in children:
        payload = {
            "name": child.title,
            "description": child.description or "",
            "status": _map_status(child.status),
            "progress": child.progress or 0,
            "priority": child.priority.value if child.priority else "medium",
        }
        if child.assignee:
            payload["assignee_id"] = _resolve_assignee_id(client, child.assignee)

        if child.remote_id:
            client.update_task(child.remote_id, payload)
            updated += 1
        else:
            result = client.create_task(project.remote_id, payload)
            if result and result.get("id"):
                child.remote_id = result["id"]
                session.add(child)
                created += 1

    session.commit()
    return {"created": created, "updated": updated}


def pull_logs(session: Session, project_item_id: int, days: int = 7) -> dict:
    project = session.get(WorkItem, project_item_id)
    if not project or not project.remote_id:
        raise WorklogError("该项目未关联 Worklog 项目")

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    client = WorklogClient()
    logs = client.get_logs(
        project.remote_id, start_date.isoformat(), end_date.isoformat()
    )

    children = session.exec(
        select(WorkItem).where(WorkItem.parent_id == project_item_id)
    ).all()
    name_map = {c.title: c for c in children}

    synced = 0
    for log_entry in logs:
        task_name = log_entry.get("project_name") or log_entry.get("content", "")
        content = log_entry.get("content", "")
        log_date = log_entry.get("log_date", "")

        matched = name_map.get(task_name)
        if not matched:
            for child in children:
                if child.title in task_name or task_name in child.title:
                    matched = child
                    break

        if matched:
            session.add(
                ActivityLog(
                    work_item_id=matched.id,
                    content=f"[Worklog {log_date}] {content}",
                    source=ActivitySource.worklog,
                )
            )
            synced += 1

    session.commit()
    return {
        "synced": synced,
        "total_logs": len(logs),
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
    }


def pull_all_logs(session: Session, days: int = 7) -> dict:
    projects = session.exec(
        select(WorkItem).where(
            WorkItem.remote_id.is_not(None), WorkItem.parent_id.is_(None)
        )
    ).all()
    total_synced = 0
    total_logs = 0
    for project in projects:
        try:
            result = pull_logs(session, project.id, days)
            total_synced += result["synced"]
            total_logs += result["total_logs"]
        except WorklogError:
            pass
    return {"synced": total_synced, "total_logs": total_logs, "projects": len(projects)}


STATUS_MAP = {
    WorkItemStatus.todo: "planned",
    WorkItemStatus.in_progress: "in_progress",
    WorkItemStatus.blocked: "paused",
    WorkItemStatus.done: "completed",
    WorkItemStatus.cancelled: "cancelled",
}


def _map_status(status: WorkItemStatus) -> str:
    return STATUS_MAP.get(status, "planned")


def _resolve_assignee_id(client: WorklogClient, name: str) -> Optional[int]:
    try:
        users = client.get_users()
        for u in users:
            if u.get("display_name") == name or u.get("username") == name:
                return u["id"]
    except Exception:
        pass
    return None
