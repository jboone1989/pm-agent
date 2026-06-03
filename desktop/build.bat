@echo off
echo === PM Agent Desktop Builder ===
echo.

pyinstaller --onefile --windowed --name "pm-agent" --add-data "templates;templates" --add-data "static;static" --hidden-import pystray --hidden-import PIL --hidden-import PIL.Image --hidden-import PIL.ImageDraw --hidden-import PIL.ImageFont --collect-data webview desktop/main.py

echo.
echo Build complete. Output: dist\pm-agent.exe
pause
