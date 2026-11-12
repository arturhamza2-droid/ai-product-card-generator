"""Главный сценарий: проверка данных → вызов модели → проверка ответа → результат."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .checks import CardText, parse_card, validate_card
from .llm import LLMClient, LLMError, extract_json
from .product import Product
from .prompts import SYSTEM_PROMPT, build_retry_message, build_user_message
from .specs import KeySpecGroup, build_key_specs

MIN_DESCRIPTION_FOR_NO_SPECS = 100


@dataclass
class CardResult:
    status: str  # "ok" | "needs_review" | "insufficient_data"
    product: Product
    key_groups: list[KeySpecGroup] = field(default_factory=list)
    other_specs: list[tuple[str, str]] = field(default_factory=list)
    card: CardText | None = None
    missing: list[str] = field(default_factory=list)  # чего не хватает во входных данных
    problems: list[str] = field(default_factory=list)  # что не прошло автопроверку
    attempts: int = 0


def _missing_report(product: Product, groups: list[KeySpecGroup]) -> list[str]:
    missing: list[str] = []
    labels = {"manufacturer": "производитель (manufacturer)", "description": "описание (description)",
              "specs": "характеристики (specs)"}
    for item in product.empty_fields:
        if item.startswith("specs."):
            missing.append(f"у характеристики «{item[6:]}» нет значения")
        else:
            missing.append(f"не заполнено: {labels.get(item, item)}")
    for group in groups:
        if group.required and group.missing:
            missing.append(f"нет данных: {group.label}")
    return missing


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()


def apply_description_specs(product: Product, groups: list[KeySpecGroup], extracted: list[dict]) -> int:
    """Добавляет в пустые группы значения из описания, ТОЛЬКО если цитата есть в описании
    и значение есть в цитате. Возвращает число принятых значений."""
    description = _squash(product.description)
    by_label = {g.label: g for g in groups}
    accepted = 0
    for item in extracted:
        group = by_label.get(str(item.get("group", "")).strip())
        name, value, quote = (str(item.get(k, "")).strip() for k in ("name", "value", "quote"))
        if not group or not group.missing or not (name and value and quote):
            continue
        q = _squash(quote)
        if q not in description or _squash(value) not in q:
            continue  # цитаты нет в описании или значения нет в цитате: отбрасываем
        group.items.append((f"{name} (из описания)", value))
        accepted += 1
    return accepted


def generate_card(product: Product, client: LLMClient, max_attempts: int = 3) -> CardResult:
    groups, other = build_key_specs(product.specs)
    result = CardResult(status="ok", product=product, key_groups=groups, other_specs=other,
                        missing=_missing_report(product, groups))

    # Данных слишком мало: модель не вызываем, чтобы она ничего не «досочиняла».
    if not product.specs and len(product.description) < MIN_DESCRIPTION_FOR_NO_SPECS:
        result.status = "insufficient_data"
        result.missing.insert(0, "данных недостаточно для карточки: нет характеристик и нет содержательного описания")
        return result

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(product, [g.label for g in groups if g.missing])},
    ]
    best: CardText | None = None
    problems: list[str] = []
    for attempt in range(1, max_attempts + 1):
        result.attempts = attempt
        raw = client.complete(messages)
        try:
            card = parse_card(extract_json(raw))
        except ValueError as exc:
            problems = [f"ответ не удалось разобрать: {exc}"]
        else:
            best = card
            problems = validate_card(card, product)
            if not problems:
                break
        messages += [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": build_retry_message(raw, problems)},
        ]

    if best is None:
        raise LLMError("Модель не вернула ответ в нужном формате: " + "; ".join(problems))
    result.card = best
    apply_description_specs(product, groups, best.extracted)
    result.missing = _missing_report(product, groups)  # пересчёт: часть групп закрыта описанием
    result.problems = problems
    result.status = "needs_review" if problems else "ok"
    return result
