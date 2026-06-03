import threading
from PIL import Image, ImageDraw, ImageFont
import pystray


def _make_icon_image(size: int = 64) -> Image.Image:
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
        self._setup_done = False

    def setup(self):
        if self._setup_done:
            return
        self._setup_done = True
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
