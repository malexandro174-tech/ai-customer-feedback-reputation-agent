import json

from sqlalchemy import select

from app.database import Base, configure_database, engine, session_scope
from app.broker import BrokerError
from app.models import Notification, Review
from app.processor import _notify_once, claim_reviews, process_claimed_review
from app.sandbox_source import SandboxReviewSource


class FakeBroker:
    def __init__(self):
        self.notifications = []

    def complete(self, capability, messages, response_json=False):
        return {"choices": [{"message": {"content": json.dumps({"response_text": "Спасибо за обратную связь, мы всё проверим."})}}]}

    def send_test_notification(self, text):
        self.notifications.append(text)
        return {"status": "PASS", "target_registered": True, "message_id": 101}


class FailingNotificationBroker(FakeBroker):
    def send_test_notification(self, text):
        raise BrokerError("TELEGRAM_DELIVERY_FAILED")


def setup_database(tmp_path):
    configure_database(f"sqlite+pysqlite:///{tmp_path / 'processing.sqlite'}")
    Base.metadata.drop_all(engine())
    Base.metadata.create_all(engine())


def test_safe_review_is_processed_once(tmp_path):
    setup_database(tmp_path)
    source, broker = SandboxReviewSource(), FakeBroker()
    with session_scope() as session:
        review = source.create_review(session, author_name="Ирина", text="Спасибо, всё отлично")
        review_id = review.id
        assert claim_reviews(session, source) == [review_id]
    with session_scope() as session:
        assert process_claimed_review(session, review_id, source, broker) == "PROCESSED"
    with session_scope() as session:
        stored = session.get(Review, review_id)
        assert stored.status == "PROCESSED"
        assert stored.response_text
        assert process_claimed_review(session, review_id, source, broker) == "SKIPPED"


def test_negative_review_notifies_only_once(tmp_path):
    setup_database(tmp_path)
    source, broker = SandboxReviewSource(), FakeBroker()
    with session_scope() as session:
        review = source.create_review(session, author_name="Ирина", text="Ужасный сервис, ничего не работает")
        review_id = review.id
        claim_reviews(session, source)
    with session_scope() as session:
        assert process_claimed_review(session, review_id, source, broker) == "AWAITING_APPROVAL"
    with session_scope() as session:
        notification = session.scalar(select(Notification).where(Notification.review_id == review_id))
        assert notification is not None and notification.status == "SENT"
        assert notification.attempts == 1
    assert len(broker.notifications) == 1
    assert broker.notifications[0].startswith("🆕 Новый отзыв — требуется внимание\n")


def test_controlled_retry_reuses_the_existing_notification(tmp_path):
    setup_database(tmp_path)
    source = SandboxReviewSource()
    with session_scope() as session:
        review = source.create_review(session, author_name="Ирина", text="Ужасный сервис, ничего не работает")
        review_id = review.id
        claim_reviews(session, source)
    with session_scope() as session:
        assert process_claimed_review(session, review_id, source, FailingNotificationBroker()) == "AWAITING_APPROVAL"
        notification = session.scalar(select(Notification).where(Notification.review_id == review_id))
        assert notification is not None and notification.status == "DELIVERY_REVIEW_REQUIRED"
        notification.status = "RETRY_PENDING"
    broker = FakeBroker()
    with session_scope() as session:
        review = session.get(Review, review_id)
        assert review is not None
        _notify_once(session, review, broker)
        notifications = list(session.scalars(select(Notification).where(Notification.review_id == review_id)))
        assert len(notifications) == 1
        assert notifications[0].status == "SENT"
        assert notifications[0].attempts == 2
    assert len(broker.notifications) == 1
