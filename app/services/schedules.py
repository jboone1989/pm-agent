from collections import defaultdict
from typing import Optional

from sqlmodel import Session, select

from app.models import WorkItem, WorkItemType
from app.schemas import PersonSchedule, ProjectSchedule, ScheduleItem
from app.services.work_items import get_root_item


def _to_schedule_item(session: Session, item: WorkItem, include_root: bool = False) -> ScheduleItem:
    root_title = None
    if include_root:
        root = get_root_item(session, item)
        root_title = root.title if root.id != item.id else None
    return ScheduleItem(
        id=item.id,
        title=item.title,
        status=item.status,
        type=item.type,
        assignee=item.assignee,
        start_date=item.start_date,
        due_date=item.due_date,
        parent_id=item.parent_id,
        progress=item.progress,
        root_title=root_title,
    )


def get_person_schedules(session: Session) -> list[PersonSchedule]:
    items = list(session.exec(select(WorkItem).order_by(WorkItem.assignee)).all())
    grouped: dict[str, list[WorkItem]] = defaultdict(list)
    unassigned: list[WorkItem] = []

    for item in items:
        if item.assignee:
            grouped[item.assignee].append(item)
        else:
            unassigned.append(item)

    schedules: list[PersonSchedule] = []
    for assignee in sorted(grouped.keys()):
        person_items = grouped[assignee]
        planned = [i for i in person_items if i.type == WorkItemType.planned]
        ad_hoc = [i for i in person_items if i.type == WorkItemType.ad_hoc]
        schedules.append(
            PersonSchedule(
                assignee=assignee,
                items=[_to_schedule_item(session, i, include_root=True) for i in planned],
                ad_hoc_items=[_to_schedule_item(session, i) for i in ad_hoc],
            )
        )

    if unassigned:
        planned = [i for i in unassigned if i.type == WorkItemType.planned]
        ad_hoc = [i for i in unassigned if i.type == WorkItemType.ad_hoc]
        schedules.append(
            PersonSchedule(
                assignee="未分配",
                items=[_to_schedule_item(session, i, include_root=True) for i in planned],
                ad_hoc_items=[_to_schedule_item(session, i) for i in ad_hoc],
            )
        )
    return schedules


def get_project_schedules(session: Session, project_id: Optional[int] = None) -> list[ProjectSchedule]:
    roots = list(session.exec(select(WorkItem).where(WorkItem.parent_id.is_(None))).all())
    if project_id is not None:
        roots = [r for r in roots if r.id == project_id]

    all_items = list(session.exec(select(WorkItem)).all())
    children_map: dict[int, list[WorkItem]] = defaultdict(list)
    for item in all_items:
        if item.parent_id is not None:
            children_map[item.parent_id].append(item)

    def collect_tree(root_id: int) -> list[WorkItem]:
        result = []
        stack = [root_id]
        while stack:
            current_id = stack.pop()
            item = next((i for i in all_items if i.id == current_id), None)
            if item:
                result.append(item)
                stack.extend(child.id for child in children_map.get(current_id, []))
        return result

    schedules: list[ProjectSchedule] = []
    for root in sorted(roots, key=lambda r: r.title):
        tree_items = collect_tree(root.id)
        schedules.append(
            ProjectSchedule(
                project_id=root.id,
                project_title=root.title,
                items=[_to_schedule_item(session, i) for i in tree_items],
            )
        )
    return schedules
