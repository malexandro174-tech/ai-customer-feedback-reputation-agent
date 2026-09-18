from __future__ import annotations

import argparse
import logging
import time

from .broker import BrokerClient
from .config import get_settings
from .database import database_healthy, init_db, session_scope
from .models import ProcessingRun, utcnow
from .processor import claim_reviews, process_claimed_review
from .sandbox_source import SandboxReviewSource

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_once(limit: int = 20, broker: BrokerClient | None = None) -> dict[str, int]:
    init_db()
    source, broker = SandboxReviewSource(), broker or BrokerClient()
    with session_scope() as session:
        run = ProcessingRun()
        session.add(run)
        session.flush()
        run_id = run.id
        claimed = claim_reviews(session, source, limit)
        run.claimed_count = len(claimed)
    completed = failed = 0
    for review_id in claimed:
        with session_scope() as session:
            result = process_claimed_review(session, review_id, source, broker)
            completed += result in {"PROCESSED", "AWAITING_APPROVAL", "ESCALATED"}
            failed += result == "FAILED"
    with session_scope() as session:
        run = session.get(ProcessingRun, run_id)
        assert run is not None
        run.status = "COMPLETED" if not failed else "COMPLETED_WITH_ERRORS"
        run.processed_count, run.failed_count, run.completed_at = completed, failed, utcnow()
    return {"claimed": len(claimed), "processed": completed, "failed": failed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    if args.health:
        raise SystemExit(0 if database_healthy() else 1)
    if args.once:
        logger.info("worker run: %s", run_once())
        return
    settings = get_settings()
    while True:
        try:
            logger.info("worker run: %s", run_once())
        except Exception as exc:
            logger.exception("worker cycle failure class=%s", type(exc).__name__)
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
