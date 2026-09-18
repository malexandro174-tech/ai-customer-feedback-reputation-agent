from datetime import timedelta

from app.database import Base, configure_database, engine, session_scope
from app.models import utcnow
from app.sandbox_source import SandboxReviewSource


def test_sandbox_source_persists_review(tmp_path):
    configure_database(f"sqlite+pysqlite:///{tmp_path / 'reviews.sqlite'}")
    Base.metadata.create_all(engine())
    with session_scope() as session:
        review = SandboxReviewSource().create_review(session, author_name="Марина", text="Спасибо, отличный сервис")
        review_id = review.id
    with session_scope() as session:
        stored = session.get(type(review), review_id)
        assert stored is not None
        assert stored.status == "NEW"
        assert SandboxReviewSource().health_check(session) is True


def test_retry_backoff_hides_future_candidate(tmp_path):
    configure_database(f"sqlite+pysqlite:///{tmp_path / 'backoff.sqlite'}")
    Base.metadata.create_all(engine())
    source = SandboxReviewSource()
    with session_scope() as session:
        review = source.create_review(session, author_name="Олег", text="Нужна помощь")
        review.status = "RETRY_PENDING"
        review.next_retry_at = utcnow() + timedelta(minutes=3)
    with session_scope() as session:
        assert source.fetch_candidates(session, 10) == []
