# PM Agent — Architecture & Coding Conventions

**PM Agent** is a natural language project management system. Users describe work in Chinese → an LLM agent structures it into tasks → a web UI displays timelines, schedules, and progress.

## Tech Stack

- **FastAPI** (>= 0.115.0) — REST API + static/template serving
- **SQLModel** (>= 0.0.22) — SQLAlchemy ORM + Pydantic validator integration; single data model serves as both DB table and API schema
- **SQLite** — Local file-based storage (`pm_agent.db` at project root)
- **OpenAI Tool Calling** (>= 1.55.0) — Agent function definitions and structured tool invocation

## Project Structure

```
app/
  __init__.py
  config.py                    # Environment variables: LLM_API_KEY, LLM_MODEL, LLM_API_BASE, DATABASE_URL
  db.py                        # Database session management (get_session, init_db)
  main.py                      # App initialization, router includes, static/template mounting
  models.py                    # SQLModel tables: WorkItem, ActivityLog, OperationLog, WeeklyReport
  schemas.py                   # Pydantic models: WorkItemCreate, WorkItemRead, ChatRequest, ChatResponse, etc.
  routers/
    chat.py                    # POST /api/chat — calls agent_service.run_agent()
    work_items.py              # CRUD endpoints for work items
    weekly_log.py              # Weekly operation logs and reports
  services/
    agent.py                   # Core agent loop: run_agent() → LLM + tool calling
    work_items.py              # CRUD and search for WorkItem; add_activity() for audit trails
    operation_log.py           # Record user chats and agent actions
    weekly_report.py           # Weekly summary generation (LLM-based)
    schedules.py               # Schedule queries by person/project
static/                        # CSS/JS for frontend
templates/                     # Jinja2 index.html
pm_agent.db                    # SQLite database (auto-created on startup)
```

## Core Concepts

### 1. Work Item Hierarchy

All tasks are `WorkItem` records. A parent-child relationship models:
- **Project** (parent_id=None, type=planned) — Top-level deliverables
- **Subtask** (parent_id=project_id, type=planned) — Tracked work
- **Ad-hoc** (type=ad_hoc, parent_id=None) — Quick/urgent items outside projects

Fields:
- `status`: todo, in_progress, blocked, done, cancelled
- `type`: planned (scheduled) or ad_hoc (unplanned)
- `priority`: low, medium, high, urgent
- `progress`: 0–100 (integer %)
- `assignee`: None or string (person name, typically Chinese)

### 2. Activity Log & Audit Trail

Every work item change or agent action is recorded in `ActivityLog`:
- `source`: user_message or agent_action
- `content`: Note/summary of what happened
- Human-readable history visible in task detail view

**Progress normalization** (`services/work_items.py::normalize_progress`):
- Setting progress to 100 auto-transitions status → `done`
- Setting progress > 0 when status is `todo` auto-transitions → `in_progress`
- This runs on both create and update, so the agent doesn't need to set status explicitly for progress changes

**Cascade delete**: `delete_work_item()` recursively deletes children and their activity logs. There is no soft-delete.

### 3. LLM Agent (Tool-Based Loop)

**Location**: `app/services/agent.py::run_agent(session, message)`

**Flow**:
1. User sends a Chinese message via `/api/chat`
2. System prompt + message context → OpenAI Chat API with tools enabled
3. LLM chooses to call 0+ tools (create/update/search work items, add activity)
4. Each tool call → `execute_tool()` → database operation → result JSON back to LLM
5. Loop max 8 iterations; LLM stops when no more tool calls needed
6. Return: (reply, actions_list, changed_item_ids)

**Available Tools** (system-initialized as LLM function definitions):
- `create_work_item` — Create task; auto parent_id inference from title/message context
- `update_work_item` — Modify status, assignee, progress, etc.
- `search_work_items` — Fuzzy search by query/assignee/status/type
- `add_activity` — Log a note to work item
- `split_work_item` — Batch create subtasks under a parent

### 4. System Prompt & Context Building

**System Prompt** (`SYSTEM_PROMPT` in agent.py):
- All responses in Chinese
- Rules: chase down ambiguity, search before create, use ad_hoc for emergent work, record activities, infer parent_id from titles/message context
- Date format: YYYY-MM-DD (current year)
- Progress updates when user says "30% done" → update progress field

