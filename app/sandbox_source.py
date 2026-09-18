from __future__ import annotations

import uuid

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from .models import ProcessingEvent, Review, utcnow
from .source_adapter import ReviewSourceAdapter


class SandboxReviewSource(ReviewSourceAdapter):
    source_name = "SandboxReviewSource"

    def health_check(self, session: Session) -> bool:
        session.execute(text("SELECT 1"))
        return True

    def create_review(self, session: Session, *, author_name: str, text: str, external_review_id: str | None = None) -> Review:
        review = Review(
            source=self.source_name,
            external_review_id=external_review_id or f"sandbox-{uuid.uuid4()}",
            author_name=author_name.strip(),
            text=text.strip(),
            status="NEW",
        )
        session.add(review)
        session.flush()
        session.add(ProcessingEvent(
            review_id=review.id,
            event_type="REVIEW_INGESTED",
            correlation_id=review.correlation_id,
            payload={"source": self.source_name},
        ))
        return review

    def fetch_candidates(self, session: Session, limit: int) -> list[Review]:
        return list(session.scalars(
            select(Review).where(
                Review.source == self.source_name,
                Review.status.in_(["NEW", "RETRY_PENDING"]),
                or_(Review.next_retry_at.is_(None), Review.next_retry_at <= utcnow()),
            ).order_by(Review.created_at).limit(limit)
        ))

    def publish_response(self, session: Session, review: Review, response_text: str) -> None:
        review.response_text = response_text
        session.add(ProcessingEvent(
            review_id=review.id,
            event_type="RESPONSE_PUBLISHED_TO_SANDBOX",
            correlation_id=review.correlation_id,
            payload={"source": self.source_name},
        ))
