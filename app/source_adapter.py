from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from .models import Review


class ReviewSourceAdapter(ABC):
    """Source boundary. Real external sources can be added without changing processing."""

    source_name: str

    @abstractmethod
    def health_check(self, session: Session) -> bool: ...

    @abstractmethod
    def create_review(self, session: Session, *, author_name: str, text: str, external_review_id: str | None = None) -> Review: ...

    @abstractmethod
    def fetch_candidates(self, session: Session, limit: int) -> list[Review]: ...

    @abstractmethod
    def publish_response(self, session: Session, review: Review, response_text: str) -> None: ...
