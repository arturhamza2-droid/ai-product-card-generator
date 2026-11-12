"""Автоматическая проверка ответа модели (делает код, а не модель)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .product import Product

TITLE_MAX = 70
DESC_MIN, DESC_MAX = 800, 1200
QUERIES_MIN, QUERIES_MAX = 3, 5

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

# Слова, которые нельзя употреблять, если их нет во входных данных: это утверждения о сертификатах,
# стандартах, гарантиях, торговых условиях и неподтверждённые оценки. Ищем по началу слова.
RISKY_STEMS = [
    "взрывозащ", "искробезопас", "сертифи", "декларац", "гост", "реестр", "ростехнадзор",
    "гарант", "доставк", "в наличии", "со склада", "скидк", "бесплатн", "оригинальн", "официальн",
    "лучш", "самый", "самая", "самое", "самые", "уникальн", "надежн", "высокоточн", "инновацион",
    "идеальн", "премиум", "лидер", "качественн", "безупречн", "передов",
]


@dataclass
class CardText:
    """Тексты, сгенерированные моделью, в проверенной структуре."""

    seo_title: str
    seo_description: str
    search_queries: list[str]
    suitable_for: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    data_issues: list[str] = field(default_factory=list)
    # значения характеристик, найденные моделью в описании (с цитатой; проверяются кодом)
    extracted: list[dict] = field(default_factory=list)

    def all_text(self) -> str:
        parts = [self.seo_title, self.seo_description, *self.search_queries,
                 *self.suitable_for, *self.tasks, *self.caveats]
        return "\n".join(parts)


def _str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise ValueError("ожидался список строк")
    return [str(v).strip() for v in value if str(v).strip()]


def parse_card(data: dict) -> CardText:
    """Приводит JSON модели к CardText; при неверной структуре бросает ValueError."""
    for key in ("seo_title", "seo_description", "search_queries"):
        if key not in data:
            raise ValueError(f"в ответе нет поля «{key}»")
    commercial = data.get("commercial") or {}
    if not isinstance(commercial, dict):
        raise ValueError("поле «commercial» должно быть объектом")
    return CardText(
        seo_title=str(data["seo_title"]).strip(),
        seo_description=str(data["seo_description"]).strip(),
        search_queries=_str_list(data["search_queries"]),
        suitable_for=_str_list(commercial.get("suitable_for")),
        tasks=_str_list(commercial.get("tasks")),
        caveats=_str_list(commercial.get("caveats")),
        data_issues=_str_list(data.get("data_issues")),
        extracted=[x for x in (data.get("spec_from_description") or []) if isinstance(x, dict)],
    )


def numbers_in(text: str) -> set[str]:
    return {m.replace(",", ".") for m in _NUMBER.findall(text)}


def source_corpus(product: Product) -> str:
    specs = "\n".join(f"{k} {v}" for k, v in product.specs.items())
    return "\n".join([product.name, product.manufacturer, specs, product.description])


def find_unknown_numbers(card: CardText, product: Product) -> list[str]:
    """Числа из текста карточки, которых нет во входных данных (возможная выдумка)."""
    known = numbers_in(source_corpus(product))
    unknown = sorted(numbers_in(card.all_text()) - known, key=lambda s: (len(s), s))
    return unknown


# Фразы о нехватке данных: им место в «Что проверить», а не в публичном тексте карточки.
META_PHRASES = ["не указан", "не приведен", "не приведён", "отсутству", "в данных", "в карточке",
                "уточните у менеджера", "данных нет", "нет информации", "информация не"]


def find_meta_phrases(card: CardText) -> list[str]:
    public = _norm("\n".join([card.seo_title, card.seo_description, *card.search_queries]))
    return [p for p in META_PHRASES if _norm(p) in public]


_LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{2,}")


def find_foreign_words(card: CardText, product: Product) -> list[str]:
    """Английские слова в тексте карточки, которых нет во входных данных."""
    source = _norm(source_corpus(product))
    words = {w for w in _LATIN_WORD.findall(card.all_text()) if _norm(w) not in source}
    return sorted(words)


def _norm(text: str) -> str:
    return text.lower().replace("ё", "е")


def find_unsupported_terms(card: CardText, product: Product) -> list[str]:
    """Рискованные слова из текста карточки, которых нет во входных данных."""
    text, source = _norm(card.all_text()), _norm(source_corpus(product))
    found = []
    for stem in RISKY_STEMS:
        stem_n = _norm(stem)
        if re.search(r"(?<!\w)" + re.escape(stem_n), text) and stem_n not in source:
            found.append(stem)
    return found


def validate_card(card: CardText, product: Product) -> list[str]:
    """Возвращает список нарушений (пустой — карточка прошла все проверки)."""
    problems: list[str] = []
    if not card.seo_title:
        problems.append("seo_title пустой")
    elif len(card.seo_title) > TITLE_MAX:
        problems.append(
            f"seo_title длиной {len(card.seo_title)} символов, нужно не более {TITLE_MAX}"
        )
    n = len(card.seo_description)
    if not DESC_MIN <= n <= DESC_MAX:
        problems.append(f"seo_description длиной {n} символов, нужно от {DESC_MIN} до {DESC_MAX}")
    q = len(card.search_queries)
    if not QUERIES_MIN <= q <= QUERIES_MAX:
        problems.append(f"search_queries содержит {q} запросов, нужно от {QUERIES_MIN} до {QUERIES_MAX}")
    elif len({s.lower() for s in card.search_queries}) != q:
        problems.append("search_queries содержит повторы")
    unknown = find_unknown_numbers(card, product)
    if unknown:
        problems.append(
            "в тексте есть числа, которых нет во входных данных: " + ", ".join(unknown)
            + ". Убери их или замени формулировкой без чисел"
        )
    foreign = find_foreign_words(card, product)
    if foreign:
        problems.append(
            "в тексте есть латиница, которой нет во входных данных: " + ", ".join(foreign)
            + ". Замени русскими словами"
        )
    meta = find_meta_phrases(card)
    if meta:
        problems.append(
            "в публичном тексте (заголовок, описание, запросы) есть фразы о нехватке данных ("
            + ", ".join(meta) + "). Такие замечания пиши только в data_issues"
        )
    terms = find_unsupported_terms(card, product)
    if terms:
        problems.append(
            "в тексте есть утверждения, которых нет во входных данных (слова на: "
            + ", ".join(terms) + "). Убери эти слова или замени фактами из данных"
        )
    return problems
