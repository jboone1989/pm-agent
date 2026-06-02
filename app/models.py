from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class WorkItemType(str, Enum):
    planned = "planned"
    ad_hoc = "ad_hoc"


class WorkItemStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"
    cancelled = "cancelled"


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class ActivitySource(str, Enum):
    user_message = "user_message"
    agent_action = "agent_action"
    wechat = "wechat"
    worklog = "worklog"


class OperationAction(str, Enum):
    create = "create"
    update = "update"
    delete = "delete"
    chat = "chat"
    agent = "agent"


class WorkItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str = ""
    parent_id: Optional[int] = Field(default=None, foreign_key="workitem.id")
    type: WorkItemType = WorkItemType.planned
    status: WorkItemStatus = WorkItemStatus.todo
    assignee: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    priority: Priority = Priority.medium
    progress: int = Field(default=0, ge=0, le=100)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ActivityLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    work_item_id: int = Field(foreign_key="workitem.id")
    content: str
    source: ActivitySource = ActivitySource.user_message
    created_at: datetime = Field(default_factory=datetime.utcnow)


class OperationLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    week_key: str = Field(index=True)
    action: OperationAction
    work_item_id: Optional[int] = None
    work_item_title: str = ""
    message: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WeeklyReport(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    week_key: str = Field(index=True, unique=True)
    this_week_summary: str
    next_week_plan: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
