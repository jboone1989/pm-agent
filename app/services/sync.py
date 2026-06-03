from __future__ import annotations

from datetime import date, datetime, timedelta

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
            existing.updated_at = datetime.utcnow()
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

    all_descendants = _collect_descendants(session, project_item_id)
    if not all_descendants:
        return {"created": 0, "updated": 0}

    client = WorklogClient()
    created = 0
    updated = 0

    for item in all_descendants:
        payload = {
            "name": item.title,
            "description": item.description or "",
            "status": _map_status(item.status),
            "progress": item.progress or 0,
            "priority": item.priority.value if item.priority else "medium",
        }

        if item.parent_id != project_item_id:
            parent_item = session.get(WorkItem, item.parent_id)
            if parent_item and parent_item.remote_id:
                payload["parent_id"] = parent_item.remote_id

        if item.remote_id:
            try:
                client.update_task(item.remote_id, payload)
                updated += 1
            except WorklogError:
                item.remote_id = None
                session.add(item)
                session.commit()
                try:
                    result = client.create_task(project.remote_id, payload)
                    if result and result.get("id"):
                        item.remote_id = result["id"]
                        session.add(item)
                        created += 1
                except WorklogError as e:
                    raise WorklogError(f"创建「{item.title}」失败: {e}")
        else:
            try:
                result = client.create_task(project.remote_id, payload)
            except WorklogError as e:
                raise WorklogError(f"创建「{item.title}」失败: {e}")
            if result and result.get("id"):
                item.remote_id = result["id"]
                session.add(item)
                created += 1

    session.commit()
    return {"created": created, "updated": updated}


def _collect_descendants(session: Session, root_id: int) -> list[WorkItem]:
    """BFS to collect all descendants, parents before children."""
    result: list[WorkItem] = []
    queue = [root_id]
    while queue:
        parent_id = queue.pop(0)
        children = session.exec(
            select(WorkItem).where(WorkItem.parent_id == parent_id)
        ).all()
        for child in children:
            result.append(child)
            queue.append(child.id)
    return result


def pull_logs(session: Session, project_item_id: int, days: int = 7) -> dict:
    project = session.get(WorkItem, project_item_id)
    if not project or not project.remote_id:
        raise WorklogError("该项目未关联 Worklog 项目")

    end_date = date.today() + timedelta(days=1)
    start_date = end_date - timedelta(days=days + 1)

    client = WorklogClient()
    logs = client.get_logs(
        project.remote_id, start_date.isoformat(), end_date.isoformat()
    )

    children = _collect_descendants(session, project_item_id)
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

            new_progress = _infer_progress(content, matched.progress or 0)
            if new_progress != matched.progress:
                matched.progress = new_progress
                from app.services.work_items import normalize_progress
                normalize_progress(matched)
                session.add(matched)

            synced += 1

    session.commit()
    return {
        "synced": synced,
        "total_logs": len(logs),
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
    }


def push_single_task(session: Session, item_id: int) -> dict:
    item = session.get(WorkItem, item_id)
    if not item:
        raise WorklogError("任务不存在")
    if not item.parent_id:
        raise WorklogError("根任务不能推送，请推送到具体子任务")
    parent = session.get(WorkItem, item.parent_id)
    if not parent or not parent.remote_id:
        raise WorklogError("父项目未关联 Worklog")

    client = WorklogClient()
    payload = {
        "name": item.title,
        "description": item.description or "",
        "status": _map_status(item.status),
        "progress": item.progress or 0,
        "priority": item.priority.value if item.priority else "medium",
    }
    if item.parent_id != parent.id:
        grandparent = session.get(WorkItem, item.parent_id)
        if grandparent and grandparent.remote_id:
            payload["parent_id"] = grandparent.remote_id

    if item.remote_id:
        try:
            client.update_task(item.remote_id, payload)
            return {"action": "updated", "remote_id": item.remote_id}
        except WorklogError:
            item.remote_id = None
            session.add(item)
            session.commit()

    try:
        result = client.create_task(parent.remote_id, payload)
    except WorklogError as e:
        raise WorklogError(f"创建到项目#{parent.remote_id}失败: {e}")

    if result and result.get("id"):
        item.remote_id = result["id"]
        session.add(item)
        session.commit()
        return {"action": "created", "remote_id": result["id"]}
    raise WorklogError("创建失败，未返回ID")


def pull_all_logs(session: Session, days: int = 7) -> dict:
    projects = session.exec(
        select(WorkItem).where(
            WorkItem.remote_id.is_not(None), WorkItem.parent_id.is_(None)
        )
    ).all()

    end_date = date.today() + timedelta(days=1)
    start_date = end_date - timedelta(days=days + 1)
    client = WorklogClient()

    entries = []
    total_synced = 0

    for project in projects:
        try:
            logs = client.get_logs(
                project.remote_id, start_date.isoformat(), end_date.isoformat()
            )
        except WorklogError:
            continue

        children = _collect_descendants(session, project.id)
        name_map = {c.title: c for c in children}

        for log_entry in logs:
            task_name = log_entry.get("project_name") or ""
            content = log_entry.get("content", "")
            log_date = log_entry.get("log_date", "")
            username = log_entry.get("display_name") or log_entry.get("username", "")

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
                new_progress = _infer_progress(content, matched.progress or 0)
                if new_progress != matched.progress:
                    matched.progress = new_progress
                    from app.services.work_items import normalize_progress
                    normalize_progress(matched)
                    session.add(matched)
                total_synced += 1

            entries.append({
                "project_name": project.title,
                "task_name": task_name,
                "content": content,
                "log_date": log_date,
                "username": username,
                "matched": matched is not None,
            })

    session.commit()
    return {
        "synced": total_synced,
        "total_logs": len(entries),
        "projects": len(projects),
        "entries": entries,
    }


def _infer_progress(content: str, current: int) -> int:
    import re
    pct_match = re.search(r"(\d{1,3})\s*%", content)
    if pct_match:
        return max(0, min(100, int(pct_match.group(1))))
    if any(kw in content for kw in ["完成", "搞定", "做完", "上线", "发布", "合入", "done"]):
        return 100
    if any(kw in content for kw in ["基本完成", "差不多了", "收尾", "测试中"]):
        return max(current, 90)
    if any(kw in content for kw in ["进行中", "开发中", "修复中", "排查中"]):
        return max(current, 50)
    if any(kw in content for kw in ["开始", "启动", "排期"]):
        return max(current, 10)
    return current


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
