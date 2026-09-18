from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Sentiment(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    MIXED = "MIXED"
    UNKNOWN = "UNKNOWN"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ResponseMode(str, Enum):
    AUTO_SAFE = "AUTO_SAFE"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    BLOCKED = "BLOCKED"


class ClassificationOutput(BaseModel):
    sentiment: Sentiment
    confidence: float = Field(ge=0, le=1)
    topic: str = Field(min_length=2, max_length=120)
    risk_level: RiskLevel
    short_reason: str = Field(min_length=2, max_length=500)


class GeneratedResponse(BaseModel):
    response_text: str = Field(min_length=5, max_length=1200)


class UpwardReport(BaseModel):
    report_type: Literal["UPWARD_REPORT"] = "UPWARD_REPORT"
    total_reviews: int
    negative_reviews: int
    critical_reviews: int
    average_response_minutes: float | None
    summary: str


class KpiSnapshot(BaseModel):
    report_type: Literal["KPI_SNAPSHOT"] = "KPI_SNAPSHOT"
    sentiment_distribution: dict[str, int]
    risk_distribution: dict[str, int]
    processed_reviews: int


class IncidentSummary(BaseModel):
    report_type: Literal["INCIDENT_SUMMARY"] = "INCIDENT_SUMMARY"
    review_id: str
    risk_level: RiskLevel
    summary: str


class EscalationRequest(BaseModel):
    report_type: Literal["ESCALATION_REQUEST"] = "ESCALATION_REQUEST"
    review_id: str
    reason: str
    requested_action: str


class ReputationSummary(BaseModel):
    report_type: Literal["REPUTATION_SUMMARY"] = "REPUTATION_SUMMARY"
    sentiment_index: float
    main_topics: list[str]
    open_escalations: int
