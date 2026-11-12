"""Тонкая обёртка над LLM API (OpenAI-совместимый протокол, в том числе через «туннели»).

Весь код сервиса зависит только от метода `complete()`, поэтому провайдера
можно сменить, переписав один этот файл.
"""
from __future__ import annotations

import json
import re
import time
from typing import Protocol

import openai

from .config import Settings


class LLMError(Exception):
    """Ошибка обращения к модели (текст понятен пользователю)."""


class LLMClient(Protocol):
    def complete(self, messages: list[dict]) -> str: ...


class OpenAICompatibleClient:
    def __init__(self, settings: Settings, max_retries: int = 3):
        self._settings = settings
        self._max_retries = max_retries
        self._client = openai.OpenAI(
            base_url=settings.base_url,
            api_key=settings.api_key,
            timeout=settings.timeout,
            max_retries=0,  # повторы делаем сами, чтобы выдавать понятные сообщения
        )

    def complete(self, messages: list[dict]) -> str:
        # Сначала просим строгий JSON и низкую температуру; если провайдер/модель
        # не поддерживает эти параметры — повторяем запрос без них.
        param_sets = [
            {"temperature": 0.2, "response_format": {"type": "json_object"}},
            {},
        ]
        last_bad_request: Exception | None = None
        for params in param_sets:
            try:
                return self._request(messages, params)
            except openai.BadRequestError as exc:
                last_bad_request = exc
                continue
        raise LLMError(f"Модель отклонила запрос: {_short(last_bad_request)}")

    def _request(self, messages: list[dict], params: dict) -> str:
        delay = 2.0
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._settings.model, messages=messages, **params
                )
            except openai.AuthenticationError as exc:
                raise LLMError("API отклонил ключ (401). Проверьте LLM_API_KEY в файле .env.") from exc
            except openai.PermissionDeniedError as exc:
                raise LLMError(f"Нет доступа к модели «{self._settings.model}» (403): {_short(exc)}") from exc
            except openai.NotFoundError as exc:
                raise LLMError(
                    f"Модель «{self._settings.model}» или адрес API не найдены (404). "
                    "Проверьте LLM_MODEL и LLM_BASE_URL."
                ) from exc
            except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError,
                    openai.InternalServerError) as exc:
                if attempt == self._max_retries:
                    raise LLMError(
                        f"API недоступен или перегружен ({type(exc).__name__}: {_root_cause(exc)}). "
                        "Проверьте интернет/VPN и адрес LLM_BASE_URL, затем повторите."
                    ) from exc
                time.sleep(delay)
                delay *= 2
                continue
            except openai.BadRequestError:
                raise
            except openai.APIError as exc:
                raise LLMError(f"Ошибка API: {_short(exc)}") from exc

            if not response.choices:
                raise LLMError("API вернул пустой ответ.")
            text = response.choices[0].message.content or ""
            if not text.strip():
                raise LLMError("Модель вернула пустой текст.")
            return text
        raise LLMError("Не удалось получить ответ от модели.")  # недостижимо, для полноты


def _root_cause(exc: BaseException) -> str:
    """Самая глубокая причина сетевой ошибки (без адресов с ключами)."""
    while exc.__cause__ is not None:
        exc = exc.__cause__
    return f"{type(exc).__name__}: {str(exc)[:150]}"


def _short(exc: Exception | None, limit: int = 300) -> str:
    return str(exc)[:limit] if exc else "неизвестная ошибка"


def extract_json(text: str) -> dict:
    """Достаёт JSON-объект из ответа модели (допускает ```json-ограждения и лишний текст)."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("в ответе нет JSON-объекта") from None
        try:
            data = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"ответ не является корректным JSON ({exc.msg})") from exc
    if not isinstance(data, dict):
        raise ValueError("ответ должен быть JSON-объектом")
    return data
