# PM Agent

用自然语言管理项目：告诉 Agent 发生了什么、有什么进展，它会自动整理成结构化任务，并在 Web 里按列表、按人、按项目查看排期。

## 技术栈

- **FastAPI** — API 与页面服务
- **SQLModel + SQLite** — 本地数据存储
- **OpenAI Tool Calling** — Agent 结构化操作任务

## 快速开始

```bash
cd pm-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# 编辑 .env，填入 LLM_API_KEY 等配置
uvicorn app.main:app --reload
```

浏览器打开 http://127.0.0.1:8000

## 使用方式

在左侧聊天框用中文描述即可，例如：

- `新建项目「用户系统重构」，下周五上线，小李负责后端`
- `登录页做完了，接口还有 401 问题，等后端修`
- `临时：客户 A 投诉账单不对，今天必须回复`

Agent 会自动创建/更新任务、记录进展。右侧可切换：

- **列表** — 树形层级（大工作 → 子任务）
- **按人** — 每个人的计划排期 + 临时跟进
- **按项目** — 每个顶层项目的时间线

点击任意任务可查看详情与完整进展历史。

## 数据备份

数据库文件为项目根目录下的 `pm_agent.db`，复制该文件即可备份。

## 环境变量

| 变量 | 说明 |
|------|------|
| `LLM_API_BASE` | 模型 API 地址（OpenAI 兼容），默认 SiliconFlow / OpenAI |
| `LLM_API_KEY` | API Key |
| `LLM_MODEL` | 模型名称，如 `deepseek-ai/DeepSeek-V3.2` |
| `DATABASE_URL` | 默认 `sqlite:///./pm_agent.db` |

未配置 API Key 时，聊天会提示你配置；CRUD 与视图仍可手动使用（后续可加表单）。