**Message Context**:
- `_build_message_context()` — Detect `#id` references in user message
- Fetch task details (title, parent_id, ancestor) to inform LLM decisions
- Passed as system message context so LLM knows exact task when `#123` is mentioned

### 5. Argument Normalization

**Function**: `_normalize_create_arguments(session, args, message)`

Before passing WorkItemCreate to DB:
- Auto-set `start_date` to today if not provided
- If message contains "今天/今日", set `due_date` to today
- **Parent ID Inference** (key pattern):
  - Check explicit parent_id in args
  - Regex detect "放到 #x 下面/作为子任务"
  - Match new task title prefix against existing tasks (e.g., "项目 A" in "项目 A 后端开发")
  - Single `#id` reference + "子任务" keyword → use that id
  - First matching ancestor in message refs

This makes agent decisions more natural: `"项目 A 的后端开发"` automatically becomes a child of `"项目 A"` if it exists.

## API Patterns

### REST Endpoints (via FastAPI Routers)

```python
# app/routers/work_items.py
GET    /api/work_items              # List all (tree-nested by parent_id)
GET    /api/work_items/flat         # Flat list (no nesting)
GET    /api/work_items/{id}         # Get single work item
POST   /api/work_items              # Create (WorkItemCreate → WorkItemRead)
PATCH  /api/work_items/{id}         # Update (WorkItemUpdate → WorkItemRead)
DELETE /api/work_items/{id}         # Hard delete (cascades to children + activity logs)
GET    /api/work_items/{id}/activities  # Get activity log for a work item
GET    /api/work_items/schedules/by-person  # Tasks grouped by assignee
GET    /api/work_items/schedules/by-project  # Tasks grouped by root project (optional ?project_id=)
GET    /api/work_items/meta/assignees  # Distinct assignee names

# app/routers/chat.py
POST   /api/chat                    # ChatRequest → ChatResponse (reply, actions, changed_item_ids)

# app/routers/weekly_log.py
GET    /api/weekly-log              # Operations in a week (optional ?week=YYYY-WNN)
POST   /api/weekly-log/generate     # Trigger LLM-based weekly summary (optional ?week=)
```

### Session Dependency

```python
from app.db import get_session
from sqlmodel import Session
from fastapi import Depends

@router.post("/example")
def example(session: Session = Depends(get_session)):
    # session auto commits on context exit; errors auto-rollback
    ...
```

## Database Models (SQLModel)

### WorkItem
```python
id, title, description, parent_id, type, status, assignee, start_date, due_date, priority, progress, created_at, updated_at
```
- Self-referential: parent_id → workitem.id

### ActivityLog
```python
id, work_item_id, content, source, created_at
```
- Immutable audit log; only insert, never update

### OperationLog
```python
id, week_key, action, work_item_id, work_item_title, message, created_at
```
- Week-keyed for historical queries (e.g., "what happened in week 2026-W05")
- action: create, update, delete, chat, agent

### WeeklyReport
```python
id, week_key, this_week_summary, next_week_plan, generated_at
```
- Unique per week_key; LLM-generated summaries

## Key Files for Common Tasks

| Task | File(s) |
|------|---------|
| Add new work item field | `models.py` (SQLModel), `schemas.py` (Pydantic), `db.py::migrate_db()` |
| Add new API endpoint | `routers/*.py` (define route + logic) |
| Add new agent tool | `agent.py` (TOOLS list + execute_tool branch) |
| Change LLM behavior | `agent.py` (SYSTEM_PROMPT, argument normalization, tool definitions) |
| Add activity types | `models.py` (ActivitySource enum) |
| Modify DB schema | `models.py` (SQLModel table), then `db.py::migrate_db()` (add ALTER TABLE) |
| Add search filters | `services/work_items.py::search_work_items()` |
| Implement weekly logic | `services/weekly_report.py`, `routers/weekly_log.py` |

## Running & Debugging

### Start Dev Server
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env            # Edit LLM_API_KEY, etc.
uvicorn app.main:app --reload
```
Runs on `http://127.0.0.1:8000`

There are no automated tests in this project.

