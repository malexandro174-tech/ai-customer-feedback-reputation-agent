from app.classifier import classify_review, rule_prefilter
from app.schemas import RiskLevel, Sentiment


def test_positive_rule_is_auto_classified():
    decision = rule_prefilter("Спасибо, всё отлично и очень удобно")
    assert decision.result.sentiment == Sentiment.POSITIVE
    assert decision.requires_llm is False


def test_negative_rule_is_auto_classified():
    decision = rule_prefilter("Ужасный сервис, ничего не работает")
    assert decision.result.sentiment == Sentiment.NEGATIVE


def test_ambiguous_text_requires_llm():
    decision = rule_prefilter("В целом опыт непростой, но хочу уточнить несколько деталей")
    assert decision.requires_llm is True


def test_critical_marker_escalates_risk():
    decision = rule_prefilter("У меня списали деньги, это выглядит как обман")
    assert decision.result.risk_level == RiskLevel.CRITICAL


def test_critical_rule_cannot_be_downgraded_by_llm():
    class BrokerThatMustNotBeCalled:
        def complete(self, *args, **kwargs):
            raise AssertionError("critical risk must not be sent to a downgradeable classifier")

    result = classify_review("У меня списали деньги, это выглядит как обман", BrokerThatMustNotBeCalled())
    assert result.risk_level == RiskLevel.CRITICAL
