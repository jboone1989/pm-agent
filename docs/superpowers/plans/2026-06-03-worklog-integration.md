# Worklog API Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Worklog API — pull projects, push tasks with remote_id mapping, pull logs to update progress.

**Architecture:** New `worklog_client.py` wraps all Worklog HTTP calls with Bearer auth. New `sync.py` orchestrates sync operations. New `sync.py` router exposes POST endpoints. WorkItem model gets `remote_id` field for bidirectional mapping.

**Tech Stack:** `httpx` (already transitive dep via openai), existing FastAPI + SQLModel stack.

---

### Task 1: Add Worklog config and remote_id field

**Files:**
- Modify: `app/config.py`
- Modify: `app/models.py`
- Modify: `app/schemas.py`
- Modify: `app/db.py`

- [ ] **Step 1: Add WORKLOG env vars to config.py**

Add after the existing LLM config lines in `app/config.py`:

```python
WORKLOG_API_KEY = os.getenv("WORKLOG_API_KEY", "")
WORKLOG_API_BASE = os.getenv("WORKLOG_API_BASE", "https://k1.xaytzn.com/worklog/api/v1")
```

- [ ] **Step 2: Add remote_id to WorkItem model**

In `app/models.py`, add field to WorkItem class after `progress`:

```python
remote_id: Optional[int] = Field(default=None)
```

- [ ] **Step 3: Add migration for remote_id column**

In `app/db.py::migrate_db()`, add after the `progress` column migration block:

```python
if "remote_id" not in columns:
    conn.execute(text("ALTER TABLE workitem ADD COLUMN remote_id INTEGER"))
```

- [ ] **Step 4: Add remote_id to schemas**

In `app/schemas.py`, add to `WorkItemCreate`:

```python
remote_id: Optional[int] = None
```

Add to `WorkItemUpdate`:

```python
remote_id: Optional[int] = None
```

Add to `WorkItemRead`:

```python
remote_id: Optional[int] = None
```

- [ ] **Step 5: Commit**

```
git add app/config.py app/models.py app/schemas.py app/db.py
git commit -m "feat: add remote_id field and worklog config for external sync"
```

---

### Task 2: Create Worklog HTTP client

**Files:**
- Create: `app/services/worklog_client.py`

- [ ] **Step 1: Create `app/services/worklog_client.py`**

```python
from __future__ import annotations

from typing import Optional

import httpx

from app.config import WORKLOG_API_BASE, WORKLOG_API_KEY


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {WORKLOG_API_KEY}",
        "Content-Type": "application/json",
    }


def _url(path: str) -> str:
    return f"{WORKLOG_API_BASE}{path}"


class WorklogError(Exception):
    pass


class WorklogClient:
    def __init__(self):
        self._client = httpx.Client(timeout=30)

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = self._client.request(method, _url(path), headers=_headers(), **kwargs)
        except httpx.RequestError as e:
            raise WorklogError(f"请求失败: {e}")
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json().get("error", resp.text)
            except Exception:
                pass
            raise WorklogError(f"API 错误 ({resp.status_code}): {detail}")
        if resp.status_code == 204:
            return {}
        return resp.json()

    def get_projects(self) -> list[dict]:
        return self._request("GET", "/projects").get("data", [])

    def get_tasks(self, project_id: int, status: Optional[str] = None) -> list[dict]:
        params = {}
        if status:
            params["status"] = status
        return self._request("GET", f"/projects/{project_id}/tasks", params=params).get("data", [])

    def create_task(self, project_id: int, data: dict) -> dict:
        return self._request("POST", f"/projects/{project_id}/tasks", json=data).get("data", {})

    def update_task(self, task_id: int, data: dict) -> dict:
        return self._request("PUT", f"/tasks/{task_id}", json=data).get("data", {})

    def delete_task(self, task_id: int) -> None:
        self._request("DELETE", f"/tasks/{task_id}")

    def get_logs(self, project_id: int, start_date: str, end_date: str) -> list[dict]:
        return self._request(
            "GET",
            "/logs",
            params={"project_id": project_id, "start_date": start_date, "end_date": end_date, "limit": 200},
        ).get("data", [])
```

- [ ] **Step 2: Commit**

```
git add app/services/worklog_client.py
git commit -m "feat: add Worklog API HTTP client"
```

---

### Task 3: Create sync service

**Files:**
- Create: `app/services/sync.py`

- [ ] **Step 1: Create `app/services/sync.py`**

```python
from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session, select

from app.models import WorkItem, WorkItemStatus, WorkItemType, ActivityLog, ActivitySource
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
            existing.updated_at = None  # trigger SQLAlchemy update
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
            payload["assignee_name"] = child.assignee

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
    logs = client.get_logs(project.remote_id, start_date.isoformat(), end_date.isoformat())

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
            session.add(ActivityLog(
                work_item_id=matched.id,
                content=f"[Worklog {log_date}] {content}",
                source=ActivitySource.worklog,
            ))
            synced += 1

    session.commit()
    return {"synced": synced, "total_logs": len(logs), "start": start_date.isoformat(), "end": end_date.isoformat()}


STATUS_MAP = {
    WorkItemStatus.todo: "planned",
    WorkItemStatus.in_progress: "in_progress",
    WorkItemStatus.blocked: "paused",
    WorkItemStatus.done: "completed",
    WorkItemStatus.cancelled: "cancelled",
}


def _map_status(status: WorkItemStatus) -> str:
    return STATUS_MAP.get(status, "planned")
```

