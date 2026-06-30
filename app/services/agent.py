import json
import re
from collections.abc import Generator
from datetime import date, timedelta
from typing import Any

from openai import OpenAI
from sqlmodel import Session

from app.config import LLM_API_BASE, LLM_API_KEY, LLM_MODEL
from app.models import ActivitySource, WorkItem, WorkItemStatus, WorkItemType
from app.schemas import WorkItemCreate, WorkItemUpdate, WorkLogCreate
from app.services import work_items as work_item_service
from app.services import work_logs as work_log_service

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
            "description": "添加会议/日程/提醒等临时备忘，不记入任务列表。仅用于记录讨论内容本身，待办事项仍需create_work_item。日期格式YYYY-MM-DD",
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
    {
        "type": "function",
        "function": {
            "name": "log_work",
            "description": "记录个人已完成的工作活动及用时（已发生的事实），不是新建任务。用于汇报做了什么、花了多长时间。如果同时有任务关联，调用此工具后还应调用add_activity记录进展。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "工作内容描述"},
                    "duration_minutes": {"type": ["integer", "null"], "description": "花费的分钟数，如不确定可不填"},
                    "log_date": {"type": ["string", "null"], "description": "日期 YYYY-MM-DD，默认今天"},
                    "work_item_id": {"type": ["integer", "null"], "description": "关联的任务ID（如有）"},
                },
                "required": ["content"],
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

    # Include today's existing work logs for context
    today_logs = work_log_service.list_work_logs(session, log_date=date.today(), limit=10)
    work_log_context = ""
    if today_logs:
        log_lines = []
        for wl in today_logs:
            duration_str = f"（{wl.duration_minutes}分钟）" if wl.duration_minutes else ""
            log_lines.append(f"  - {wl.content}{duration_str}")
        work_log_context = "\n## 今天已记录的工作日志\n" + "\n".join(log_lines)

    return f"""你是一个项目管理+个人工作日志助手。中文回复，对话式，像一个可靠的工作伙伴。

今天={today}。任务总数{len(items)}。顶层项目：{json.dumps(projects, ensure_ascii=False)}。人员：{assignees}。
{ref_hint}
{work_log_context}

## 收到消息后，按以下流程思考：

### 步骤1：理解意图
判断用户消息属于哪种类型（可能是多种混合）：
A) 汇报工作（"今天做了XX"、"开了个会"、"写完了文档"）
B) 提出新需求（"需要做XX"、"能不能加XX"）
C) 会议/日程/提醒（"下午XX开会"、"明天要XX"）
D) 更新已有任务（"XX做完了"、"XX卡住了"）
E) 查询信息（"有哪些任务"、"XX进度怎么样"）
F) 混合类型（"上午写了文档，下午开了评审会，需要修改3个地方"）

### 步骤2：识别信息缺口
根据类型判断缺失的关键信息：

A类（汇报工作）→ 必须主动问：
- 用了多长时间？（对应log_work的duration_minutes）
- 关联到哪个任务？（对应work_item_id）
- 如果提到了待办事项，要create任务并问：什么时候完成？谁来负责？

B类（新需求）→ 必须主动问：
- 什么时候完成？（due_date）
- 谁来负责？（assignee）

C类（会议/日程）→ 问清楚：
- 如果是日程提醒：用add_daily_note记录
- 如果提到了会议中的待办事项：每个待办必须create任务，并追问due_date和assignee

D类（更新任务）→ 如果只说"更新了XX"但没有具体内容，必须追问

### 步骤3：决定行动
- 信息充足 → 直接执行所有需要的工具调用
- 部分信息缺失 → 先执行已知部分，再追问缺失的信息
- 关键信息缺失 → 先问清楚再执行，不要替用户假设

### 步骤4：执行或询问
工具选择指南：
- log_work → 记录已完成的工作及用时（已发生的事）
- create_work_item → 创建新任务/待办事项（需要做的事）
- update_work_item → 更新已有任务状态/进度
- add_daily_note → 记录会议/日程备忘（临时、不计入任务列表）
- add_activity → 在任务下添加进展备注或讨论背景
- split_work_item → 拆分子任务
- search_work_items → 搜索已有任务

## 关键原则
- **信息不足时主动追问**：不要替用户做假设。缺少时间、负责人、截止日期等信息时，执行已知操作的同时追问。
- **混合场景**：用户经常同时汇报工作+提出待办。先log_work记录已完成的工作，再create待办任务，然后追问缺失信息。
- **关联操作**：log_work时如果关联了任务（work_item_id），同时调add_activity记录进展到该任务。
- **不要重复记录**：检查"今天已记录的工作日志"，如果内容明显重复就不要再log_work。
- **只汇报实际调用了工具的操作**。ad_hoc=临时任务。
- **不要输出大段说明文字**：直接做事+简短追问，字数控制在80字以内。

## 对话示例

用户："我今天用2小时写完了需求文档"
你：log_work(content="编写需求文档", duration_minutes=120) → 回复："已记录，2小时。关联到哪个任务？"

用户："下午开了项目A评审会，需要输出设计方案"
你：log_work(content="项目A评审会") + add_daily_note(content="评审会讨论内容...") + create_work_item(title="输出设计方案", parent_id=项目A的ID) → 回复："已记录会议。设计方案的任务已创建，什么时候完成？谁来负责？"

用户："#15 登录功能做完了"
你：update_work_item(id=15, progress=100) → 回复："已标记完成。用了多长时间？我帮你记工作日志。"

用户："下周一前需要完成测试报告"
你：create_work_item(title="测试报告", due_date=下周一) → 回复："已创建。谁来负责这个任务？"""


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

    if name == "log_work":
        payload = WorkLogCreate(**arguments)
        log = work_log_service.create_work_log(session, payload)
        return json.dumps({
            "id": log.id,
            "content": log.content,
            "duration_minutes": log.duration_minutes,
            "log_date": log.log_date.isoformat(),
            "work_item_id": log.work_item_id,
        }, ensure_ascii=False), changed_ids

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
        "log_work": f"记录工作日志：{args.get('content', '')[:30]}",
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
