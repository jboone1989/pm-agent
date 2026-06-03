from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.models import ActivitySource, Priority, WorkItemStatus, WorkItemType


class WorkItemCreate(BaseModel):
    title: str
    description: str = ""
    parent_id: Optional[int] = None
    type: WorkItemType = WorkItemType.planned
    status: WorkItemStatus = WorkItemStatus.todo
    assignee: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    priority: Priority = Priority.medium
    progress: int = 0
    remote_id: Optional[int] = None


class WorkItemUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    parent_id: Optional[int] = None
    type: Optional[WorkItemType] = None
    status: Optional[WorkItemStatus] = None
    assignee: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    priority: Optional[Priority] = None
    progress: Optional[int] = None
    remote_id: Optional[int] = None

    @field_validator("progress")
    @classmethod
    def validate_progress(cls, value: Optional[int]) -> Optional[int]:
        if value is None:
            return value
        return max(0, min(100, value))


class WorkItemRead(BaseModel):
    id: int
    title: str
    description: str
    parent_id: Optional[int]
    type: WorkItemType
    status: WorkItemStatus
    assignee: Optional[str]
    start_date: Optional[date]
    due_date: Optional[date]
    priority: Priority
    progress: int = 0
    remote_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    children: list["WorkItemRead"] = Field(default_factory=list)


class ActivityLogRead(BaseModel):
    id: int
    work_item_id: int
    content: str
    source: ActivitySource
    created_at: datetime


class ActivityLogCreate(BaseModel):
    content: str


class TimelineItem(BaseModel):
    id: int
    type: str  # "create", "status", "progress", "note", "assignee", "date"
    content: str
    detail: str = ""
    created_at: datetime


class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []


class ChatResponse(BaseModel):
    reply: str
    actions: list[str] = Field(default_factory=list)
    changed_item_ids: list[int] = Field(default_factory=list)


class ScheduleItem(BaseModel):
    id: int
    title: str
    status: WorkItemStatus
    type: WorkItemType
    assignee: Optional[str]
    start_date: Optional[date]
    due_date: Optional[date]
    parent_id: Optional[int]
    progress: int = 0
    root_title: Optional[str] = None


class PersonSchedule(BaseModel):
    assignee: str
    items: list[ScheduleItem]
    ad_hoc_items: list[ScheduleItem]


class ProjectSchedule(BaseModel):
    project_id: int
    project_title: str
    items: list[ScheduleItem]


class OperationLogRead(BaseModel):
    id: int
    week_key: str
    action: str
    work_item_id: Optional[int]
    work_item_title: str
    message: str
    created_at: datetime


class WeeklyLogResponse(BaseModel):
    week_key: str
    week_label: str
    start_date: date
    end_date: date
    entries: list[OperationLogRead]
    report: Optional["WeeklyReportRead"] = None


class WeeklyReportRead(BaseModel):
    week_key: str
    this_week_summary: str
    next_week_plan: str
    generated_at: datetime


class WeeklyReportGenerateResponse(BaseModel):
    week_key: str
    this_week_summary: str
    next_week_plan: str
    generated_at: datetime


WorkItemRead.model_rebuild()
WeeklyLogResponse.model_rebuild()
