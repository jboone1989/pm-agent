"""Import 异动智能体 schedule from Gantt chart."""

from app.db import engine, init_db
from app.models import WorkItemStatus, WorkItemType, Priority
from app.schemas import WorkItemCreate
from app.services.work_items import create_work_item
from sqlmodel import Session, select
from app.models import WorkItem


def status_from_progress(progress: int | None) -> WorkItemStatus:
    if progress is None:
        return WorkItemStatus.todo
    if progress >= 100:
        return WorkItemStatus.done
    if progress > 0:
        return WorkItemStatus.in_progress
    return WorkItemStatus.todo


def priority_from_level(level: int) -> Priority:
    return Priority.high if level == 1 else Priority.medium


def create(session: Session, parent_id: int | None, **kwargs) -> WorkItem:
    data = WorkItemCreate(parent_id=parent_id, type=WorkItemType.planned, **kwargs)
    return create_work_item(session, data)


def main() -> None:
    init_db()
    with Session(engine) as session:
        existing = session.exec(select(WorkItem).where(WorkItem.title == "异动智能体")).first()
        if existing:
            print("Schedule already imported (root: 异动智能体). Skipping.")
            return

        root = create(
            session,
            None,
            title="异动智能体",
            description="异动智能体项目总计划",
            start_date="2026-05-11",
            due_date="2026-07-16",
            status=status_from_progress(22),
            priority=priority_from_level(1),
        )

        v11 = create(
            session,
            root.id,
            title="1.1版本（推广）",
            start_date="2026-05-14",
            due_date="2026-06-10",
            status=status_from_progress(28),
            priority=priority_from_level(2),
        )

        create(
            session,
            v11.id,
            title="技术环境调研",
            start_date="2026-05-14",
            due_date="2026-05-20",
            status=status_from_progress(100),
            priority=priority_from_level(1),
        )
        create(
            session,
            v11.id,
            title="技术改造评估",
            start_date="2026-05-21",
            due_date="2026-05-22",
            status=status_from_progress(0),
            priority=priority_from_level(1),
        )

        refactor = create(
            session,
            v11.id,
            title="改造",
            start_date="2026-05-25",
            due_date="2026-06-05",
            status=status_from_progress(0),
            priority=priority_from_level(1),
        )
        create(
            session,
            refactor.id,
            title="配套页面",
            start_date="2026-05-25",
            due_date="2026-06-05",
            status=status_from_progress(0),
            priority=priority_from_level(1),
        )
        create(
            session,
            refactor.id,
            title="配套接口",
            start_date="2026-05-25",
            due_date="2026-06-05",
            status=status_from_progress(0),
            priority=priority_from_level(1),
        )
        create(
            session,
            v11.id,
            title="部署手册、接口文档、操作手册",
            start_date="2026-06-08",
            due_date="2026-06-10",
            status=status_from_progress(0),
            priority=priority_from_level(1),
        )
        create(
            session,
            v11.id,
            title="1.1推广版本完成",
            description="里程碑",
            start_date="2026-06-10",
            due_date="2026-06-10",
            status=WorkItemStatus.todo,
            priority=priority_from_level(2),
        )

        create(
            session,
            root.id,
            title="1.0版本",
            start_date="2026-05-11",
            due_date="2026-07-16",
            status=status_from_progress(20),
            priority=priority_from_level(1),
        )

        anhui = create(
            session,
            root.id,
            title="安徽试点版本（2.0）",
            start_date="2026-05-25",
            due_date="2026-06-30",
            status=status_from_progress(9),
            priority=priority_from_level(2),
        )
        create(
            session,
            anhui.id,
            title="接入中国电科院专题影响因素分析工具",
            start_date="2026-06-08",
            due_date="2026-06-12",
            status=status_from_progress(0),
            priority=priority_from_level(1),
        )
        create(
            session,
            anhui.id,
            title="接入市场信息，构建事件-用电变化关联分析能力",
            start_date="2026-06-15",
            due_date="2026-06-19",
            status=status_from_progress(0),
            priority=priority_from_level(1),
        )
        create(
            session,
            anhui.id,
            title="缓冲",
            start_date="2026-06-22",
            due_date="2026-06-30",
            status=status_from_progress(0),
            priority=priority_from_level(1),
        )

        total = len(session.exec(select(WorkItem)).all())
        print(f"Imported 异动智能体 schedule. Total work items: {total}")


if __name__ == "__main__":
    main()
