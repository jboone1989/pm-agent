import json
import re
from collections.abc import Generator
from datetime import date, timedelta
from typing import Any

from openai import OpenAI
from sqlmodel import Session

from app.config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL
from app.models import ActivitySource, WorkItem, WorkItemStatus, WorkItemType
from app.schemas import WorkItemCreate, WorkItemUpdate
from app.services import work_items as work_item_service

TASK_REF_RE = re.compile(r"#(\d+)(?:「([^」]+)」)?")

MAX_ROUNDS = 5

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_work_item",
            "description": "创建新任务/子任务/项目（不用于会议/日程/提醒等临时安排）",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string", "default": ""},
                    "parent_id": {"type": ["integer", "null"]},
                    "type": {"type": "string", "enum": ["planned", "ad_hoc"]},
                    "status": {"type": "string", "enum": ["todo", "in_progress", "blocked", "done", "cancelled"]},
                    "assignee": {"type": ["string", "null"]},
                    "start_date": {"type": ["string", "null"]},
                    "due_date": {"type": ["string", "null"]},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                    "progress": {"type": "integer", "minimum": 0, "maximum": 100},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_work_item",
            "description": "更新已有工作项",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "parent_id": {"type": ["integer", "null"]},
                    "status": {"type": "string", "enum": ["todo", "in_progress", "blocked", "done", "cancelled"]},
                    "assignee": {"type": ["string", "null"]},
                    "start_date": {"type": ["string", "null"]},
                    "due_date": {"type": ["string", "null"]},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                    "type": {"type": "string", "enum": ["planned", "ad_hoc"]},
                    "progress": {"type": "integer", "minimum": 0, "maximum": 100},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_work_items",
            "description": "模糊搜索工作项",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "assignee": {"type": ["string", "null"]},
                    "status": {"type": "string", "enum": ["todo", "in_progress", "blocked", "done", "cancelled"]},
                    "type": {"type": "string", "enum": ["planned", "ad_hoc"]},
                    "limit": {"type": "integer"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_activity",
            "description": "为任务添加进展备注/状态更新记录（非新建任务）",
            "parameters": {
                "type": "object",
                "properties": {
                    "work_item_id": {"type": "integer"},
                    "content": {"type": "string"},
                },
                "required": ["work_item_id", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_daily_note",
            "description": "添加会议/日程/提醒等临时备忘，不记入任务列表。优先于create_work_item。日期格式YYYY-MM-DD",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "日期，如2026-06-04"},
                    "content": {"type": "string", "description": "备忘内容"},
                },
                "required": ["date", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "split_work_item",
            "description": "将一个大任务拆成多个子任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "parent_id": {"type": "integer"},
                    "children": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "description": {"type": "string"},
                                "assignee": {"type": ["string", "null"]},
                                "due_date": {"type": ["string", "null"]},
                                "status": {"type": "string", "enum": ["todo", "in_progress", "blocked", "done", "cancelled"]},
                                "type": {"type": "string", "enum": ["planned", "ad_hoc"]},
                                "progress": {"type": "integer", "minimum": 0, "maximum": 100},
                            },
                            "required": ["title"],
                        },
                    },
                },
                "required": ["parent_id", "children"],
            },
        },
    },
]


def _extract_task_ids(message: str) -> list[int]:
    return list(dict.fromkeys(int(match.group(1)) for match in TASK_REF_RE.finditer(message)))


def _build_system_prompt(session: Session, message: str) -> str:
    items = work_item_service.list_all_work_items(session)
    assignees = work_item_service.list_assignees(session)

    status_counts = {}
    projects = []
    for item in items:
        status_counts[item.status.value] = status_counts.get(item.status.value, 0) + 1
        if item.parent_id is None:
            projects.append({"id": item.id, "title": item.title, "status": item.status.value})

    today = date.today().isoformat()

    ref_hint = ""
    ref_ids = _extract_task_ids(message)
    if ref_ids:
        ref_lines = []
        for rid in ref_ids:
            item = work_item_service.get_work_item(session, rid)
            if item:
                parent_title = ""
                if item.parent_id:
                    parent = session.get(WorkItem, item.parent_id)
                    parent_title = f"，父任务 #{item.parent_id}「{parent.title if parent else '?'}」"
                ref_lines.append(f"  #{item.id}「{item.title}」状态={item.status.value} 进度={item.progress}%{parent_title}")
        if ref_lines:
            ref_hint = "\n## 用户引用的任务\n" + "\n".join(ref_lines)

    return f"""项目管理助手。中文回复，简洁直接。

今天={today}。任务总数{len(items)}。顶层项目：{json.dumps(projects, ensure_ascii=False)}。人员：{assignees}。
{ref_hint}
规则：用户汇报新需求/新问题必须create。会议/日程/提醒等临时安排只用add_daily_note，禁止create。分配人员调update。只汇报实际调用了工具的操作。ad_hoc=临时。"""


