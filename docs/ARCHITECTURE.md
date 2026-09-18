# Архитектура сервиса

`review-site` предоставляет публичный sandbox и операторскую сводку. `feedback-worker` выполняет отдельный polling-цикл. `review-db` хранит reviews, processing events, notifications, processing runs и approvals в persistent volume. Все внешние вызовы проходят через private Docker network к Access & Integration Broker.

Новые источники отзывов реализуют `ReviewSourceAdapter`. Они не могут обходить policy layer, напрямую читать credential или отправлять уведомления вне Broker.

## Контракты управления

Сервис формирует `UpwardReport`, `KpiSnapshot`, `IncidentSummary`, `EscalationRequest` и `ReputationSummary`. Это локальные типизированные данные: подключения к внешней управляющей системе в данной версии нет.
