from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Review
from .schemas import EscalationRequest, IncidentSummary, KpiSnapshot, ReputationSummary, UpwardReport


class DirectorCommandService:
    """Director-ready contracts only; no external director system is called."""

    def __init__(self, session: Session):
        self.session = session

    def _reviews(self) -> list[Review]:
        return list(self.session.scalars(select(Review)))

    def kpi_snapshot(self) -> KpiSnapshot:
        reviews = self._reviews()
        return KpiSnapshot(
            sentiment_distribution=dict(Counter(r.sentiment for r in reviews)),
            risk_distribution=dict(Counter(r.risk_level for r in reviews)),
            processed_reviews=sum(r.status in {"PROCESSED", "AWAITING_APPROVAL", "ESCALATED"} for r in reviews),
        )

    def upward_report(self) -> UpwardReport:
        reviews = self._reviews()
        completed = [r for r in reviews if r.processed_at]
        minutes = [max(0, (r.processed_at - r.created_at).total_seconds() / 60) for r in completed]
        return UpwardReport(
            total_reviews=len(reviews),
            negative_reviews=sum(r.sentiment == "NEGATIVE" for r in reviews),
            critical_reviews=sum(r.risk_level == "CRITICAL" for r in reviews),
            average_response_minutes=round(sum(minutes) / len(minutes), 2) if minutes else None,
            summary="Агрегированные показатели репутационного контура.",
        )

    def reputation_summary(self) -> ReputationSummary:
        reviews = self._reviews()
        positive = sum(r.sentiment == "POSITIVE" for r in reviews)
        negative = sum(r.sentiment == "NEGATIVE" for r in reviews)
        index = round((positive - negative) / len(reviews) * 100, 1) if reviews else 0.0
        topics = [topic for topic, _ in Counter(r.topic for r in reviews if r.topic).most_common(5)]
        return ReputationSummary(sentiment_index=index, main_topics=topics, open_escalations=sum(r.status in {"ESCALATED", "AWAITING_APPROVAL"} for r in reviews))

    def incident_summary(self, review_id: str) -> IncidentSummary:
        review = self.session.get(Review, review_id)
        if not review:
            raise KeyError(review_id)
        return IncidentSummary(review_id=review.id, risk_level=review.risk_level, summary=f"{review.sentiment}: {review.topic or 'без темы'}")

    def escalation_request(self, review_id: str) -> EscalationRequest:
        review = self.session.get(Review, review_id)
        if not review:
            raise KeyError(review_id)
        return EscalationRequest(review_id=review.id, reason=f"Risk {review.risk_level}", requested_action="Review and approve the proposed response")
