from __future__ import annotations

import re
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


_WORKLOG_ID_RE = re.compile(r"\[Worklog#(\d+)")


def _format_worklog_label(log_entry: dict) -> str:
    wl_log_id = log_entry.get("id")
    log_date = log_entry.get("log_date", "")
    username = log_entry.get("display_name") or log_entry.get("username", "")
    content = log_entry.get("content", "")
    head = f"[Worklog#{wl_log_id} {log_date}" if wl_log_id else f"[Worklog {log_date}"
    if username:
        head += f" {username}"
    return f"{head}] {content}"


def _load_synced_worklog_keys(
    session: Session, work_item_ids: list[int]
) -> set[tuple[int, int]]:
    if not work_item_ids:
        return set()
    rows = session.exec(
        select(ActivityLog.work_item_id, ActivityLog.content).where(
            ActivityLog.work_item_id.in_(work_item_ids),
            ActivityLog.source == ActivitySource.worklog,
        )
    ).all()
    keys: set[tuple[int, int]] = set()
    for work_item_id, text in rows:
        match = _WORKLOG_ID_RE.search(text)
        if match:
            keys.add((work_item_id, int(match.group(1))))
    return keys


def _log_date_range(days: int) -> tuple[date, date]:
    end_date = date.today() + timedelta(days=1)
    start_date = end_date - timedelta(days=days + 1)
    return start_date, end_date


def _find_worklog_activity(session: Session, wl_log_id: int) -> ActivityLog | None:
    if not wl_log_id:
        return None
    prefix = f"[Worklog#{wl_log_id} "
    return session.exec(
        select(ActivityLog).where(
            ActivityLog.source == ActivitySource.worklog,
            ActivityLog.content.startswith(prefix),
        )
    ).first()


def _match_local_work_item(
    local_project: WorkItem,
    children: list[WorkItem],
    name_map: dict[str, WorkItem],
    log_entry: dict,
    remote_name: str,
) -> WorkItem | None:
    task_id = log_entry.get("task_id")
    if task_id is not None:
        for child in children:
            if child.remote_id == task_id:
                return child
        return None

    wl_task_name = (log_entry.get("task_name") or "").strip()
    if wl_task_name:
        if wl_task_name in (remote_name, local_project.title):
            return None
        matched = name_map.get(wl_task_name)
        if matched:
            return matched
        for child in children:
            if child.title in wl_task_name or wl_task_name in child.title:
                return child
        return None

    return None


def _apply_project_logs(
    session: Session,
    logs: list[dict],
    remote_id: int,
    remote_name: str,
    local_project: WorkItem | None,
) -> tuple[list[dict], int, int]:
    children: list[WorkItem] = []
    name_map: dict[str, WorkItem] = {}
    synced_keys: set[tuple[int, int]] = set()
    if local_project and local_project.id is not None:
        children = _collect_descendants(session, local_project.id)
        name_map = {c.title: c for c in children}
        work_item_ids = [local_project.id] + [c.id for c in children if c.id is not None]
        synced_keys = _load_synced_worklog_keys(session, work_item_ids)

    entries: list[dict] = []
    synced = 0
    skipped = 0

    for log_entry in logs:
        if log_entry.get("project_id") not in (None, remote_id):
            continue

        wl_task_name = (log_entry.get("task_name") or "").strip()
        content = log_entry.get("content", "")
        log_date = log_entry.get("log_date", "")
        wl_log_id = log_entry.get("id")
        username = log_entry.get("display_name") or log_entry.get("username", "")
        already_synced = False

        matched: WorkItem | None = None
        if local_project:
            matched = _match_local_work_item(
                local_project, children, name_map, log_entry, remote_name
            )

            if matched and matched.id is not None:
                if wl_log_id:
                    existing = _find_worklog_activity(session, wl_log_id)
                    if existing:
                        if existing.work_item_id == matched.id:
                            already_synced = True
                            skipped += 1
                        else:
                            existing.work_item_id = matched.id
                            session.add(existing)
                            synced += 1
                        entries.append({
                            "project_name": log_entry.get("project_name") or remote_name,
                            "task_name": wl_task_name or "-",
                            "task_id": log_entry.get("task_id"),
                            "worklog_id": wl_log_id,
                            "content": content,
                            "log_date": log_date,
                            "username": username,
                            "matched": True,
                            "already_synced": already_synced,
                            "remote_project_id": remote_id,
                        })
                        continue

                dedupe_key = (matched.id, wl_log_id) if wl_log_id else None
                if dedupe_key and dedupe_key in synced_keys:
                    already_synced = True
                    skipped += 1
                else:
                    label = _format_worklog_label(log_entry)
                    session.add(
                        ActivityLog(
                            work_item_id=matched.id,
                            content=label,
                            source=ActivitySource.worklog,
                        )
                    )
                    if dedupe_key:
                        synced_keys.add(dedupe_key)

                    if matched.parent_id is not None:
                        new_progress = _infer_progress(content, matched.progress or 0)
                        if new_progress != matched.progress:
                            matched.progress = new_progress
                            from app.services.work_items import normalize_progress
                            normalize_progress(matched)
                            session.add(matched)

                    synced += 1

        entries.append({
            "project_name": log_entry.get("project_name") or remote_name,
            "task_name": wl_task_name or "-",
            "task_id": log_entry.get("task_id"),
            "worklog_id": wl_log_id,
            "content": content,
            "log_date": log_date,
            "username": username,
            "matched": matched is not None,
            "already_synced": already_synced,
            "remote_project_id": remote_id,
        })

    return entries, synced, skipped


