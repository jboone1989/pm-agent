import json
import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from openai import OpenAI
from sqlmodel import Session, select

from app.config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL
from app.models import ActivityLog, ActivitySource, OperationAction, WeeklyReport, WorkItem, WorkItemStatus
from app.services import operation_log as op_log
from app.services.work_items import get_root_item

_WORKLOG_LINE_RE = re.compile(
    r"^\[Worklog(?:#(\d+))?\s+(\d{4}-\d{2}-\d{2})(?:\s+([^\]]+))?\]\s*(.*)",
    re.DOTALL,
)

THIS_WEEK_SYSTEM_PROMPT = """你是项目管理周报助手。根据各具体任务本周的工作日志，撰写本周工作总结。

要求：
- Markdown 格式：输入中有几个任务，就必须输出几个「## 任务名」章节，一一对应，禁止合并
- 不要用「## 项目名」作为章节；项目名如需提及，在任务段落里一笔带过即可
- 每个任务写一段过程描述：该任务本周经历了怎样的推进（做了哪些事、如何深入、遇到什么问题、目前到哪一步）
- 正文不要出现具体人名、日期、星期
- 要体现过程脉络，不要只写一句结论
- 不要编造日志中没有的内容
- 某任务无日志时可写「本周无记录」"""

NEXT_WEEK_SYSTEM_PROMPT = """你是项目管理周报助手。根据当前未完成任务列表，撰写下周工作计划。

要求：
- 使用中文，Markdown 格式
- 每个具体任务单独一节，用「## 任务名」作标题（不要用项目名作章节）
- 每个任务写清：当前进度、本周遗留、下周具体动作、截止日期与风险
- 简洁务实，可执行
- 如果信息不足，说明还需补充什么"""


def get_saved_report(session: Session, week_key: str) -> WeeklyReport | None:
    return session.exec(select(WeeklyReport).where(WeeklyReport.week_key == week_key)).first()


def _is_project_container(session: Session, task: WorkItem, root: WorkItem) -> bool:
    """项目根节点（有子任务时）不算具体任务，周报应写到子任务上。"""
    if task.id != root.id or task.parent_id is not None:
        return False
    child = session.exec(
        select(WorkItem.id).where(WorkItem.parent_id == task.id).limit(1)
    ).first()
    return child is not None


def _parse_worklog_activity(content: str) -> tuple[int | None, date | None, str, str]:
    match = _WORKLOG_LINE_RE.match(content.strip())
    if not match:
        return None, None, "", content.strip()
    worklog_id = int(match.group(1)) if match.group(1) else None
    log_date = date.fromisoformat(match.group(2))
    username = (match.group(3) or "").strip()
    body = (match.group(4) or "").strip()
    return worklog_id, log_date, username, body


def _dedupe_logs(logs: list[dict]) -> list[dict]:
    """同一天、同一内容的日志只保留一条（优先保留带填写人的记录）。"""
    sorted_logs = sorted(
        logs,
        key=lambda row: (
            row["log_date"],
            0 if row.get("username") else 1,
            row.get("username", ""),
        ),
    )
    seen_ids: set[int] = set()
    seen_day_content: set[tuple[str, str]] = set()
    result: list[dict] = []
    for log in sorted_logs:
        worklog_id = log.get("worklog_id")
        day_content = (log["log_date"], log["content"])
        if worklog_id is not None and worklog_id in seen_ids:
            continue
        if day_content in seen_day_content:
            continue
        if worklog_id is not None:
            seen_ids.add(worklog_id)
        seen_day_content.add(day_content)
        result.append(log)
    return result


def _ordered_unique_notes(logs: list[dict]) -> list[str]:
    seen: set[str] = set()
    notes: list[str] = []
    for log in sorted(logs, key=lambda row: row["log_date"]):
        content = log["content"].strip()
        if not content or content in seen:
            continue
        seen.add(content)
        notes.append(content)
    return notes


def collect_task_worklogs(session: Session, start: date, end: date) -> list[dict]:
    """按具体任务（子任务）收集本周 Worklog，不含项目根节点。"""
    activities = session.exec(
        select(ActivityLog)
        .where(ActivityLog.source == ActivitySource.worklog)
        .order_by(ActivityLog.created_at)
    ).all()

    task_map: dict[int, dict] = {}

    for activity in activities:
        worklog_id, log_date, username, body = _parse_worklog_activity(activity.content)
        if log_date is None:
            log_date = activity.created_at.date()
        if log_date < start or log_date > end:
            continue

        task = session.get(WorkItem, activity.work_item_id)
        if not task or task.id is None:
            continue

        root = get_root_item(session, task)
        if root.id is None or _is_project_container(session, task, root):
            continue

        if task.id not in task_map:
            task_map[task.id] = {
                "task_id": task.id,
                "task_title": task.title,
                "project_id": root.id,
                "project_title": root.title,
                "assignee": task.assignee,
                "status": task.status.value,
                "progress": task.progress,
                "logs": [],
            }

        task_map[task.id]["logs"].append(
            {
                "worklog_id": worklog_id,
                "log_date": log_date.isoformat(),
                "username": username,
                "content": body or activity.content,
            }
        )

    tasks = list(task_map.values())
    for task in tasks:
        task["logs"] = _dedupe_logs(task["logs"])
    tasks = [task for task in tasks if task["logs"]]
    tasks.sort(key=lambda row: (row["project_title"], row["task_title"]))
    return tasks


