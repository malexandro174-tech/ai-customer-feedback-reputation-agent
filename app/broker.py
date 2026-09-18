from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from .config import get_settings


class BrokerError(RuntimeError):
    pass


class BrokerClient:
    """Private broker client. It never accepts or stores provider credentials."""

    def __init__(self, base_url: str | None = None, requester_id: str | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.broker_url).rstrip("/")
        self.requester_id = requester_id or settings.requester_id

    def _post(self, path: str, payload: dict[str, Any], timeout: int = 40) -> dict[str, Any]:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(f"{self.base_url}{path}", data=raw, method="POST", headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read(96_000).decode("utf-8"))
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            raise BrokerError("BROKER_UNAVAILABLE_OR_REJECTED") from exc

    def request_access(self, service_id: str, capability: str) -> None:
        result = self._post("/access/request", {
            "requester_id": self.requester_id,
            "service_id": service_id,
            "capability": capability,
        })
        if result.get("result") != "GRANTED":
            raise BrokerError("DENIED_BY_POLICY")

    def complete(self, capability: str, messages: list[dict[str, str]], *, response_json: bool = False) -> dict[str, Any]:
        self.request_access("deepseek", capability)
        payload: dict[str, Any] = {"messages": messages, "temperature": 0.2, "max_tokens": 700}
        if response_json:
            payload["response_format"] = {"type": "json_object"}
        return self._post("/deepseek/complete", {
            "requester_id": self.requester_id,
            "capability": capability,
            "payload": payload,
        })

    def send_test_notification(self, text: str) -> dict[str, Any]:
        self.request_access("telegram_course_test_bot", "TEST_MESSAGE_SEND")
        result = self._post("/telegram/send", {
            "requester_id": self.requester_id,
            "capability": "TEST_MESSAGE_SEND",
            "text": text[:3500],
        })
        if result.get("status") != "PASS" or not result.get("target_registered"):
            raise BrokerError("TELEGRAM_DELIVERY_FAILED")
        return result
