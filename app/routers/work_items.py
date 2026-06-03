from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.schemas import (
    ActivityLogCreate,
    ActivityLogRead,
    PersonSchedule,
    ProjectSchedule,
    TimelineItem,
    WorkItemCreate,
    WorkItemRead,
    WorkItemUpdate,
)
from app.services import schedules as schedule_service
from app.services import work_items as work_item_service

router = APIRouter(prefix="/api/work-items", tags=["work-items"])


def build_tree(items: list) -> list[WorkItemRead]:
    children_map: dict[int, list] = {}
    roots: list = []
    for item in items:
        children_map.setdefault(item.parent_id, []).append(item)
    for node in children_map.get(None, []):
        data = WorkItemRead.model_validate(node, from_attributes=True)
        _attach_children(data, children_map)
        roots.append(data)
    roots.sort(key=lambda x: x.updated_at, reverse=True)
    return roots


def _attach_children(parent: WorkItemRead, children_map: dict[int, list]) -> None:
    children = children_map.get(parent.id, [])
    parent.children = []
    for node in sorted(children, key=lambda x: x.updated_at, reverse=True):
        data = WorkItemRead.model_validate(node, from_attributes=True)
        _attach_children(data, children_map)
        parent.children.append(data)


@router.get("", response_model=list[WorkItemRead])
def list_work_items(session: Session = Depends(get_session)):
    items = work_item_service.list_all_work_items(session)
    return build_tree(items)


@router.get("/flat", response_model=list[WorkItemRead])
def list_work_items_flat(session: Session = Depends(get_session)):
    items = work_item_service.list_all_work_items(session)
    return [WorkItemRead.model_validate(item, from_attributes=True) for item in items]


@router.post("", response_model=WorkItemRead)
def create_work_item(payload: WorkItemCreate, session: Session = Depends(get_session)):
    item = work_item_service.create_work_item(session, payload)
    return WorkItemRead.model_validate(item, from_attributes=True)


@router.get("/schedules/by-person", response_model=list[PersonSchedule])
def schedules_by_person(session: Session = Depends(get_session)):
    return schedule_service.get_person_schedules(session)


@router.get("/schedules/by-project", response_model=list[ProjectSchedule])
def schedules_by_project(project_id: Optional[int] = None, session: Session = Depends(get_session)):
    return schedule_service.get_project_schedules(session, project_id)


@router.get("/meta/assignees", response_model=list[str])
def list_assignees(session: Session = Depends(get_session)):
    return work_item_service.list_assignees(session)


@router.get("/{item_id}", response_model=WorkItemRead)
def get_work_item(item_id: int, session: Session = Depends(get_session)):
    item = work_item_service.get_work_item(session, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    return WorkItemRead.model_validate(item, from_attributes=True)


@router.patch("/{item_id}", response_model=WorkItemRead)
def update_work_item(item_id: int, payload: WorkItemUpdate, session: Session = Depends(get_session)):
    item = work_item_service.update_work_item(session, item_id, payload)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    return WorkItemRead.model_validate(item, from_attributes=True)


@router.delete("/{item_id}")
def delete_work_item(item_id: int, session: Session = Depends(get_session)):
    if not work_item_service.delete_work_item(session, item_id):
        raise HTTPException(status_code=404, detail="Work item not found")
    return {"ok": True}


@router.get("/{item_id}/activities", response_model=list[ActivityLogRead])
def get_activities(item_id: int, session: Session = Depends(get_session)):
    item = work_item_service.get_work_item(session, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Work item not found")
    logs = work_item_service.get_activity_logs(session, item_id)
    return [ActivityLogRead.model_validate(log, from_attributes=True) for log in logs]


@router.post("/{item_id}/activities", response_model=ActivityLogRead)
def create_activity(item_id: int, payload: ActivityLogCreate, session: Session = Depends(get_session)):
    log = work_item_service.add_activity(session, item_id, payload.content)
    if not log:
        raise HTTPException(status_code=404, detail="Work item not found")
    return ActivityLogRead.model_validate(log, from_attributes=True)


@router.delete("/{item_id}/activities/{activity_id}")
def delete_activity(item_id: int, activity_id: int, session: Session = Depends(get_session)):
    ok = work_item_service.delete_activity(session, activity_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Activity log not found")
    return {"ok": True}


@router.get("/{item_id}/timeline", response_model=list[TimelineItem])
def get_timeline(item_id: int, session: Session = Depends(get_session)):
    return work_item_service.get_timeline(session, item_id)


@router.get("/{item_id}/children-activity")
def children_last_activity(item_id: int, session: Session = Depends(get_session)):
    return work_item_service.get_children_last_activity(session, item_id)