def _serialize_item(item) -> dict[str, Any]:
    return {
        "id": item.id,
        "title": item.title,
        "description": item.description,
        "parent_id": item.parent_id,
        "type": item.type.value,
        "status": item.status.value,
        "assignee": item.assignee,
        "start_date": item.start_date.isoformat() if item.start_date else None,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "priority": item.priority.value,
        "progress": item.progress,
    }


def _infer_parent_id_from_title(session: Session, title: str) -> int | None:
    items = work_item_service.list_all_work_items(session)
    matches = [
        item for item in items
        if len(item.title) >= 4 and title.startswith(item.title) and len(title) > len(item.title)
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: len(item.title), reverse=True)
    return matches[0].id


def _infer_parent_id(session: Session, arguments: dict[str, Any], message: str) -> int | None:
    if arguments.get("parent_id"):
        return arguments["parent_id"]

    title = (arguments.get("title") or "").strip()
    if not title:
        return None

    under_match = re.search(r"(?:放到|挂在|移到|作为.*?子任务|下面|之下).{0,20}?#(\d+)", message)
    if under_match:
        return int(under_match.group(1))

    prefix_parent = _infer_parent_id_from_title(session, title)
    if prefix_parent:
        return prefix_parent

    ids = _extract_task_ids(message)
    if len(ids) == 1 and re.search(r"子任务|下面|之下", message):
        return ids[0]

    for item_id in ids:
        item = work_item_service.get_work_item(session, item_id)
        if item and item.title in title and item.title != title:
            return item.id

    return None


def _normalize_create_arguments(
    session: Session, arguments: dict[str, Any], message: str
) -> dict[str, Any]:
    args = dict(arguments)
    today = date.today()

    if not args.get("start_date"):
        args["start_date"] = today.isoformat()

    if re.search(r"今天|今日", message):
        args["due_date"] = today.isoformat()
    elif re.search(r"明天|明日", message):
        args["due_date"] = (today + timedelta(days=1)).isoformat()

    parent_id = _infer_parent_id(session, args, message)
    if parent_id:
        args["parent_id"] = parent_id

    return args


def execute_tool(
    session: Session, name: str, arguments: dict[str, Any], user_message: str = ""
) -> tuple[str, list[int]]:
    changed_ids: list[int] = []

    if name == "create_work_item":
        arguments = _normalize_create_arguments(session, arguments, user_message)
        payload = WorkItemCreate(**arguments)
        item = work_item_service.create_work_item(session, payload)
        changed_ids.append(item.id)
        return json.dumps(_serialize_item(item), ensure_ascii=False), changed_ids

    if name == "update_work_item":
        item_id = arguments.pop("id")
        payload = WorkItemUpdate(**arguments)
        item = work_item_service.update_work_item(session, item_id, payload)
        if not item:
            return json.dumps({"error": "not found"}, ensure_ascii=False), changed_ids
        changed_ids.append(item.id)
        return json.dumps(_serialize_item(item), ensure_ascii=False), changed_ids

    if name == "search_work_items":
        status = arguments.get("status")
        item_type = arguments.get("type")
        results = work_item_service.search_work_items(
            session,
            query=arguments.get("query", ""),
            assignee=arguments.get("assignee"),
            status=WorkItemStatus(status) if status else None,
            type=WorkItemType(item_type) if item_type else None,
            limit=arguments.get("limit", 20),
        )
        return json.dumps([_serialize_item(i) for i in results], ensure_ascii=False), changed_ids

    if name == "add_activity":
        log = work_item_service.add_activity(
            session,
            work_item_id=arguments["work_item_id"],
            content=arguments["content"],
            source=ActivitySource.agent_action,
        )
        if not log:
            return json.dumps({"error": "not found"}, ensure_ascii=False), changed_ids
        changed_ids.append(log.work_item_id)
        return json.dumps({"id": log.id, "work_item_id": log.work_item_id}, ensure_ascii=False), changed_ids

    if name == "add_daily_note":
        return json.dumps({"date": arguments["date"], "content": arguments["content"]}, ensure_ascii=False), changed_ids

    if name == "split_work_item":
        children = [
            WorkItemCreate(**_normalize_create_arguments(session, child, user_message))
            for child in arguments.get("children", [])
        ]
        created = work_item_service.split_work_item(session, arguments["parent_id"], children)
        changed_ids.extend(item.id for item in created)
        return json.dumps([_serialize_item(i) for i in created], ensure_ascii=False), changed_ids

    return json.dumps({"error": f"unknown tool {name}"}, ensure_ascii=False), changed_ids


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _tool_label(name: str, args: dict[str, Any]) -> str:
    labels = {
        "create_work_item": f"创建任务「{args.get('title', '')}」",
        "update_work_item": f"更新任务 #{args.get('id', '')}",
        "search_work_items": f"搜索「{args.get('query', '')}」",
        "add_activity": f"记录进展到 #{args.get('work_item_id', '')}",
        "split_work_item": f"拆分子任务 #{args.get('parent_id', '')}",
        "add_daily_note": f"添加备忘：{args.get('content', '')[:30]}",
    }
    return labels.get(name, name)


