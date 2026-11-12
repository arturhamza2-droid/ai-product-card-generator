"""Разбор и проверка входных данных о товаре."""
from __future__ import annotations

import json
from dataclasses import dataclass, field


class InputError(Exception):
    """Входные данные некорректны (понятное сообщение для пользователя)."""


@dataclass
class Product:
    name: str
    manufacturer: str = ""
    specs: dict[str, str] = field(default_factory=dict)
    description: str = ""
    # Что в исходных данных было пустым: пойдёт в отчёт «что уточнить»
    empty_fields: list[str] = field(default_factory=list)

    def to_prompt_dict(self) -> dict:
        return {
            "name": self.name,
            "manufacturer": self.manufacturer or "данных нет",
            "specs": self.specs or "данных нет",
            "description": self.description or "данных нет",
        }


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(_as_text(v) for v in value if _as_text(v))
    return str(value).strip()


def parse_product(raw: str | dict) -> Product:
    """Принимает JSON-строку или словарь, возвращает проверенный Product."""
    if isinstance(raw, str):
        if not raw.strip():
            raise InputError("Пустой ввод: передайте JSON с данными о товаре.")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise InputError(
                f"Некорректный JSON (строка {exc.lineno}, символ {exc.colno}): {exc.msg}."
            ) from exc
    else:
        data = raw

    if not isinstance(data, dict):
        raise InputError("JSON должен быть объектом {...} с полями name, manufacturer, specs, description.")

    name = _as_text(data.get("name"))
    if not name:
        raise InputError("Не заполнено обязательное поле «name» (название товара).")

    raw_specs = data.get("specs")
    if raw_specs is None:
        raw_specs = {}
    if not isinstance(raw_specs, dict):
        raise InputError("Поле «specs» должно быть объектом вида {\"параметр\": \"значение\"}.")

    specs: dict[str, str] = {}
    empty: list[str] = []
    for key, value in raw_specs.items():
        key_text, value_text = _as_text(key), _as_text(value)
        if not key_text:
            continue
        if not value_text:
            empty.append(f"specs.{key_text}")  # параметр есть, а значения нет
            continue
        specs[key_text] = value_text

    manufacturer = _as_text(data.get("manufacturer"))
    description = _as_text(data.get("description"))
    if not manufacturer:
        empty.append("manufacturer")
    if not description:
        empty.append("description")
    if not specs:
        empty.append("specs")

    return Product(name=name, manufacturer=manufacturer, specs=specs, description=description, empty_fields=empty)
