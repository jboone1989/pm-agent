import json
import re
from datetime import date, timedelta
from typing import Any

from sqlmodel import Session

from app.config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    LLM_API_BASE,
    LLM_API_KEY,
    LLM_MODEL,
    LLM_PROVIDER,
)
from app.models import ActivitySource, WorkItem, WorkItemStatus, WorkItemType
from app.schemas import WorkItemCreate, WorkItemUpdate
from app.services import work_items as work_item_service

SYSTEM_PROMPT = """你是项目管理助手。用户会用自然语言描述项目、任务进展或临时事项。

规则：
1. 始终用中文回复，简洁说明做了什么；有歧义时先追问，不要静默改错任务。
2. 收到消息后先用 search_work_items 查找是否已有相关任务；可用 #id 或任务名搜索。
3. 临时、突发、没有明确计划的事项用 type=ad_hoc。
4. 每次写操作后调用 add_activity 记录用户原话或你的操作摘要。
5. 需要拆分子任务时用 split_work_item；单个新建子任务用 create_work_item 并设置 parent_id。
6. 日期格式 YYYY-MM-DD，必须使用当前年份；负责人用 assignee 字符串。
7. 如果缺少关键信息（负责人、截止日期），可以创建后再在回复里追问。
8. progress 为 0-100 的整数，表示任务完成百分比；用户说「完成了 30%」「进度到 80%」时更新 progress。
9. 用户可能用 @姓名 指负责人，用 #id 或 #id「任务名」指具体工作项；优先按 id 定位任务。
10. 创建子任务时：若标题以某父任务名开头，或用户说「放到 #x 下面/作为子任务」，必须设置 parent_id=x。
11. 用户说「今天/今日完成」时，due_date 必须设为今天；未指定 start_date 时系统会默认今天。"""

TASK_REF_RE = re.compile(r"#(\d+)(?:「([^」]+)」)?")

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_work_item",
            "description": "创建新的工作项（大项目、子任务或临时事项）",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "parent_id": {"type": ["integer", "null"]},
                    "type": {"type": "string", "enum": ["planned", "ad_hoc"]},
                    "status": {
                        "type": "string",
                        "enum": ["todo", "in_progress", "blocked", "done", "cancelled"],
                    },
                    "assignee": {"type": ["string", "null"]},
                    "start_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                    "due_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
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
                    "status": {
                        "type": "string",
                        "enum": ["todo", "in_progress", "blocked", "done", "cancelled"],
                    },
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
            "description": "模糊搜索工作项，用于匹配用户提到的任务",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "assignee": {"type": ["string", "null"]},
                    "status": {
                        "type": "string",
                        "enum": ["todo", "in_progress", "blocked", "done", "cancelled"],
                    },
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
            "description": "为工作项添加进展记录",
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
                                "status": {
                                    "type": "string",
                                    "enum": ["todo", "in_progress", "blocked", "done", "cancelled"],
                                },
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


def _openai_tools_to_anthropic() -> list[dict[str, Any]]:
    """Convert OpenAI-format tool definitions to Anthropic format."""
    anthropic_tools = []
    for tool in TOOLS:
        func = tool["function"]
        anthropic_tools.append({
            "name": func["name"],
            "description": func["description"],
            "input_schema": func["parameters"],
        })
    return anthropic_tools


ANTHROPIC_TOOLS = _openai_tools_to_anthropic()


def _extract_task_ids(message: str) -> list[int]:
    return list(dict.fromkeys(int(match.group(1)) for match in TASK_REF_RE.finditer(message)))


def _build_message_context(session: Session, message: str) -> str:
    ids = _extract_task_ids(message)
    if not ids:
        return ""

    lines = ["用户消息中引用的任务（供创建/更新时设置 parent_id 等）："]
    for item_id in ids:
        item = work_item_service.get_work_item(session, item_id)
        if not item:
            continue
        parent_hint = ""
        if item.parent_id:
            parent = session.get(WorkItem, item.parent_id)
            parent_hint = f"，父任务 #{item.parent_id}「{parent.title if parent else '?'}」"
        lines.append(f"- #{item.id}「{item.title}」parent_id={item.parent_id}{parent_hint}")
    return "\n".join(lines)


def _infer_parent_id_from_title(session: Session, title: str) -> int | None:
    items = work_item_service.list_all_work_items(session)
    matches = [
        item
        for item in items
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
    elif args.get("due_date"):
        due = date.fromisoformat(str(args["due_date"]))
        if due < today - timedelta(days=30):
            args["due_date"] = today.isoformat()

    parent_id = _infer_parent_id(session, args, message)
    if parent_id:
        args["parent_id"] = parent_id

    return args


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


def _run_agent_openai(session: Session, message: str, system_prompt: str) -> tuple[str, list[str], list[int]]:
    from openai import OpenAI

    client = OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]
    actions: list[str] = []
    changed_ids: list[int] = []

    for _ in range(8):
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        choice = response.choices[0]
        assistant_message = choice.message
        messages.append(assistant_message.model_dump(exclude_none=True))

        if not assistant_message.tool_calls:
            reply = assistant_message.content or "已处理。"
            return reply, actions, list(dict.fromkeys(changed_ids))

        for tool_call in assistant_message.tool_calls:
            args = json.loads(tool_call.function.arguments or "{}")
            result, ids = execute_tool(session, tool_call.function.name, args, message)
            actions.append(f"{tool_call.function.name}({json.dumps(args, ensure_ascii=False)})")
            changed_ids.extend(ids)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })

    return "操作步骤较多，请拆成更小的指令再试。", actions, list(dict.fromkeys(changed_ids))


def _run_agent_anthropic(session: Session, message: str, system_prompt: str) -> tuple[str, list[str], list[int]]:
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages: list[dict[str, Any]] = [{"role": "user", "content": message}]
    actions: list[str] = []
    changed_ids: list[int] = []

    for _ in range(8):
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=ANTHROPIC_TOOLS,
        )

        assistant_content: list[dict[str, Any]] = []
        tool_uses: list[dict[str, Any]] = []
        text_parts: list[str] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_uses.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        messages.append({"role": "assistant", "content": assistant_content})

        if not tool_uses:
            reply = "\n".join(text_parts) if text_parts else "已处理。"
            return reply, actions, list(dict.fromkeys(changed_ids))

        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            result, ids = execute_tool(session, tu["name"], tu["input"], message)
            actions.append(f"{tu['name']}({json.dumps(tu['input'], ensure_ascii=False)})")
            changed_ids.extend(ids)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu["id"],
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    return "操作步骤较多，请拆成更小的指令再试。", actions, list(dict.fromkeys(changed_ids))


def run_agent(session: Session, message: str) -> tuple[str, list[str], list[int]]:
    if LLM_PROVIDER == "anthropic":
        if not ANTHROPIC_API_KEY:
            return (
                "请先在 .env 中配置 ANTHROPIC_API_KEY 后再使用 Agent。你也可以直接在右侧视图手动管理工作项。",
                [],
                [],
            )
    else:
        if not LLM_API_KEY:
            return (
                "请先在 .env 中配置 LLM_API_KEY 后再使用 Agent。你也可以直接在右侧视图手动管理工作项。",
                [],
                [],
            )

    context = _build_message_context(session, message)
    system_prompt = SYSTEM_PROMPT if not context else f"{SYSTEM_PROMPT}\n\n{context}"

    if LLM_PROVIDER == "anthropic":
        return _run_agent_anthropic(session, message, system_prompt)
    else:
        return _run_agent_openai(session, message, system_prompt)
