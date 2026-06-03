@echo off
echo === PM Agent Desktop Builder ===
echo.

if not exist .venv-build (
    echo Creating clean virtual environment...
    python -m venv .venv-build
    .venv-build\Scripts\pip install fastapi uvicorn sqlmodel python-dotenv openai jinja2 python-multipart pywebview pystray Pillow pyinstaller
)

echo Building...
.venv-build\Scripts\pyinstaller --onefile --windowed --name "pm-agent" --add-data "templates;templates" --add-data "static;static" --hidden-import pystray --hidden-import PIL --hidden-import PIL.Image --hidden-import PIL.ImageDraw --hidden-import PIL.ImageFont --hidden-import app --hidden-import app.main --hidden-import app.config --hidden-import app.db --hidden-import app.models --hidden-import app.schemas --hidden-import app.routers --hidden-import app.services --hidden-import app.routers.chat --hidden-import app.routers.work_items --hidden-import app.routers.weekly_log --hidden-import app.services.agent --hidden-import app.services.work_items --hidden-import app.services.operation_log --hidden-import app.services.weekly_report --hidden-import app.services.schedules --collect-data webview desktop/main.py

echo.
echo Build complete. Output: dist\pm-agent.exe
echo Size:
dir dist\pm-agent.exe
pause
