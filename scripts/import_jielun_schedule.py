"""Import 结论辅助生成智能体 / 负荷异动分析智能体 schedule from Gantt chart."""

from app.db import engine, init_db
from app.models import WorkItem, WorkItemStatus, WorkItemType, Priority
from app.schemas import WorkItemCreate
from app.services.work_items import create_work_item
from sqlmodel import Session, select


def status_from_progress(progress: int | None) -> WorkItemStatus:
    if progress is None:
        return WorkItemStatus.todo
    if progress >= 100:
        return WorkItemStatus.done
    if progress > 0:
        return WorkItemStatus.in_progress
    return WorkItemStatus.todo


def priority_from_level(level: int | None) -> Priority:
    if level == 1:
        return Priority.high
    if level == 3:
        return Priority.medium
    return Priority.medium


def create(
    session: Session,
    parent_id: int | None,
    *,
    progress: int | None = None,
    priority_level: int | None = 1,
    **kwargs,
) -> WorkItem:
    if progress is not None:
        kwargs["progress"] = progress
        kwargs["status"] = status_from_progress(progress)
    kwargs["priority"] = priority_from_level(priority_level)
    data = WorkItemCreate(parent_id=parent_id, type=WorkItemType.planned, **kwargs)
    return create_work_item(session, data)


def main() -> None:
    init_db()
    with Session(engine) as session:
        root = session.exec(
            select(WorkItem).where(WorkItem.title == "结论辅助生成智能体")
        ).first()
        if root:
            has_reports = session.exec(
                select(WorkItem).where(
                    WorkItem.parent_id == root.id,
                    WorkItem.title == "总部两个报告",
                )
            ).first()
            if has_reports:
                print("Schedule already imported (root: 结论辅助生成智能体). Skipping.")
                return
            session.delete(root)
            session.commit()

        if session.exec(select(WorkItem).where(WorkItem.title == "负荷异动分析智能体")).first():
            print("负荷异动分析智能体 already exists. Skipping duplicate root.")
            load_root = None
        else:
            load_root = "pending"

        root = create(
            session,
            None,
            title="结论辅助生成智能体",
            description="结论辅助生成智能体项目总计划",
            start_date="2026-05-11",
            due_date="2026-06-12",
            progress=21,
            priority_level=1,
        )

        reports = create(
            session,
            root.id,
            title="总部两个报告",
            start_date="2026-05-11",
            due_date="2026-06-12",
            progress=22,
            priority_level=1,
        )

        create(
            session,
            reports.id,
            title="缓冲",
            start_date="2026-06-01",
            due_date="2026-06-12",
            progress=0,
            priority_level=1,
        )
        create(
            session,
            reports.id,
            title="全链路测试",
            start_date="2026-05-25",
            due_date="2026-05-29",
            progress=0,
            priority_level=1,
        )
        create(
            session,
            reports.id,
            title="改造实施，在页面新加模板",
            start_date="2026-05-18",
            due_date="2026-05-22",
            progress=10,
            priority_level=1,
        )

        env_prep = create(
            session,
            reports.id,
            title="前期环境准备",
            start_date="2026-05-11",
            due_date="2026-05-22",
            progress=58,
            priority_level=1,
        )
        create(
            session,
            env_prep.id,
            title="结论辅助生成智能体部署",
            start_date="2026-05-11",
            due_date="2026-05-15",
            progress=100,
            priority_level=1,
        )

        api_debug = create(
            session,
            reports.id,
            title="接口调试",
            start_date="2026-05-18",
            due_date="2026-05-22",
            progress=17,
            priority_level=1,
        )
        create(
            session,
            api_debug.id,
            title="市场信息接入继续推进",
            start_date="2026-05-18",
            due_date="2026-05-22",
            progress=50,
            priority_level=1,
        )
        create(
            session,
            api_debug.id,
            title="住房空置率propmt约束",
            start_date="2026-05-18",
            due_date="2026-05-22",
            progress=0,
            priority_level=1,
        )
        create(
            session,
            api_debug.id,
            title="两个报告数据与实际差异大，需要验证",
            start_date="2026-05-18",
            due_date="2026-05-22",
            progress=0,
            priority_level=1,
        )

        create(
            session,
            reports.id,
            title="总部两个报告交付",
            description="里程碑",
            start_date="2026-06-12",
            due_date="2026-06-12",
            progress=0,
            priority_level=1,
        )

        create(
            session,
            None,
            title="未命名任务",
            start_date="2026-05-12",
            due_date="2026-05-12",
            progress=0,
            priority_level=None,
        )

        if load_root == "pending":
            create(
                session,
                None,
                title="负荷异动分析智能体",
                description="负荷异动分析智能体项目",
                start_date="2026-06-01",
                due_date="2026-06-30",
                progress=0,
                priority_level=3,
            )

        imported = session.exec(
            select(WorkItem).where(WorkItem.title == "结论辅助生成智能体")
        ).first()
        child_count = len(
            session.exec(select(WorkItem).where(WorkItem.parent_id == imported.id)).all()
        ) if imported else 0
        total = len(session.exec(select(WorkItem)).all())
        print(
            f"Imported 结论辅助生成智能体 schedule "
            f"({child_count} direct children under root). Total work items: {total}"
        )


if __name__ == "__main__":
    main()
