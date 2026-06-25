"""Client for the quiz content API (https://pi.local/api)."""

from __future__ import annotations

import logging

import httpx

from .config import ApiConfig

logger = logging.getLogger(__name__)


class QuizApiError(RuntimeError):
    pass


class QuizApiClient:
    def __init__(self, config: ApiConfig) -> None:
        self._config = config
        self._client = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            verify=config.verify_tls,
            timeout=config.timeout_seconds,
        )

    def __enter__(self) -> "QuizApiClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, payload: dict) -> dict:
        resp = self._client.post(path, json=payload)
        resp.raise_for_status()
        data = resp.json()
        error_code = data.get("error_code")
        if error_code:
            raise QuizApiError(f"{path} returned error_code={error_code}")
        return data

    def get_tests(self, domain: str) -> list[dict]:
        data = self._post("/tests/get", {"domain": domain})
        return data.get("payload") or []

    def get_questions(self, domain: str, test_id: int) -> list[dict]:
        data = self._post("/questions/get", {"domain": domain, "test_id": test_id})
        return data.get("payload") or []
