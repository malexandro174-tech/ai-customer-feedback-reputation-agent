from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus


def _read_secret(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    return path.read_text(encoding="utf-8").strip() if path.is_file() else None


@dataclass(frozen=True)
class Settings:
    app_name: str
    environment: str
    root_path: str
    database_url: str
    broker_url: str
    requester_id: str
    worker_poll_seconds: int
    public_base_url: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    direct_url = os.getenv("DATABASE_URL")
    if direct_url:
        database_url = direct_url
    else:
        password = _read_secret(os.getenv("DATABASE_PASSWORD_FILE"))
        if not password:
            raise RuntimeError("DATABASE_PASSWORD_FILE is required when DATABASE_URL is not configured")
        user = quote_plus(os.getenv("DATABASE_USER", "reputation"))
        host = os.getenv("DATABASE_HOST", "review-db")
        name = os.getenv("DATABASE_NAME", "reputation")
        database_url = f"postgresql+psycopg://{user}:{quote_plus(password)}@{host}:5432/{name}"
    return Settings(
        app_name="AI Customer Feedback & Reputation Agent",
        environment=os.getenv("APP_ENV", "TEST"),
        root_path=os.getenv("ROOT_PATH", ""),
        database_url=database_url,
        broker_url=os.getenv("BROKER_URL", "http://mag-access-broker-runtime:8101"),
        requester_id="ai_feedback_reputation_agent",
        worker_poll_seconds=max(5, int(os.getenv("WORKER_POLL_SECONDS", "15"))),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost:8000"),
    )
