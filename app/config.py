import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_IS_FROZEN = getattr(sys, "frozen", False)

if _IS_FROZEN:
    _EXE_DIR = Path(sys.executable).resolve().parent
    load_dotenv(_EXE_DIR / ".env")
else:
    _EXE_DIR = Path(__file__).resolve().parent.parent
    load_dotenv()

BASE_DIR = _EXE_DIR
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'pm_agent.db'}")

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")


def _normalize_base_url(url: str) -> str:
    url = url.rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


LLM_API_BASE = _normalize_base_url(LLM_API_BASE)

WORKLOG_API_KEY = os.getenv("WORKLOG_API_KEY", "")
WORKLOG_API_BASE = os.getenv("WORKLOG_API_BASE", "https://k1.xaytzn.com/worklog/api/v1")
