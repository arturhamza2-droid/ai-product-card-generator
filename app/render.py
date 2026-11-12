"""Вывод результата: Markdown (для копирования в CMS) и JSON."""
from __future__ import annotations

import json

from .service import CardResult
from .specs import NO_DATA

STATUS_TEXT = {
    "ok": "Готово: автопроверки пройдены. Перед публикацией текст всё равно должен прочитать человек.",
    "needs_review": "Требует ручной правки: часть автопроверок не пройдена (см. раздел «Что проверить»).",
    "insufficient_data": "Карточка не сформирована: данных недостаточно.",
}


def _esc(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_dict(result: CardResult) -> dict:
    card = result.card
    return {
        "status": result.status,
        "status_text": STATUS_TEXT[result.status],
        "product": {"name": result.product.name, "manufacturer": result.product.manufacturer or NO_DATA},
        "seo_title": card.seo_title if card else None,
        "seo_title_length": len(card.seo_title) if card else None,
        "seo_description": card.seo_description if card else None,
        "seo_description_length": len(card.seo_description) if card else None,
        "key_specs": [
            {
                "group": g.label,
                "values": [{"name": k, "value": v} for k, v in g.items] or NO_DATA,
            }
            for g in result.key_groups
        ],
        "other_specs": [{"name": k, "value": v} for k, v in result.other_specs],
        "search_queries": card.search_queries if card else [],
        "manager_block": {
            "suitable_for": card.suitable_for if card else [],
            "tasks": card.tasks if card else [],
            "caveats": card.caveats if card else [],
        },
        "to_check": {
            "missing_input_data": result.missing,
            "data_issues_from_model": card.data_issues if card else [],
            "failed_auto_checks": result.problems,
        },
        "generation_attempts": result.attempts,
    }


def to_json(result: CardResult) -> str:
    return json.dumps(to_dict(result), ensure_ascii=False, indent=2)


def to_markdown(result: CardResult) -> str:
    d = to_dict(result)
    out = [f"# {d['product']['name']}", "", f"_Производитель: {d['product']['manufacturer']}_", "",
           f"**Статус:** {d['status_text']}", ""]
    card = result.card
    if card:
        out += [f"## SEO-заголовок ({d['seo_title_length']} симв., лимит 70)", "", card.seo_title, "",
                f"## SEO-описание ({d['seo_description_length']} симв., норма 800–1200)", "",
                card.seo_description, ""]
    out += ["## Ключевые характеристики", "", "| Параметр | Значение (дословно из источника) |", "|---|---|"]
    for g in result.key_groups:
        if g.missing:
            out.append(f"| **{g.label}** | {NO_DATA} |")
        for name, value in g.items:
            shown = _esc(name) if name.lower() == g.label.lower() else f"{g.label}: {_esc(name)}"
            out.append(f"| **{shown}** | {_esc(value)} |")
    if result.other_specs:
        out += ["", "### Остальные характеристики из источника", "", "| Параметр | Значение |", "|---|---|"]
        out += [f"| {_esc(k)} | {_esc(v)} |" for k, v in result.other_specs]
    if card:
        out += ["", "## Поисковые запросы", ""] + [f"{i}. {q}" for i, q in enumerate(card.search_queries, 1)]
        out += ["", "## Блок для менеджера", ""]
        for title, items in (("Кому подходит", card.suitable_for), ("Какие задачи решает", card.tasks),
                             ("На что обратить внимание", card.caveats)):
            if items:
                out += [f"**{title}:**"] + [f"- {x}" for x in items] + [""]
    checks = d["to_check"]
    out += ["## Что проверить перед публикацией", ""]
    any_item = False
    for title, items in (("Не хватает во входных данных", checks["missing_input_data"]),
                         ("Замечания модели к данным", checks["data_issues_from_model"]),
                         ("Не пройдены автопроверки", checks["failed_auto_checks"])):
        if items:
            any_item = True
            out += [f"**{title}:**"] + [f"- {x}" for x in items] + [""]
    if not any_item:
        out += ["Замечаний нет.", ""]
    return "\n".join(out).rstrip() + "\n"
