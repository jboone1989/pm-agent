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
    load_dotenv(_EXE_DIR / ".env")

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


def _normalize_worklog_base_url(url: str) -> str:
    url = url.rstrip("/")
    if url.endswith("/api/v1"):
        return url
    if url.endswith("/api"):
        return f"{url}/v1"
    return f"{url}/api/v1"


LLM_API_BASE = _normalize_base_url(LLM_API_BASE)

WORKLOG_API_KEY = os.getenv("WORKLOG_API_KEY", "")
_raw_worklog_base = os.getenv("WORKLOG_API_BASE") or os.getenv(
    "WORKLOG_BASE_URL", "https://k1.xaytzn.com/worklog"
)
WORKLOG_API_BASE = _normalize_worklog_base_url(_raw_worklog_base)

WORKLOG_SYNC_INTERVAL_SEC = int(os.getenv("WORKLOG_SYNC_INTERVAL_SEC", "300"))
WORKLOG_SYNC_LOOKBACK_DAYS = int(os.getenv("WORKLOG_SYNC_LOOKBACK_DAYS", "30"))
WORKLOG_AUTO_PUSH = os.getenv("WORKLOG_AUTO_PUSH", "false").lower() in ("1", "true", "yes")
WORKLOG_ACCOUNT_NAME = os.getenv("WORKLOG_ACCOUNT_NAME", "")
WORKLOG_ACCOUNT_USERNAME = os.getenv("WORKLOG_ACCOUNT_USERNAME", "")
