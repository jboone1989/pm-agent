# Worklog API 集成设计

**日期**: 2026-06-03
**分支**: `desktop`

## 概述

PM Agent 集成 Worklog 外部 API，实现：拉取项目 → 本地建任务 → 推送覆盖远端 → 拉取日志更新进展 → 周报总结。

## 数据模型变更

`WorkItem` 新增字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `remote_id` | int, nullable | Worklog 远端 task/project ID |
| `remote_source` | str, nullable | `"worklog"` 标识来源 |

`remote_id` 同时用于 project 和 task：project 存 worklog project_id，task 存 worklog task_id。

## 新增配置

`.env`:
```
WORKLOG_API_KEY=wlg_xxx
WORKLOG_API_BASE=https://k1.xaytzn.com/worklog/api/v1
```

## 架构

```
app/
  services/
    worklog_client.py   # HTTP client for Worklog API
    sync.py             # sync logic: pull projects, push tasks, pull logs
  routers/
    sync.py             # API endpoints: POST /api/sync/pull-projects, etc.
```

### worklog_client.py

封装所有 Worklog API 调用：
- `get_projects()` → `GET /projects`
- `get_tasks(project_id)` → `GET /projects/{id}/tasks`
- `create_task(project_id, data)` → `POST /projects/{id}/tasks`
- `update_task(task_id, data)` → `PUT /tasks/{id}`
- `delete_task(task_id)` → `DELETE /tasks/{id}`
- `get_logs(project_id, start_date, end_date)` → `GET /logs`

### sync.py

同步逻辑：
- `pull_projects(session)` → 拉取 worklog 项目，按 `remote_id` upsert 到 WorkItem（type=planned, parent_id=None）
- `push_tasks(session, project_id)` → 将该 project 下的本地 tasks 推送到 worklog：有 remote_id 的 update，无 remote_id 的 create
- `pull_logs(session, project_id, start_date, end_date)` → 拉取日志，按 project + date 汇总，更新对应 task 的 progress

### 前端

- 项目列表旁加"从 Worklog 拉取"按钮
- 项目内加"推送任务到 Worklog"按钮
- 项目内加"拉取日志"按钮（可选日期范围）

## 同步流程

### 拉取项目
1. 调 worklog GET /projects
2. 对每个 project：已存在（remote_id 匹配）→ 更新 title/description；不存在 → 创建 WorkItem(type=planned, remote_id=project.id)
3. 返回拉取结果（新建 N 个，更新 M 个）

### 推送任务
1. 查询该 project 下所有 WorkItem（type=planned, parent_id=project_item.id）
2. 对每个子任务：
   - 有 remote_id → PUT /tasks/{remote_id}
   - 无 remote_id → POST /projects/{remote_project_id}/tasks，保存返回的 task.id 到 remote_id
3. 返回推送结果

### 拉取日志
1. 调 worklog GET /logs?project_id=X&start_date=Y&end_date=Z
2. 按日期汇聚到 activity log
3. 更新对应 task 的 progress（根据日志条数/工时推算）
4. 返回拉取的日志条数

## 缓存后端改进

无。目前 32MB exe，集成后预计增加 2-3KB 代码。
