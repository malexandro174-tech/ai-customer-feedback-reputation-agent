from app.models import Review
from app.processor import response_mode_for
from app.schemas import ResponseMode


def review(sentiment: str, risk: str) -> Review:
    return Review(external_review_id="test", author_name="Test", text="text", sentiment=sentiment, risk_level=risk)


def test_safe_positive_is_auto_safe():
    assert response_mode_for(review("POSITIVE", "LOW")) == ResponseMode.AUTO_SAFE


def test_negative_requires_approval():
    assert response_mode_for(review("NEGATIVE", "LOW")) == ResponseMode.APPROVAL_REQUIRED


def test_critical_is_blocked():
    assert response_mode_for(review("NEUTRAL", "CRITICAL")) == ResponseMode.BLOCKED