- [ ] **Step 2: Commit**

```
git add app/services/sync.py
git commit -m "feat: add sync service for pull/push/pull-logs"
```

---

### Task 4: Create sync router

**Files:**
- Create: `app/routers/sync.py`
- Modify: `app/main.py`

- [ ] **Step 1: Create `app/routers/sync.py`**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.services import sync as sync_service
from app.services.worklog_client import WorklogError

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/pull-projects")
def pull_projects(session: Session = Depends(get_session)):
    try:
        result = sync_service.pull_projects(session)
        return {"ok": True, **result}
    except WorklogError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/push-tasks/{project_item_id}")
def push_tasks(project_item_id: int, session: Session = Depends(get_session)):
    try:
        result = sync_service.push_tasks(session, project_item_id)
        return {"ok": True, **result}
    except WorklogError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pull-logs/{project_item_id}")
def pull_logs(project_item_id: int, days: int = 7, session: Session = Depends(get_session)):
    try:
        result = sync_service.pull_logs(session, project_item_id, days)
        return {"ok": True, **result}
    except WorklogError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 2: Register router in app/main.py**

In `app/main.py`, add import after existing router imports:

```python
from app.routers import chat, weekly_log, work_items, sync
```

Add after existing `app.include_router` lines:

```python
app.include_router(sync.router)
```

- [ ] **Step 3: Commit**

```
git add app/routers/sync.py app/main.py
git commit -m "feat: add sync API endpoints for pull-projects, push-tasks, pull-logs"
```

---

### Task 5: Add sync buttons to frontend

**Files:**
- Modify: `templates/index.html`
- Modify: `static/js/app.js`

- [ ] **Step 1: Add sync buttons to HTML**

In `templates/index.html`, add after the chat panel or in the sidebar header area. Find a suitable spot — add a sync section above the project tree. Add before the tree container:

```html
<div class="sync-bar">
  <button type="button" class="btn primary sm" id="pullProjectsBtn">从 Worklog 拉取项目</button>
  <span id="syncStatus" style="font-size:12px;color:var(--muted);margin-left:8px"></span>
</div>
```

- [ ] **Step 2: Add sync JS functions and event handlers**

In `static/js/app.js`, add:

```javascript
async function pullProjects() {
  const btn = document.getElementById("pullProjectsBtn");
  const status = document.getElementById("syncStatus");
  btn.disabled = true;
  status.textContent = "同步中...";
  try {
    const result = await fetchJson("/api/sync/pull-projects", { method: "POST" });
    status.textContent = `已同步: 新建 ${result.created}, 更新 ${result.updated}`;
    await loadData();
  } catch (e) {
    status.textContent = `失败: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
}

async function pushTasks(projectId) {
  try {
    const result = await fetchJson(`/api/sync/push-tasks/${projectId}`, { method: "POST" });
    showAppToast(`推送完成: 新建 ${result.created}, 更新 ${result.updated}`);
    await loadData();
  } catch (e) {
    showAppToast(`推送失败: ${e.message}`, "error");
  }
}

async function pullLogs(projectId) {
  try {
    const result = await fetchJson(`/api/sync/pull-logs/${projectId}?days=7`, { method: "POST" });
    showAppToast(`拉取日志: ${result.synced}/${result.total_logs} 条`);
    await loadData();
  } catch (e) {
    showAppToast(`拉取日志失败: ${e.message}`, "error");
  }
}

document.getElementById("pullProjectsBtn").addEventListener("click", pullProjects);
```

- [ ] **Step 3: Add per-project push/logs buttons to timeline modal**

In `static/js/app.js`, in the `openTimelineModal` function, when rendering a project (parent_id is None and remote_id exists), add push and pull-logs buttons after the project title or in the header:

```javascript
// When rendering timeline modal for a project with remote_id:
// Add these buttons alongside existing "添加子任务" / "编辑详情" / "删除"
const headerActions = document.querySelector(".timeline-modal-header-actions");
if (headerActions && item.remote_id) {
  const pushBtn = document.createElement("button");
  pushBtn.className = "btn primary sm";
  pushBtn.textContent = "推送到 Worklog";
  pushBtn.addEventListener("click", () => pushTasks(item.id));
  headerActions.prepend(pushBtn);

  const logsBtn = document.createElement("button");
  logsBtn.className = "btn secondary sm";
  logsBtn.textContent = "拉取日志";
  logsBtn.addEventListener("click", () => pullLogs(item.id));
  headerActions.prepend(logsBtn);
}
```

- [ ] **Step 4: Commit**

```
git add templates/index.html static/js/app.js
git commit -m "feat: add sync buttons for pull-projects, push-tasks, pull-logs"
```

---

### Task 6: End-to-end verification

**No code changes.**

- [ ] **Step 1: Set API key in .env**

Ensure `.env` contains: `WORKLOG_API_KEY=wlg_your_key`

- [ ] **Step 2: Start the server**

Run: `uvicorn app.main:app --reload`

- [ ] **Step 3: Pull projects**

Click "从 Worklog 拉取项目" button. Expected: Worklog projects appear in the tree.

- [ ] **Step 4: Create a subtask under a synced project**

Use the UI or chat to create a task. Verify it appears under the project.

- [ ] **Step 5: Push tasks**

Open a synced project's timeline modal, click "推送到 Worklog". Expected: toast shows created count.

- [ ] **Step 6: Pull logs**

Click "拉取日志". Expected: activity entries appear in task timeline.
