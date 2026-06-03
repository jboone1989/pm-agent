# PM Agent 桌面端设计

**日期**: 2026-06-03
**分支**: `desktop`

## 概述

PM Agent 从 Web 应用改为独立 Windows 桌面应用。保持现有代码不变，新增桌面启动层。

## 技术选型

- **PyWebView**: 用系统 WebView2 嵌入前端，约 30-50MB
- **PyInstaller**: 打包为单个 .exe
- **pystray + Pillow**: 系统托盘图标
- **FastAPI**: 后台线程运行，不做 HTTP 端口绑定（只监听 127.0.0.1）

## 架构

```
desktop/
  __init__.py
  main.py        # 入口函数
  tray.py        # 托盘图标与菜单
  build.bat      # PyInstaller 打包脚本

app/              # 现有代码不变
static/           # 现有前端不变
templates/        # 现有模板不变
```

- FastAPI 在后台线程启动（daemon 线程，绑定 127.0.0.1:8000）
- PyWebView 加载 `http://127.0.0.1:8000`
- 关闭窗口 → 隐藏到系统托盘，进程不退出
- 托盘菜单：显示窗口 / 退出
- 数据库和 .env 放在 exe 同目录

## 新增依赖

- `pywebview` — 桌面窗口
- `pystray` — 系统托盘
- `Pillow` — 托盘图标生成
- `pyinstaller` — 打包（dev 依赖）

## 打包

`pyinstaller --onefile --windowed --name pm-agent desktop/main.py`
输出: `dist/pm-agent.exe`
