# Desktop App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert PM Agent from browser-based web app to standalone Windows desktop app with system tray support.

**Architecture:** FastAPI runs in a daemon thread on 127.0.0.1; PyWebView embeds the frontend in a native window; closing the window minimizes to a pystray system tray icon with show/exit menu.

**Tech Stack:** pywebview, pystray, Pillow, PyInstaller (on top of existing FastAPI + SQLite stack)

---

### Task 1: Add desktop dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Append desktop deps to requirements.txt**

```
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
sqlmodel>=0.0.22
python-dotenv>=1.0.1
openai>=1.55.0
jinja2>=3.1.4
python-multipart>=0.0.12
pywebview>=5.3.0
pystray>=0.19.5
Pillow>=11.1.0
```

- [ ] **Step 2: Install new dependencies**

Run: `pip install pywebview pystray Pillow`

- [ ] **Step 3: Commit**

```
git add requirements.txt
git commit -m "chore: add pywebview, pystray, Pillow for desktop support"
```

---

### Task 2: Create desktop/tray.py — system tray module

**Files:**
- Create: `desktop/__init__.py`
- Create: `desktop/tray.py`

- [ ] **Step 1: Create `desktop/__init__.py`** (empty)

```python
```

- [ ] **Step 2: Create `desktop/tray.py`**

```python
import threading
from PIL import Image, ImageDraw, ImageFont
import pystray


def _make_icon_image(size: int = 64) -> Image.Image:
    """Generate a simple PM icon: blue square with white 'PM' text."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = size // 8
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=size // 6,
        fill=(59, 130, 246),
    )
    text = "PM"
    font = None
    for font_size in range(size, 1, -2):
        try:
            font = ImageFont.truetype("msyh.ttc", font_size)
            break
        except (OSError, IOError):
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
                break
            except (OSError, IOError):
                pass
    if font is None:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2), text, fill="white", font=font)
    return img


class SystemTray:
    def __init__(self, on_show, on_exit):
        self._on_show = on_show
        self._on_exit = on_exit
        self._icon = None

    def setup(self):
        menu = pystray.Menu(
            pystray.MenuItem("显示窗口", self._on_show, default=True),
            pystray.MenuItem("退出", self._on_exit),
        )
        self._icon = pystray.Icon("pm_agent", _make_icon_image(), "PM Agent", menu)
        threading.Thread(target=self._icon.run, daemon=True).start()

    def stop(self):
        if self._icon:
            self._icon.stop()

    def notify(self, title: str, message: str):
        if self._icon and hasattr(self._icon, "notify"):
            self._icon.notify(message, title)
```

- [ ] **Step 3: Commit**

```
git add desktop/__init__.py desktop/tray.py
git commit -m "feat: add system tray module with icon generator"
```

---

### Task 3: Create desktop/main.py — desktop entry point

**Files:**
- Create: `desktop/main.py`

- [ ] **Step 1: Create `desktop/main.py`**

```python
from __future__ import annotations

import os
import sys
import threading
import time

import uvicorn
import webview

from desktop.tray import SystemTray

PORT = 8000
ROOT_URL = f"http://127.0.0.1:{PORT}"


def _start_api_server():
    """Run FastAPI in a daemon thread."""
    config = uvicorn.Config(
        "app.main:app",
        host="127.0.0.1",
        port=PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    server.run()


def main():
    # Start API server in background thread
    api_thread = threading.Thread(target=_start_api_server, daemon=True)
    api_thread.start()

    # Wait for server to be ready
    for _ in range(50):
        try:
            import urllib.request
            urllib.request.urlopen(ROOT_URL)
            break
        except Exception:
            time.sleep(0.1)

    # Create window
    window = webview.create_window("PM Agent", ROOT_URL, width=1280, height=800, min_size=(900, 600))

    # Tray setup
    def on_show():
        window.show()
        window.restore()

    def on_exit():
        window.destroy()
        os._exit(0)

    tray = SystemTray(on_show, on_exit)

    # Override close to minimize to tray
    window.events.closing += lambda: (window.hide(), tray.setup())[0]

    tray.setup()
    webview.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```
git add desktop/main.py
git commit -m "feat: add desktop entry point with webview + tray"
```

---

### Task 4: Add PyInstaller build script

**Files:**
- Create: `desktop/build.bat`

- [ ] **Step 1: Create `desktop/build.bat`**

```bat
@echo off
echo === PM Agent Desktop Builder ===
echo.

pyinstaller --onefile --windowed --name "pm-agent" --add-data "templates;templates" --add-data "static;static" --hidden-import pystray --hidden-import PIL --hidden-import PIL.Image --hidden-import PIL.ImageDraw --collect-data webview desktop/main.py

echo.
echo Build complete. Output: dist\pm-agent.exe
pause
```

- [ ] **Step 2: Commit**

```
git add desktop/build.bat
git commit -m "feat: add PyInstaller build script"
```

---

### Task 5: End-to-end manual verification

**No code changes — run the app and verify behavior.**

- [ ] **Step 1: Start the desktop app**

Run: `python -m desktop.main`  (or `python desktop/main.py`)

- [ ] **Step 2: Verify the window opens and the app loads**

Expected: PM Agent window appears at 1280x800, frontend loads, chat and work items are functional.

- [ ] **Step 3: Verify close-to-tray behavior**

Close the window (click X). Expected: window hides, system tray icon appears. Right-click tray icon → "显示窗口" restores the window.

- [ ] **Step 4: Verify exit from tray**

Right-click tray icon → "退出". Expected: window closes, process exits cleanly.
