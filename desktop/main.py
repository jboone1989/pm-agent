import os
import sys
import threading
import time
import urllib.request

import uvicorn
import webview

import app.main  # force PyInstaller to bundle app package
from desktop.tray import SystemTray

PORT = 8000
ROOT_URL = f"http://127.0.0.1:{PORT}"


def _start_api_server():
    config = uvicorn.Config(
        "app.main:app",
        host="127.0.0.1",
        port=PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    server.run()


def main():
    api_thread = threading.Thread(target=_start_api_server, daemon=True)
    api_thread.start()

    for _ in range(50):
        try:
            urllib.request.urlopen(ROOT_URL)
            break
        except Exception:
            time.sleep(0.1)

    window = webview.create_window(
        "PM Agent", ROOT_URL, width=1280, height=800, min_size=(900, 600)
    )

    def on_show():
        window.show()
        window.restore()

    def on_exit():
        window.destroy()
        os._exit(0)

    tray = SystemTray(on_show, on_exit)
    tray.setup()

    def on_closing():
        window.hide()
        return True

    window.events.closing += on_closing
    webview.start()


if __name__ == "__main__":
    main()
