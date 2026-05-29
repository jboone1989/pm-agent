import json
import re
from datetime import date, timedelta
from collections.abc import Generator
from typing import Any

import anthropic
from sqlmodel import Session

from app.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_BASE_URL,
    ANTHROPIC_MODEL,
)
from app.models import ActivitySource, WorkItem, WorkItemStatus, WorkItemType
from app.schemas import WorkItemCreate, WorkItemUpdate
from app.services import work_items as work_item_service

TASK_REF_RE = re.compile(r"#(\d+)(?:「([^」]+)」)?")

MAX_ROUNDS = 8

TOOLS = [
    {
        "name": "create_work_item",
        "description": "创建新的工作项（项目、子任务或临时事项）",
        "input_schema": {
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
    {
        "name": "update_work_item",
        "description": "更新已有工作项",
        "input_schema": {
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
    {
        "name": "search_work_items",
        "description": "模糊搜索工作项",
        "input_schema": {
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
    {
        "name": "add_activity",
        "description": "为工作项添加进展记录",
        "input_schema": {
            "type": "object",
            "properties": {
                "work_item_id": {"type": "integer"},
                "content": {"type": "string"},
            },
            "required": ["work_item_id", "content"],
        },
    },
    {
        "name": "split_work_item",
        "description": "将一个大任务拆成多个子任务",
        "input_schema": {
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
]


def _extract_task_ids(message: str) -> list[int]:
    return list(dict.fromkeys(int(match.group(1)) for match in TASK_REF_RE.finditer(message)))


def _build_system_prompt(session: Session, message: str) -> str:
    """Build a concise system prompt. Don't dump all items — let the model search."""
    items = work_item_service.list_all_work_items(session)
    assignees = work_item_service.list_assignees(session)

    # Summary only: counts by status, top-level projects
    status_counts = {}
    projects = []
    for item in items:
        status_counts[item.status.value] = status_counts.get(item.status.value, 0) + 1
        if item.parent_id is None:
            projects.append({"id": item.id, "title": item.title, "status": item.status.value})

    today = date.today().isoformat()

    # If user references specific IDs, include those details
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

    return f"""你是项目管理助手，用中文回复。

## 数据库概览
共 {len(items)} 个任务，状态分布：{json.dumps(status_counts, ensure_ascii=False)}
人员：{json.dumps(assignees, ensure_ascii=False)}
今天：{today}

## 顶层项目
{json.dumps(projects, ensure_ascii=False)}
{ref_hint}
## 工具说明
- 需要查任务详情时用 search_work_items，不要猜
- planned=计划任务，ad_hoc=临时任务
- 日期 YYYY-MM-DD，年份 {today[:4]}
- progress=100 自动标记完成
- 创建子任务设置 parent_id"""


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

    if name == "split_work_item":
        children = [
            WorkItemCreate(**_normalize_create_arguments(session, child, user_message))
            for child in arguments.get("children", [])
        ]
        created = work_item_service.split_work_item(session, arguments["parent_id"], children)
        changed_ids.extend(item.id for item in created)
        return json.dumps([_serialize_item(i) for i in created], ensure_ascii=False), changed_ids

    return json.dumps({"error": f"unknown tool {name}"}, ensure_ascii=False), changed_ids


def run_agent(session: Session, message: str) -> tuple[str, list[str], list[int]]:
    if not ANTHROPIC_API_KEY:
        return (
            "请先在 .env 中配置 ANTHROPIC_API_KEY 后再使用 Agent。",
            [],
            [],
        )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)
    system_prompt = _build_system_prompt(session, message)
    messages: list[dict[str, Any]] = [{"role": "user", "content": message}]
    actions: list[str] = []
    changed_ids: list[int] = []

    for _ in range(MAX_ROUNDS):
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=TOOLS,
        )

        text_parts: list[str] = []
        tool_uses: list[dict[str, Any]] = []
        assistant_content: list[dict[str, Any]] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_uses.append({"id": block.id, "name": block.name, "input": block.input})
                assistant_content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})

        messages.append({"role": "assistant", "content": assistant_content})

        if not tool_uses:
            reply = "\n".join(text_parts) if text_parts else "已处理。"
            return reply, actions, list(dict.fromkeys(changed_ids))

        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            result, ids = execute_tool(session, tu["name"], tu["input"], message)
            actions.append(f"{tu['name']}({json.dumps(tu['input'], ensure_ascii=False)})")
            changed_ids.extend(ids)
            tool_results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": result})

        messages.append({"role": "user", "content": tool_results})

    return "操作步骤较多，请拆成更小的指令再试。", actions, list(dict.fromkeys(changed_ids))


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _tool_label(name: str, args: dict[str, Any]) -> str:
    labels = {
        "create_work_item": f"创建任务「{args.get('title', '')}」",
        "update_work_item": f"更新任务 #{args.get('id', '')}",
        "search_work_items": f"搜索「{args.get('query', '')}」",
        "add_activity": f"记录进展到 #{args.get('work_item_id', '')}",
        "split_work_item": f"拆分子任务 #{args.get('parent_id', '')}",
    }
    return labels.get(name, name)


def run_agent_stream(session: Session, message: str) -> Generator[str, None, None]:
    """Generator yielding SSE event strings for real-time frontend updates.

    Events:
        text: model's streaming text chunks
        tool_start: about to execute a tool
        tool_end: tool execution result
        done: final result with changed_item_ids
    """
    if not ANTHROPIC_API_KEY:
        yield _sse("text", {"text": "请先在 .env 中配置 ANTHROPIC_API_KEY 后再使用 Agent。"})
        yield _sse("done", {"reply": "未配置 API Key", "changed_item_ids": []})
        return

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, base_url=ANTHROPIC_BASE_URL)
    system_prompt = _build_system_prompt(session, message)
    messages: list[dict[str, Any]] = [{"role": "user", "content": message}]
    all_changed_ids: list[int] = []
    actions: list[str] = []

    for _ in range(MAX_ROUNDS):
        yield _sse("status", {"text": "正在思考..."})

        try:
            with client.messages.stream(
                model=ANTHROPIC_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=TOOLS,
            ) as stream:
                for text_chunk in stream.text_stream:
                    yield _sse("text", {"text": text_chunk})
                final = stream.get_final_message()
        except Exception:
            # Streaming not supported, fall back to non-streaming
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
                tools=TOOLS,
            )
            final = response
            # Yield all text at once since we can't stream token-by-token
            for block in final.content:
                if block.type == "text":
                    yield _sse("text", {"text": block.text})

        text_parts: list[str] = []
        tool_uses: list[dict[str, Any]] = []
        assistant_content: list[dict[str, Any]] = []

        for block in final.content:
            if block.type == "text":
                text_parts.append(block.text)
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_uses.append({"id": block.id, "name": block.name, "input": block.input})
                assistant_content.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})

        messages.append({"role": "assistant", "content": assistant_content})

        if not tool_uses:
            reply = "\n".join(text_parts) if text_parts else "已处理。"
            yield _sse("done", {"reply": reply, "changed_item_ids": list(dict.fromkeys(all_changed_ids)), "actions": actions})
            return

        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            yield _sse("tool_start", {
                "tool": tu["name"],
                "label": _tool_label(tu["name"], tu["input"]),
                "args": tu["input"],
            })
            result, ids = execute_tool(session, tu["name"], tu["input"], message)
            all_changed_ids.extend(ids)
            actions.append(f"{tu['name']}({json.dumps(tu['input'], ensure_ascii=False)})")
            yield _sse("tool_end", {
                "tool": tu["name"],
                "label": _tool_label(tu["name"], tu["input"]),
                "result": result[:500],
            })
            tool_results.append({"type": "tool_result", "tool_use_id": tu["id"], "content": result})

        messages.append({"role": "user", "content": tool_results})

    yield _sse("done", {"reply": "操作步骤较多，请拆成更小的指令再试。", "changed_item_ids": list(dict.fromkeys(all_changed_ids)), "actions": actions})
