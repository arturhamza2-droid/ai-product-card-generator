"""Простая веб-форма: вставили JSON — получили карточку (Markdown и JSON для копирования).

Запуск:  python -m uvicorn app.web:app --reload
"""
from __future__ import annotations

import html
from functools import lru_cache

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from .config import ConfigError, PROJECT_ROOT, load_settings
from .llm import LLMClient, LLMError, OpenAICompatibleClient
from .product import InputError, parse_product
from .render import to_json, to_markdown
from .service import generate_card

app = FastAPI(title="Черновик карточки товара")

PAGE = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Черновик карточки товара</title>
<style>
 :root {{ color-scheme: light dark; --bg:#f6f7f9; --card:#fff; --text:#1c2230; --muted:#667; --line:#d9dde5; --accent:#1b5fd1; --bad:#b3261e; }}
 @media (prefers-color-scheme: dark) {{ :root {{ --bg:#14171d; --card:#1d222b; --text:#e6e9ef; --muted:#9aa3b2; --line:#303744; --accent:#6ea2ff; --bad:#ff8a80; }} }}
 body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.5 system-ui,Segoe UI,sans-serif; }}
 main {{ max-width:900px; margin:0 auto; padding:20px 16px 60px; }}
 h1 {{ font-size:22px; }} section {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; margin:16px 0; }}
 textarea {{ width:100%; min-height:260px; box-sizing:border-box; font:13px/1.4 ui-monospace,Consolas,monospace; background:var(--bg); color:var(--text); border:1px solid var(--line); border-radius:8px; padding:10px; }}
 button {{ background:var(--accent); color:#fff; border:0; border-radius:8px; padding:9px 16px; font-size:15px; cursor:pointer; }}
 button.ghost {{ background:transparent; color:var(--accent); border:1px solid var(--accent); padding:5px 10px; font-size:13px; }}
 .err {{ color:var(--bad); font-weight:600; }} .muted {{ color:var(--muted); font-size:13px; }}
 pre {{ white-space:pre-wrap; word-wrap:break-word; background:var(--bg); border:1px solid var(--line); border-radius:8px; padding:12px; font:13px/1.45 ui-monospace,Consolas,monospace; }}
 .row {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
</style></head><body><main>
<h1>Черновик карточки товара</h1>
<p class="muted">Вставьте JSON с данными о приборе (поля name, manufacturer, specs, description). Модель пишет только тексты, характеристики копируются из ваших данных без изменений.</p>
<form method="post" action="/generate" onsubmit="this.querySelector('button').disabled=true;this.querySelector('button').textContent='Генерирую… до минуты';">
<textarea name="product_json" placeholder="{{ ... }}">{value}</textarea>
<div class="row" style="margin-top:10px"><button type="submit">Сформировать карточку</button>
<span class="muted">Один запрос к модели (при необходимости — до трёх попыток с автоисправлением).</span></div>
</form>
{result}
</main>
<script>
function copyFrom(id) {{ navigator.clipboard.writeText(document.getElementById(id).innerText); }}
</script></body></html>"""


def _example_json() -> str:
    first = sorted((PROJECT_ROOT / "examples" / "input").glob("*.json"))
    return first[0].read_text(encoding="utf-8") if first else ""


@lru_cache(maxsize=1)
def _client() -> LLMClient:
    return OpenAICompatibleClient(load_settings())


def _render(value: str, result_html: str = "") -> HTMLResponse:
    return HTMLResponse(PAGE.format(value=html.escape(value), result=result_html))


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return _render(_example_json())


@app.post("/generate", response_class=HTMLResponse)
def generate(product_json: str = Form("")) -> HTMLResponse:
    try:
        product = parse_product(product_json)
        result = generate_card(product, _client())
    except InputError as exc:
        return _render(product_json, f'<section><p class="err">Ошибка во входных данных: {html.escape(str(exc))}</p></section>')
    except ConfigError as exc:
        return _render(product_json, f'<section><p class="err">Ошибка настройки: {html.escape(str(exc))}</p></section>')
    except LLMError as exc:
        return _render(product_json, f'<section><p class="err">Ошибка модели: {html.escape(str(exc))}</p></section>')

    block = (
        '<section><div class="row"><b>Markdown</b><button class="ghost" type="button" onclick="copyFrom(\'md\')">Копировать</button></div>'
        f'<pre id="md">{html.escape(to_markdown(result))}</pre></section>'
        '<section><div class="row"><b>JSON</b><button class="ghost" type="button" onclick="copyFrom(\'js\')">Копировать</button></div>'
        f'<pre id="js">{html.escape(to_json(result))}</pre></section>'
    )
    return _render(product_json, block)
