# AI Customer Feedback & Reputation Agent

AI-система для мониторинга клиентских отзывов, анализа тональности, подготовки ответов и эскалации сложных обращений. Сервис принимает отзывы через безопасный sandbox-источник, классифицирует их с помощью правил и DeepSeek через Credential/Access Broker, сохраняет операционное состояние в PostgreSQL и отправляет TEST-уведомления только в зарегистрированный target.

## Возможности

- Контракт `ReviewSourceAdapter` и первый адаптер `SandboxReviewSource`.
- Тональность: `POSITIVE`, `NEGATIVE`, `NEUTRAL`, `MIXED`, `UNKNOWN`.
- Риск: `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.
- Политики ответа: `AUTO_SAFE`, `APPROVAL_REQUIRED`, `BLOCKED`.
- Устойчивая очередь с состояниями, попытками, событиями, backoff и идемпотентными уведомлениями.
- Операторская сводка и типизированные контракты для руководителя.
- Изолированные `review-site`, `feedback-worker` и PostgreSQL; доступ к DeepSeek и Telegram только через Broker.

## Поток обработки

1. `SandboxReviewSource` сохраняет отзыв в PostgreSQL как `NEW`.
2. Worker атомарно резервирует запись и применяет rule-prefilter.
3. Для неоднозначных текстов он вызывает DeepSeek с разрешением `CLASSIFICATION`.
4. Генератор ответа использует `CHAT_COMPLETION`; безопасные ответы публикуются, остальные ждут оператора или блокируются.
5. Негативные и рискованные случаи получают одно TEST-уведомление через фиксированный allowlist Broker.

## Локальный запуск

Создайте серверный файл `runtime-secrets/feedback_db_password` с правами доступа только для владельца, затем:

```bash
cp .env.example .env
docker compose up --build
```

Сервис откроется по `http://localhost:8000/`; для production используется reverse proxy prefix `/reputation/` и loopback-only порт контейнера.

## Безопасность

- В репозитории нет provider key, Telegram token, пароля PostgreSQL или connection string.
- Broker хранит и использует credential server-side; приложение передаёт только минимальные task payload.
- Telegram message delivery доступен лишь с `TEST_MESSAGE_SEND` и только зарегистрированному TEST target.
- В журнал событий попадают безопасные метаданные, correlation ID и статусы, но не секреты.

## Проверки

```bash
python -m pytest -q
docker compose config
```

Перед публикацией выполняются unit/integration smoke tests, Broker regression и secret scan.
