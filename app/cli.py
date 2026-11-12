"""Командная строка.

Примеры:
    python -m app.cli examples/input/pd100-di0-6-115-0-5.json
    python -m app.cli examples/input/*.json -o examples/output
    cat product.json | python -m app.cli -
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import sys
from pathlib import Path

from .config import ConfigError, load_settings
from .llm import LLMError, OpenAICompatibleClient
from .product import InputError, parse_product
from .render import to_json, to_markdown
from .service import generate_card


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Черновик карточки товара по JSON с данными о приборе")
    parser.add_argument("inputs", nargs="+", help="JSON-файлы с товарами или «-» для чтения из stdin")
    parser.add_argument("-o", "--out-dir", help="папка для результатов (.md и .json рядом)")
    parser.add_argument("--format", choices=["md", "json", "both"], default="md",
                        help="что печатать на экран (по умолчанию md)")
    parser.add_argument("--model", help="переопределить модель из .env (для сравнения моделей)")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        settings = load_settings()
        if args.model:
            settings = replace(settings, model=args.model)
        client = OpenAICompatibleClient(settings)
    except ConfigError as exc:
        print(f"Ошибка настройки: {exc}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    for source in args.inputs:
        label = "stdin" if source == "-" else source
        try:
            raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
        except OSError as exc:
            print(f"[{label}] не удалось прочитать файл: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        try:
            product = parse_product(raw)
            result = generate_card(product, client)
        except InputError as exc:
            print(f"[{label}] ошибка во входных данных: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        except LLMError as exc:
            print(f"[{label}] ошибка модели: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        markdown, as_json = to_markdown(result), to_json(result)
        if out_dir:
            stem = "stdin" if source == "-" else Path(source).stem
            (out_dir / f"{stem}.md").write_text(markdown, encoding="utf-8")
            (out_dir / f"{stem}.json").write_text(as_json + "\n", encoding="utf-8")
            print(f"[{label}] статус: {result.status}; сохранено в {out_dir / stem}.md / .json", file=sys.stderr)
        if args.format in ("md", "both"):
            print(markdown)
        if args.format in ("json", "both"):
            print(as_json)
        if result.status != "ok":
            exit_code = max(exit_code, 3)  # 3 = результат есть, но требует ручной проверки
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
