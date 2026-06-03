import json
from datetime import date, datetime, timedelta

from openai import OpenAI
from sqlmodel import Session, select

from app.config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL
from app.models import OperationAction, WeeklyReport, WorkItem, WorkItemStatus
from app.services import operation_log as op_log

SYSTEM_PROMPT = """你是项目管理周报助手。根据本周操作日志和当前任务状态，生成两部分内容：
1. 本周工作总结：归纳已完成、推进中、遇到的问题，条理清晰。
2. 下周工作计划：基于未完成任务、截止日期和阻塞项，给出可执行的计划。

要求：
- 使用中文，Markdown 分点列出
- 简洁务实，适合直接发给团队或自己复盘
- 不要编造日志里没有的内容
- 如果信息不足，明确说明还需要补充什么"""


def get_saved_report(session: Session, week_key: str) -> WeeklyReport | None:
    return session.exec(select(WeeklyReport).where(WeeklyReport.week_key == week_key)).first()


def collect_open_tasks(session: Session) -> list[dict]:
    items = list(
        session.exec(
            select(WorkItem).where(WorkItem.status != WorkItemStatus.done).order_by(WorkItem.due_date)
        ).all()
    )
    result = []
    for item in items:
        result.append(
            {
                "id": item.id,
                "title": item.title,
                "status": item.status.value,
                "assignee": item.assignee,
                "progress": item.progress,
                "start_date": item.start_date.isoformat() if item.start_date else None,
                "due_date": item.due_date.isoformat() if item.due_date else None,
            }
        )
    return result


def generate_report(session: Session, week_key: str) -> WeeklyReport:
    entries = op_log.list_operations(session, week_key)
    existing = get_saved_report(session, week_key)
    if existing:
        session.delete(existing)
        session.commit()

    if not entries and not LLM_API_KEY:
        report = WeeklyReport(
            week_key=week_key,
            this_week_summary="本周暂无操作记录。",
            next_week_plan="请先在系统中更新任务或向 Agent 汇报进展。",
            generated_at=datetime.utcnow(),
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        return report

    start, end = op_log.parse_week_key(week_key)
    next_week_start = end + timedelta(days=1)
    next_week_end = next_week_start + timedelta(days=6)

    log_lines = [
        f"[{entry.created_at:%m-%d %H:%M}] {entry.action.value}: {entry.message}"
        for entry in reversed(entries)
    ]
    open_tasks = collect_open_tasks(session)

    user_prompt = f"""周次：{week_key}（{start} 至 {end}）

## 本周操作日志
{chr(10).join(log_lines) if log_lines else "（无）"}

## 当前未完成任务
{json.dumps(open_tasks, ensure_ascii=False, indent=2)}

## 下周日期范围
{next_week_start} 至 {next_week_end}

请输出 JSON，格式：
{{
  "this_week_summary": "...",
  "next_week_plan": "..."
}}"""

    if not LLM_API_KEY:
        summary = "本周操作记录：\n" + "\n".join(f"- {line}" for line in log_lines[:20])
        plan = "下周待办（基于当前未完成任务）：\n" + "\n".join(
            f"- {task['title']}（进度 {task['progress']}%，截止 {task['due_date'] or '未设置'}）"
            for task in open_tasks[:15]
        )
        report = WeeklyReport(
            week_key=week_key,
            this_week_summary=summary or "本周暂无操作记录。",
            next_week_plan=plan or "暂无待办任务。",
            generated_at=datetime.utcnow(),
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        return report

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)

    report = WeeklyReport(
        week_key=week_key,
        this_week_summary=payload.get("this_week_summary", "（未生成）"),
        next_week_plan=payload.get("next_week_plan", "（未生成）"),
        generated_at=datetime.utcnow(),
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    op_log.record_operation(
        session,
        OperationAction.agent,
        f"生成 {week_key} 周报",
    )
    return report
