from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .broker import BrokerClient, BrokerError
from .classifier import classify_review, fallback_response, generate_response
from .models import Notification, ProcessingEvent, ResponseApproval, Review, utcnow
from .sandbox_source import SandboxReviewSource
from .schemas import ResponseMode, RiskLevel, Sentiment


def response_mode_for(review: Review) -> ResponseMode:
    if review.risk_level == RiskLevel.CRITICAL.value:
        return ResponseMode.BLOCKED
    if review.risk_level in {RiskLevel.HIGH.value, RiskLevel.MEDIUM.value} or review.sentiment in {Sentiment.NEGATIVE.value, Sentiment.MIXED.value, Sentiment.UNKNOWN.value}:
        return ResponseMode.APPROVAL_REQUIRED
    return ResponseMode.AUTO_SAFE


def _event(session: Session, review: Review, event_type: str, **payload: str | int | bool) -> None:
    session.add(ProcessingEvent(review_id=review.id, event_type=event_type, correlation_id=review.correlation_id, payload=payload))


def claim_reviews(session: Session, source: SandboxReviewSource, limit: int = 20) -> list[str]:
    """Atomically moves candidates to PROCESSING; a restart cannot reprocess completed rows."""
    claimed: list[str] = []
    for review in source.fetch_candidates(session, limit):
        changed = session.execute(
            update(Review).where(Review.id == review.id, Review.status.in_(["NEW", "RETRY_PENDING"])).values(status="PROCESSING", processing_attempts=Review.processing_attempts + 1, last_error=None)
        )
        if changed.rowcount == 1:
            claimed.append(review.id)
    session.flush()
    return claimed


def _notification_text(review: Review) -> str:
    return (
        "🆕 Новый отзыв — требуется внимание\n"
        f"Риск: {review.risk_level}; тональность: {review.sentiment}\n"
        f"Статус: {review.status}; тема: {review.topic or 'не определена'}\n"
        f"Review: {review.id}"
    )


def _notify_once(session: Session, review: Review, broker: BrokerClient) -> None:
    needs_notification = review.sentiment == Sentiment.NEGATIVE.value or review.risk_level in {RiskLevel.HIGH.value, RiskLevel.CRITICAL.value} or review.response_mode == ResponseMode.APPROVAL_REQUIRED.value
    if not needs_notification:
        return
    notification = session.scalar(select(Notification).where(Notification.review_id == review.id, Notification.notification_type == "REVIEW_ESCALATION"))
    if notification is None:
        notification = Notification(
            review_id=review.id,
            notification_type="REVIEW_ESCALATION",
            correlation_id=review.correlation_id,
            safe_payload={"risk_level": review.risk_level, "sentiment": review.sentiment},
            status="PENDING",
        )
        session.add(notification)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            notification = session.scalar(select(Notification).where(Notification.review_id == review.id, Notification.notification_type == "REVIEW_ESCALATION"))
    # A delivery failure is retried only after an explicit, controlled transition
    # to RETRY_PENDING.  The unique review/type constraint remains the idempotency
    # boundary, so this never creates another Telegram alert record.
    if notification is None or notification.status not in {"PENDING", "RETRY_PENDING"}:
        return
    # Persist IN_FLIGHT before the network call. A worker restart never creates a duplicate alert.
    notification.status = "IN_FLIGHT"
    notification.attempts += 1
    session.commit()
    try:
        outcome = broker.send_test_notification(_notification_text(review))
    except BrokerError:
        notification.status = "DELIVERY_REVIEW_REQUIRED"
        _event(session, review, "NOTIFICATION_DELIVERY_REVIEW_REQUIRED")
        session.commit()
        return
    notification.status = "SENT"
    notification.provider_message_id = str(outcome.get("message_id"))
    notification.sent_at = utcnow()
    _event(session, review, "NOTIFICATION_SENT", target_registered=True)
    session.commit()


def process_claimed_review(session: Session, review_id: str, source: SandboxReviewSource, broker: BrokerClient) -> str:
    review = session.get(Review, review_id)
    if review is None or review.status != "PROCESSING":
        return "SKIPPED"
    try:
        classification = classify_review(review.text, broker)
        review.sentiment = classification.sentiment.value
        review.risk_level = classification.risk_level.value
        review.topic = classification.topic
        review.response_mode = response_mode_for(review).value
        _event(session, review, "CLASSIFIED", confidence=round(classification.confidence, 2), risk=review.risk_level)
        if review.response_mode == ResponseMode.BLOCKED.value:
            review.status = "ESCALATED"
            session.add(ResponseApproval(review_id=review.id, status="BLOCKED", reason="CRITICAL risk requires operator review"))
            _event(session, review, "RESPONSE_BLOCKED", reason="CRITICAL_RISK")
        else:
            try:
                response_text = generate_response(review.text, classification, broker)
            except (BrokerError, ValueError):
                response_text = fallback_response(classification)
                _event(session, review, "RESPONSE_FALLBACK_USED")
            if review.response_mode == ResponseMode.AUTO_SAFE.value:
                source.publish_response(session, review, response_text)
                review.status = "PROCESSED"
                _event(session, review, "RESPONSE_AUTO_PUBLISHED")
            else:
                review.response_text = response_text
                review.status = "AWAITING_APPROVAL"
                session.add(ResponseApproval(review_id=review.id, status="PENDING", reason="Policy requires human approval"))
                _event(session, review, "RESPONSE_AWAITING_APPROVAL")
        review.processed_at = utcnow()
        session.commit()
        _notify_once(session, review, broker)
        return review.status
    except Exception as exc:
        session.rollback()
        review = session.get(Review, review_id)
        if review:
            review.status = "RETRY_PENDING" if review.processing_attempts < 3 else "FAILED"
            review.next_retry_at = utcnow() + timedelta(seconds=30 * max(1, review.processing_attempts))
            review.last_error = type(exc).__name__[:120]
            _event(session, review, "PROCESSING_FAILED", failure_class=type(exc).__name__)
            session.commit()
        return "FAILED"