def run_agent(session: Session, message: str, history: list[dict] | None = None) -> tuple[str, list[str], list[int]]:
    """Non-streaming version for backward compatibility."""
    if not LLM_API_KEY:
        return ("请先在 .env 中配置 LLM_API_KEY 后再使用 Agent。", [], [])

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
    system_prompt = _build_system_prompt(session, message)
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        # Keep only last 20 turns to avoid context overflow
        messages.extend(history[-20:])
    messages.append({"role": "user", "content": message})
    actions = []
    changed_ids = []

    for _ in range(MAX_ROUNDS):
        response = client.chat.completions.create(
            model=LLM_MODEL, messages=messages, tools=TOOLS, tool_choice="auto"
        )
        choice = response.choices[0]
        msg = choice.message
        messages.append(msg.model_dump(exclude_none=True))

        if not msg.tool_calls:
            return msg.content or "已处理。", actions, list(dict.fromkeys(changed_ids))

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result, ids = execute_tool(session, tc.function.name, args, message)
            actions.append(f"{tc.function.name}({json.dumps(args, ensure_ascii=False)})")
            changed_ids.extend(ids)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return "操作步骤较多，请拆成更小的指令再试。", actions, list(dict.fromkeys(changed_ids))


def run_agent_stream(session: Session, message: str, history: list[dict] | None = None) -> Generator[str, None, None]:
    """SSE streaming generator with streaming LLM calls for real-time text display."""
    if not LLM_API_KEY:
        yield _sse("text", {"text": "请先在 .env 中配置 LLM_API_KEY 后再使用 Agent。"})
        yield _sse("done", {"reply": "未配置 API Key", "changed_item_ids": [], "actions": []})
        return

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
    system_prompt = _build_system_prompt(session, message)
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        messages.extend(history[-20:])
    messages.append({"role": "user", "content": message})
    all_changed_ids = []
    all_actions = []

    for _ in range(MAX_ROUNDS):
        yield _sse("status", {"text": "正在思考..."})

        stream = client.chat.completions.create(
            model=LLM_MODEL, messages=messages, tools=TOOLS, tool_choice="auto",
            stream=True,
        )

        content_parts = []
        tc_accum: dict[int, dict] = {}  # index → {id, name, arguments_parts}
        text_buf = ""

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue

            if delta.content:
                content_parts.append(delta.content)
                text_buf += delta.content
                if len(text_buf) >= 8 or any(text_buf.endswith(c) for c in ("。", "！", "？", "，", "\n")):
                    yield _sse("text", {"text": text_buf})
                    text_buf = ""

            if delta.tool_calls:
                if text_buf:
                    yield _sse("text", {"text": text_buf})
                    text_buf = ""
                for tc_chunk in delta.tool_calls:
                    idx = tc_chunk.index
                    if idx not in tc_accum:
                        tc_accum[idx] = {"id": "", "name": "", "arguments_parts": []}

                    entry = tc_accum[idx]
                    if tc_chunk.id:
                        entry["id"] = tc_chunk.id
                    if tc_chunk.function:
                        if tc_chunk.function.name and not entry["name"]:
                            entry["name"] = tc_chunk.function.name
                            if text_buf:
                                yield _sse("text", {"text": text_buf})
                                text_buf = ""
                            yield _sse("tool_start", {
                                "tool": tc_chunk.function.name,
                                "label": _tool_label(tc_chunk.function.name, {}),
                                "args": {},
                            })
                        if tc_chunk.function.arguments:
                            entry["arguments_parts"].append(tc_chunk.function.arguments)

        if text_buf:
            yield _sse("text", {"text": text_buf})

        content = "".join(content_parts)

        tool_calls = []
        for idx in sorted(tc_accum.keys()):
            entry = tc_accum[idx]
            args_str = "".join(entry["arguments_parts"])
            tool_calls.append({
                "id": entry["id"],
                "type": "function",
                "function": {"name": entry["name"], "arguments": args_str},
            })

        assistant_msg = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        messages.append(assistant_msg)

        if not tool_calls:
            yield _sse("done", {
                "reply": content or "已处理。",
                "changed_item_ids": list(dict.fromkeys(all_changed_ids)),
                "actions": all_actions,
            })
            return

        for tc_item in tool_calls:
            name = tc_item["function"]["name"]
            args = json.loads(tc_item["function"]["arguments"] or "{}")
            result, ids = execute_tool(session, name, args, message)
            all_changed_ids.extend(ids)
            all_actions.append(f"{name}({json.dumps(args, ensure_ascii=False)})")
            yield _sse("tool_end", {
                "tool": name,
                "label": _tool_label(name, args),
                "result": result[:300],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": tc_item["id"],
                "content": result,
            })

    yield _sse("done", {
        "reply": "操作步骤较多，请拆成更小的指令再试。",
        "changed_item_ids": list(dict.fromkeys(all_changed_ids)),
        "actions": all_actions,
    })