def pull_logs(session: Session, project_item_id: int, days: int = 7) -> dict:
    project = session.get(WorkItem, project_item_id)
    if not project or not project.remote_id:
        raise WorklogError("该项目未关联 Worklog 项目")

    start_date, end_date = _log_date_range(days)

    client = WorklogClient()
    logs = client.get_logs(
        project_id=project.remote_id,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )

    entries, synced, skipped = _apply_project_logs(
        session, logs, project.remote_id, project.title, project
    )

    session.commit()
    return {
        "synced": synced,
        "skipped_duplicates": skipped,
        "total_logs": len(entries),
        "entries": entries,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
    }


def push_single_task(session: Session, item_id: int) -> dict:
    created = 0
    updated = 0

    def _push_one(task_id: int, project_remote_id: int, client: WorklogClient) -> None:
        nonlocal created, updated
        task = session.get(WorkItem, task_id)
        if not task:
            return
        payload = {
            "name": task.title,
            "description": task.description or "",
            "status": _map_status(task.status),
            "progress": task.progress or 0,
            "priority": task.priority.value if task.priority else "medium",
        }
        local_parent_id = task.parent_id
        if local_parent_id:
            lp = session.get(WorkItem, local_parent_id)
            if lp and lp.remote_id and lp.parent_id is not None:
                payload["parent_id"] = lp.remote_id

        if task.remote_id:
            try:
                client.update_task(task.remote_id, payload)
                updated += 1
                return
            except WorklogError as e:
                if "404" in str(e):
                    task.remote_id = None
                    session.add(task)
                    session.commit()
                else:
                    return

        try:
            result = client.create_task(project_remote_id, payload)
        except WorklogError:
            return
        if result and result.get("id"):
            task.remote_id = result["id"]
            session.add(task)
            created += 1

    item = session.get(WorkItem, item_id)
    if not item:
        raise WorklogError("任务不存在")
    if not item.parent_id:
        raise WorklogError("根任务不能推送")

    parent = session.get(WorkItem, item.parent_id)
    if not parent or not parent.remote_id:
        raise WorklogError("父项目未关联 Worklog")

    # Find root project's Worklog ID
    root = item
    while root.parent_id:
        p = session.get(WorkItem, root.parent_id)
        if not p:
            break
        root = p
    if not root.remote_id:
        raise WorklogError("根项目未关联 Worklog")

    descendants = [item] + _collect_descendants(session, item.id)
    wl_client = WorklogClient()
    for d in descendants:
        _push_one(d.id, root.remote_id, wl_client)
    session.commit()
    return {"created": created, "updated": updated, "total": len(descendants)}


def pull_all_logs(session: Session, days: int = 7) -> dict:
    client = WorklogClient()
    try:
        remote_projects = client.get_projects()
    except WorklogError as e:
        raise WorklogError(f"获取 Worklog 项目列表失败: {e}")

    local_projects = session.exec(
        select(WorkItem).where(
            WorkItem.remote_id.is_not(None), WorkItem.parent_id.is_(None)
        )
    ).all()
    local_by_remote = {p.remote_id: p for p in local_projects if p.remote_id is not None}

    start_date, end_date = _log_date_range(days)

    all_entries: list[dict] = []
    total_synced = 0
    total_skipped = 0
    project_results: list[dict] = []

    for rp in remote_projects:
        remote_id = rp["id"]
        remote_name = rp.get("project_name") or f"项目#{remote_id}"
        local = local_by_remote.get(remote_id)

        try:
            logs = client.get_logs(
                project_id=remote_id,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )
        except WorklogError as e:
            project_results.append({
                "remote_id": remote_id,
                "project_name": remote_name,
                "local_id": local.id if local else None,
                "total_logs": 0,
                "synced": 0,
                "error": str(e),
            })
            continue

        entries, synced, skipped = _apply_project_logs(
            session, logs, remote_id, remote_name, local
        )
        all_entries.extend(entries)
        total_synced += synced
        total_skipped += skipped
        project_results.append({
            "remote_id": remote_id,
            "project_name": remote_name,
            "local_id": local.id if local else None,
            "total_logs": len(entries),
            "synced": synced,
            "skipped_duplicates": skipped,
        })

    session.commit()
    return {
        "synced": total_synced,
        "skipped_duplicates": total_skipped,
        "total_logs": len(all_entries),
        "projects": len(remote_projects),
        "entries": all_entries,
        "project_results": project_results,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
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