### Environment Variables (load from `.env`)
- `DATABASE_URL` — Default: `sqlite:///./pm_agent.db` (relative to cwd)
- `LLM_API_KEY` — OpenAI API key (fallback: `OPENAI_API_KEY`)
- `LLM_MODEL` — Model name, e.g. `deepseek-ai/DeepSeek-V3.2` (fallback: `OPENAI_MODEL`, default: `gpt-4o-mini`)
- `LLM_API_BASE` — Base URL for OpenAI-compatible API (default: `https://api.openai.com/v1`)

`config.py` auto-appends `/v1` to `LLM_API_BASE` if not already present via `normalize_llm_base_url()`.

### DB Migrations

There is no migration framework. `db.py::migrate_db()` runs on every startup and performs lightweight, idempotent schema changes (e.g., adding the `progress` column if missing). Add new columns here following the same pattern: check `inspector.get_columns()` first, then `ALTER TABLE` only if the column is absent.

### Debugging Agent Behavior
1. **Check system prompt** in `agent.py::SYSTEM_PROMPT` — controls decision-making
2. **Trace message context** — inspect `_build_message_context()` output (task refs detected)
3. **Review tool calls** — look at returned `actions` list from `/api/chat`
4. **Inspect database** — query `pm_agent.db` directly or via `/api/work_items` endpoints
5. **Monitor LLM calls** — log OpenAI requests/responses if needed (add logging in `run_agent()`)

## Coding Conventions

### Naming & Structure
- **Files**: snake_case (e.g., `weekly_report.py`, `work_items.py`)
- **Classes/Models**: PascalCase (e.g., `WorkItem`, `ActivityLog`)
- **Enums**: snake_case values (e.g., `WorkItemType.planned`, `WorkItemStatus.todo`)
- **Functions**: snake_case (e.g., `create_work_item()`, `run_agent()`)
- **Routers**: Prefix all endpoints with `/api/` (e.g., `/api/chat`, `/api/work_items`)

### Database Operations
- Use SQLModel + SQLAlchemy Session (via `get_session` dependency)
- Always filter/query before modify (paranoia about accidental bulk ops)
- Log significant changes via `add_activity()` (work items) or `record_*()` (operations)

### LLM Integration
- Keep SYSTEM_PROMPT updated when changing agent behavior
- Tool definitions in TOOLS list must match `execute_tool()` branches
- Arguments passed to LLM are JSON; deserialize via `json.loads(tool_call.function.arguments)`
- Normalize/validate arguments before handing to service layer

### Error Handling
- Service functions return data or None (implicit "not found")
- API routes raise FastAPI exceptions (404, 400, 500) for errors
- Agent gracefully degrades (returns fallback message) if no LLM_API_KEY

### Testing & Validation
- Pydantic schemas (`WorkItemCreate`, etc.) auto-validate on construction
- Field validators in schemas (e.g., `progress` clamped 0–100)
- Enum constraints enforced at DB + API level (status ∈ {todo, in_progress, …})

## Common Workflows

### Adding a New Agent Tool
1. **Define schema** — Add parameter object to TOOLS list (function definition)
2. **Implement handler** — Add branch in `execute_tool(session, name, arguments, user_message)`
3. **Call service** — Use functions from `app/services/` (e.g., `work_item_service.create_work_item()`)
4. **Return JSON** — Serialize result via `_serialize_item()` or equivalent, then `json.dumps(..., ensure_ascii=False)`
5. **Update system prompt** — Document tool in SYSTEM_PROMPT rules if needed

### Adding a New API Endpoint
1. **Define schema** — Create request/response models in `schemas.py` (inherit from BaseModel)
2. **Create router** — Add function in `routers/*.py` with `@router.get/post/patch/delete()` decorator
3. **Use session** — Add `session: Session = Depends(get_session)` parameter
4. **Call service** — Use functions from `app/services/`
5. **Return response** — Wrap in response model (FastAPI auto-serializes)

### Updating Agent Decision Logic
1. **Modify SYSTEM_PROMPT** — Adjust rules, context, or instructions
2. **Update tool definitions** — Add/remove tools or change parameter schemas
3. **Refine argument normalization** — Update `_normalize_create_arguments()` or similar
4. **Test with `/api/chat`** — Send test message, inspect actions + results

## Further Reading

- `README.md` — User-facing setup & usage guide
- `app/services/agent.py` — Full agent loop implementation (267+ lines)
- `app/models.py` — Data model definitions
- `app/config.py` — Configuration & environment loading