def collect_project_worklogs(session: Session, start: date, end: date) -> list[dict]:
    """供 API / 前端展示：项目 → 任务分组。"""
    grouped: dict[int, dict] = {}
    for task in collect_task_worklogs(session, start, end):
        project_id = task["project_id"]
        if project_id not in grouped:
            grouped[project_id] = {
                "project_id": project_id,
                "project_title": task["project_title"],
                "tasks": [],
            }
        grouped[project_id]["tasks"].append(
            {
                "task_id": task["task_id"],
                "task_title": task["task_title"],
                "assignee": task.get("assignee"),
                "status": task.get("status"),
                "progress": task.get("progress"),
                "logs": task["logs"],
            }
        )
    projects = list(grouped.values())
    for project in projects:
        project["tasks"].sort(key=lambda row: row["task_title"])
    projects.sort(key=lambda row: row["project_title"])
    return projects


def collect_open_tasks(session: Session) -> list[dict]:
    items = list(
        session.exec(
            select(WorkItem).where(WorkItem.status != WorkItemStatus.done).order_by(WorkItem.due_date)
        ).all()
    )
    result = []
    for item in items:
        root = get_root_item(session, item)
        if _is_project_container(session, item, root):
            continue
        result.append(
            {
                "id": item.id,
                "title": item.title,
                "project_id": root.id,
                "project_title": root.title,
                "status": item.status.value,
                "assignee": item.assignee,
                "progress": item.progress,
                "start_date": item.start_date.isoformat() if item.start_date else None,
                "due_date": item.due_date.isoformat() if item.due_date else None,
            }
        )
    return result


def _build_task_process_input(task_worklogs: list[dict]) -> list[dict]:
    return [
        {
            "task_title": task["task_title"],
            "project_title": task["project_title"],
            "status": task.get("status"),
            "progress": task.get("progress"),
            "notes": _ordered_unique_notes(task["logs"]),
        }
        for task in task_worklogs
    ]


def _format_task_process_fallback(task_worklogs: list[dict]) -> str:
    if not task_worklogs:
        return "本周暂无具体任务的 Worklog 记录。请先在项目中拉取日志，并确认日志挂在子任务上。"

    parts: list[str] = []
    for task in task_worklogs:
        parts.append(f"## {task['task_title']}")
        if task["project_title"] != task["task_title"]:
            parts.append(f"> 所属项目：{task['project_title']}")
        notes = _ordered_unique_notes(task["logs"])
        if not notes:
            parts.append("本周无记录。")
        elif len(notes) == 1:
            parts.append(notes[0])
        else:
            text = notes[0]
            for note in notes[1:]:
                text += f"随后，{note}"
            parts.append(text)
        parts.append("")
    return "\n".join(parts).strip()


def _generate_this_week_summary(
    week_key: str,
    start: date,
    end: date,
    task_worklogs: list[dict],
) -> str:
    fallback = _format_task_process_fallback(task_worklogs)
    if not task_worklogs:
        return fallback
    if not LLM_API_KEY:
        return fallback

    task_input = _build_task_process_input(task_worklogs)
    user_prompt = f"""周次：{week_key}（{start} 至 {end}）

以下是本周各具体任务的工作记录（JSON 数组，每个元素对应一个任务）。请为数组中每一个任务各写一节「## 任务名」，不要合并，不要按项目汇总。

{json.dumps(task_input, ensure_ascii=False, indent=2)}

请输出 JSON，格式：
{{
  "this_week_summary": "..."
}}"""

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": THIS_WEEK_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)
    return payload.get("this_week_summary") or fallback


def _format_next_week_plan_fallback(open_tasks: list[dict]) -> str:
    if not open_tasks:
        return "暂无待办任务。"

    parts: list[str] = []
    for task in sorted(open_tasks, key=lambda row: (row["project_title"], row["title"])):
        parts.append(f"## {task['title']}")
        if task["project_title"] != task["title"]:
            parts.append(f"> 所属项目：{task['project_title']}")
        parts.append(
            f"- 当前进度 {task['progress']}%，状态 {task['status']}"
            f"，截止 {task['due_date'] or '未设置'}"
        )
        if task.get("assignee"):
            parts.append(f"- 负责人：{task['assignee']}")
        parts.append("")
    return "\n".join(parts).strip()


def _generate_next_week_plan(
    week_key: str,
    start: date,
    end: date,
    next_week_start: date,
    next_week_end: date,
    open_tasks: list[dict],
) -> str:
    fallback = _format_next_week_plan_fallback(open_tasks)
    if not LLM_API_KEY or not open_tasks:
        return fallback

    user_prompt = f"""周次：{week_key}（本周 {start} 至 {end}）

## 下周日期范围
{next_week_start} 至 {next_week_end}

## 当前未完成任务（每个任务单独一节）
{json.dumps(open_tasks, ensure_ascii=False, indent=2)}

请输出 JSON，格式：
{{
  "next_week_plan": "..."
}}"""

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": NEXT_WEEK_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    payload = json.loads(content)
    return payload.get("next_week_plan") or fallback


def generate_report(session: Session, week_key: str) -> WeeklyReport:
    existing = get_saved_report(session, week_key)
    if existing:
        session.delete(existing)
        session.commit()

    start, end = op_log.parse_week_key(week_key)
    next_week_start = end + timedelta(days=1)
    next_week_end = next_week_start + timedelta(days=6)

    task_worklogs = collect_task_worklogs(session, start, end)
    open_tasks = collect_open_tasks(session)

    summary = _generate_this_week_summary(week_key, start, end, task_worklogs)
    plan = _generate_next_week_plan(
        week_key, start, end, next_week_start, next_week_end, open_tasks
    )

    report = WeeklyReport(
        week_key=week_key,
        this_week_summary=summary,
        next_week_plan=plan,
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
