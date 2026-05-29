from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'pm_agent.db'}")

LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.openai.com/v1")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY") or LLM_API_KEY
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def normalize_llm_base_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


LLM_API_BASE = normalize_llm_base_url(LLM_API_BASE)
