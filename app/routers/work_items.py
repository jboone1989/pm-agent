from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.schemas import (
    ActivityLogRead,
    PersonSchedule,
    ProjectSchedule,
    WorkItemCreate,
    WorkItemRead,
    WorkItemUpdate,
)
from app.services import schedules as schedule_service
from app.services import work_items as work_item_service

router = APIRouter(prefix="/api/work-items", tags=["work-items"])


def build_tree(items: list, parent_id: Optional[int] = None) -> list[WorkItemRead]:
    nodes = [item for item in items if item.parent_id == parent_id]
    result: list[WorkItemRead] = []
    for node in sorted(nodes, key=lambda x: x.updated_at, reverse=True):
        data = WorkItemRead.model_validate(node, from_attributes=True)
        data.children = build_tree(items, node.id)
        result.append(data)
    return result


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
