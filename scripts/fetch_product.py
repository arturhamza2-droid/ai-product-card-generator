"""Вспомогательный скрипт: собирает входной JSON товара со страницы souz-pribor.ru.

Использование:
    python scripts/fetch_product.py https://www.souz-pribor.ru/product/trm501/ -o examples/input/trm501.json

Фид (feed.xml) содержит только название, бренд, артикул и цену, поэтому
характеристики и описание берутся со страницы товара (ссылка есть в фиде).
Скрипт делает ОДИН запрос на страницу и ничего не придумывает: что есть на
странице, то и попадёт в JSON.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (test-task prototype)"


def fetch(url: str, timeout: int = 40) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(3):  # сайт иногда отвечает с задержкой: пробуем до 3 раз
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except OSError as exc:
            last_error = exc
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Не удалось загрузить {url}: {last_error}")


def _clean(fragment: str) -> str:
    fragment = re.sub(r"(?s)<(script|style).*?</\1>", "", fragment)
    fragment = re.sub(r"(?i)<br\s*/?>|</(p|li|div|h\d|tr)>", "\n", fragment)
    fragment = re.sub(r"<[^>]+>", " ", fragment)
    fragment = html.unescape(fragment).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in fragment.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _block(page: str, block_id: str) -> str:
    """Возвращает HTML блока с данным id (до следующего блока вкладок)."""
    start = page.find(f'id="{block_id}"')
    if start < 0:
        return ""
    end = len(page)
    for nxt in ("specifications", "description", "documents", "reviews", "equipment"):
        if nxt == block_id:
            continue
        pos = page.find(f'id="{nxt}"', start + 10)
        if pos > 0:
            end = min(end, pos)
    return page[start:end]


def _common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a.lower(), b.lower()):
        if x != y:
            break
        n += 1
    return n


def parse_specs(page: str) -> dict[str, str]:
    block = _block(page, "specifications")
    specs: dict[str, str] = {}
    for row in re.findall(r"(?s)<tr.*?</tr>", block):
        cells = re.findall(r"(?s)<td[^>]*>(.*?)</td>", row)
        texts = [_clean(c).replace("\n", " ").strip() for c in cells]
        if len(texts) < 2:
            continue  # строка-заголовок раздела: пропускаем, чтобы не искажать смысл
        key = texts[0]
        value = " | ".join(t for t in texts[1:] if t)  # многоколоночные строки не теряем
        if not key or not value:
            continue
        if (key.lower(), value.lower()) == ("наименование", "значение"):
            continue  # шапка таблицы
        if _common_prefix(key, value) >= 12 or re.search(r"Х\d+Х", key + value):
            continue  # строки-подписи к чертежам (не характеристики)
        if key[:1].islower() and specs:
            # продолжение названия предыдущей строки, перенесённое на новую строку таблицы
            prev = list(specs)[-1]
            specs[f"{prev} {key}"] = f"{specs.pop(prev)}; {value}"
            continue
        specs[key] = value
    return specs


def parse_description(page: str) -> str:
    block = _block(page, "description")
    block = block[block.find(">") + 1:]  # отрезаем хвост открывающего тега блока
    lines = _clean(block).split("\n")
    cut = [i for i, ln in enumerate(lines) if ln.lower() in ("показать все", "скрыть")]
    if cut:
        lines = lines[: cut[0]]
    if lines and lines[0].lower().startswith("описание"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def parse_product(url: str, manufacturer: str = "") -> dict:
    page = fetch(url)
    h1 = re.search(r"(?s)<h1[^>]*>(.*?)</h1>", page)
    name = _clean(h1.group(1)) if h1 else ""
    return {
        "name": name,
        "manufacturer": manufacturer,
        "specs": parse_specs(page),
        "description": parse_description(page),
        "source_url": url,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("url")
    ap.add_argument("-o", "--output", help="куда сохранить JSON (по умолчанию печать на экран)")
    ap.add_argument("--manufacturer", default="", help="производитель (из фида, поле vendor)")
    args = ap.parse_args()

    data = parse_product(args.url, args.manufacturer)
    out = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out + "\n", encoding="utf-8")
        print(f"Сохранено: {args.output} (характеристик: {len(data['specs'])})")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
