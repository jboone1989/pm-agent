from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.services import sync as sync_service
from app.services.worklog_client import WorklogClient, WorklogError

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/pull-projects")
def pull_projects(session: Session = Depends(get_session)):
    try:
        result = sync_service.pull_projects(session)
        return {"ok": True, **result}
    except WorklogError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pull-all-logs")
def pull_all_logs(days: int = 7, session: Session = Depends(get_session)):
    try:
        result = sync_service.pull_all_logs(session, days)
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
def pull_logs(
    project_item_id: int, days: int = 7, session: Session = Depends(get_session)
):
    try:
        result = sync_service.pull_logs(session, project_item_id, days)
        return {"ok": True, **result}
    except WorklogError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/users")
def list_users():
    try:
        client = WorklogClient()
        users = client.get_users()
        return {"ok": True, "data": users}
    except WorklogError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/users/{user_id}")
def get_user(user_id: int):
    try:
        client = WorklogClient()
        user = client.get_user(user_id)
        return {"ok": True, "data": user}
    except WorklogError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/logs")
def list_logs(
    project_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 200,
    offset: int = 0,
):
    try:
        client = WorklogClient()
        logs = client.get_logs(
            project_id=project_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        return {"ok": True, "data": logs}
    except WorklogError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/logs/{log_id}")
def get_log(log_id: int):
    try:
        client = WorklogClient()
        log = client.get_log(log_id)
        return {"ok": True, "data": log}
    except WorklogError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/logs")
def create_log(body: dict):
    try:
        client = WorklogClient()
        log = client.create_log(body)
        return {"ok": True, "data": log}
    except WorklogError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/tasks")
def create_worklog_task(project_id: int, body: dict):
    try:
        client = WorklogClient()
        task = client.create_task(project_id, body)
        return {"ok": True, "data": task}
    except WorklogError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/push-task/{item_id}")
def push_single_task(item_id: int, session: Session = Depends(get_session)):
    try:
        result = sync_service.push_single_task(session, item_id)
        return {"ok": True, **result}
    except WorklogError as e:
        raise HTTPException(status_code=400, detail=str(e))