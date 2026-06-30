from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Text
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
    worklog = "worklog"


class WorkItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: str = Field(default="", sa_column=Column(Text))
    parent_id: Optional[int] = Field(default=None, foreign_key="workitem.id")
    type: WorkItemType = WorkItemType.planned
    status: WorkItemStatus = WorkItemStatus.todo
    assignee: Optional[str] = None
    start_date: Optional[date] = None
    due_date: Optional[date] = None
    priority: Priority = Priority.medium
    progress: int = Field(default=0, ge=0, le=100)
    remote_id: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ActivityLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    work_item_id: int = Field(foreign_key="workitem.id")
    content: str = Field(sa_column=Column(Text))
    source: ActivitySource = ActivitySource.user_message
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WorkLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    content: str = Field(sa_column=Column(Text))
    duration_minutes: Optional[int] = None
    log_date: date = Field(default_factory=date.today)
    work_item_id: Optional[int] = Field(default=None, foreign_key="workitem.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OperationLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    week_key: str = Field(index=True)
    action: OperationAction
    work_item_id: Optional[int] = None
    work_item_title: str = Field(default="", sa_column=Column(Text))
    message: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WeeklyReport(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    week_key: str = Field(index=True, unique=True)
    this_week_summary: str = Field(sa_column=Column(Text))
    next_week_plan: str = Field(sa_column=Column(Text))
    generated_at: datetime = Field(default_factory=datetime.utcnow)
