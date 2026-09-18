from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .broker import BrokerClient, BrokerError
from .schemas import ClassificationOutput, GeneratedResponse, RiskLevel, Sentiment


POSITIVE = ("спасибо", "отличн", "понрав", "быстро", "рекоменд", "супер", "удобн")
NEGATIVE = ("плохо", "ужас", "ошиб", "не работает", "разочар", "долго", "хам", "проблем")
CRITICAL = ("угроза", "мошенн", "обман", "списали", "утечк", "персональн", "здоров", "травм")
HIGH = ("суд", "юрист", "жалоб", "деньги", "возврат", "безопасност")


@dataclass(frozen=True)
class RuleDecision:
    result: ClassificationOutput
    requires_llm: bool


def rule_prefilter(text: str) -> RuleDecision:
    normalized = text.lower().strip()
    pos = any(word in normalized for word in POSITIVE)
    neg = any(word in normalized for word in NEGATIVE)
    critical = any(word in normalized for word in CRITICAL)
    high = any(word in normalized for word in HIGH)
    risk = RiskLevel.CRITICAL if critical else RiskLevel.HIGH if high else RiskLevel.LOW
    if pos and not neg:
        return RuleDecision(ClassificationOutput(sentiment=Sentiment.POSITIVE, confidence=.92, topic="positive_feedback", risk_level=risk, short_reason="Положительный маркер"), risk != RiskLevel.LOW)
    if neg and not pos:
        return RuleDecision(ClassificationOutput(sentiment=Sentiment.NEGATIVE, confidence=.90, topic="service_issue", risk_level=risk, short_reason="Негативный маркер"), risk != RiskLevel.LOW)
    if pos and neg:
        return RuleDecision(ClassificationOutput(sentiment=Sentiment.MIXED, confidence=.55, topic="mixed_feedback", risk_level=risk, short_reason="Противоречивые маркеры"), True)
    if len(normalized) < 14:
        return RuleDecision(ClassificationOutput(sentiment=Sentiment.UNKNOWN, confidence=.20, topic="insufficient_context", risk_level=risk, short_reason="Недостаточно контекста"), True)
    return RuleDecision(ClassificationOutput(sentiment=Sentiment.NEUTRAL, confidence=.50, topic="general_feedback", risk_level=risk, short_reason="Требуется семантическая оценка"), True)


def _message_content(result: dict) -> str:
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise BrokerError("INVALID_LLM_RESPONSE") from exc
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", str(content).strip(), flags=re.I)


def classify_review(text: str, broker: BrokerClient) -> ClassificationOutput:
    decision = rule_prefilter(text)
    # Deterministic safety markers are a floor, never an input the model may downgrade.
    if not decision.requires_llm or decision.result.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
        return decision.result
    system = (
        "Ты классифицируешь клиентские отзывы. Верни только JSON с полями sentiment "
        "(POSITIVE, NEGATIVE, NEUTRAL, MIXED, UNKNOWN), confidence (0..1), topic, "
        "risk_level (LOW, MEDIUM, HIGH, CRITICAL), short_reason. Не придумывай факты."
    )
    result = broker.complete("CLASSIFICATION", [{"role": "system", "content": system}, {"role": "user", "content": text}], response_json=True)
    return ClassificationOutput.model_validate(json.loads(_message_content(result)))


def generate_response(review_text: str, classification: ClassificationOutput, broker: BrokerClient) -> str:
    prompt = (
        "Подготовь короткий, вежливый ответ на отзыв на русском языке. "
        "Не обещай компенсацию, не раскрывай данные и не спорь с клиентом. "
        "Верни только JSON: {\"response_text\": \"...\"}.\n"
        f"Тональность: {classification.sentiment.value}; риск: {classification.risk_level.value}; отзыв: {review_text}"
    )
    result = broker.complete("CHAT_COMPLETION", [{"role": "system", "content": "Ты помощник службы клиентского опыта."}, {"role": "user", "content": prompt}], response_json=True)
    return GeneratedResponse.model_validate(json.loads(_message_content(result))).response_text


def fallback_response(classification: ClassificationOutput) -> str:
    if classification.sentiment == Sentiment.POSITIVE:
        return "Спасибо за ваш отзыв. Нам очень приятно, что ваш опыт оказался положительным."
    if classification.sentiment == Sentiment.NEGATIVE:
        return "Спасибо, что сообщили о ситуации. Мы внимательно разберёмся в деталях и вернёмся с решением."
    return "Спасибо за обратную связь. Мы учтём её при улучшении сервиса."
