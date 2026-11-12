"""Тесты без обращения к реальному API: модель подменена заглушкой."""
import json

import pytest

from app.checks import CardText, find_unknown_numbers, validate_card
from app.llm import LLMError, extract_json
from app.product import InputError, parse_product
from app.render import to_markdown
from app.service import generate_card
from app.specs import build_key_specs

PRODUCT = {
    "name": "Манометр DM 02",
    "manufacturer": "Манотомь",
    "specs": {"Диапазон измерений": "0–1,6 МПа", "Класс точности": "1,5", "Присоединение": "G1/2"},
    "description": "Прибор предназначен для измерения избыточного давления.",
}


def good_answer(**override) -> dict:
    data = {
        "seo_title": "Манометр DM 02 Манотомь: показывающий, 0–1,6 МПа",
        "seo_description": ("Манометр DM 02 предназначен для измерения избыточного давления. " * 15).strip(),
        "search_queries": ["манометр dm 02", "манометр 1,6 МПа", "купить манометр манотомь"],
        "commercial": {"suitable_for": ["Службы КИПиА"], "tasks": ["Контроль давления"], "caveats": []},
        "data_issues": [],
    }
    data.update(override)
    return data


class FakeClient:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        answer = self.answers.pop(0)
        return answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)


# ---- вход -----------------------------------------------------------------

def test_broken_json_gives_clear_error():
    with pytest.raises(InputError, match="Некорректный JSON"):
        parse_product("{not json")


def test_empty_input_and_missing_name():
    with pytest.raises(InputError):
        parse_product("  ")
    with pytest.raises(InputError, match="name"):
        parse_product({"specs": {"a": "b"}})


def test_empty_values_are_reported_not_invented():
    product = parse_product({"name": "X", "specs": {"Питание": "", "IP": "IP65"}, "description": ""})
    assert product.specs == {"IP": "IP65"}
    assert "specs.Питание" in product.empty_fields and "description" in product.empty_fields


# ---- ключевые характеристики ------------------------------------------------

def test_key_specs_copied_verbatim_and_missing_marked():
    groups, rest = build_key_specs(parse_product(PRODUCT).specs)
    by_label = {g.label: g for g in groups}
    assert by_label["Диапазон измерений"].items == [("Диапазон измерений", "0–1,6 МПа")]
    assert by_label["Питание"].missing  # в данных питания нет -> «данных нет»
    assert not rest or all(k != "Диапазон измерений" for k, _ in rest)


# ---- проверки ответа --------------------------------------------------------

def test_unknown_numbers_detected():
    product = parse_product(PRODUCT)
    card = CardText("Манометр", "Класс точности 0,5 и диапазон 0–1,6 МПа", ["a", "b", "c"])
    assert find_unknown_numbers(card, product) == ["0.5"]


def test_length_limits():
    product = parse_product(PRODUCT)
    card = CardText("я" * 71, "коротко", ["а"])
    problems = validate_card(card, product)
    assert len(problems) == 3


# ---- сценарий ---------------------------------------------------------------

def test_happy_path():
    result = generate_card(parse_product(PRODUCT), FakeClient(good_answer()))
    assert result.status == "ok" and result.attempts == 1
    assert "данных нет" in to_markdown(result)


def test_retry_fixes_hallucinated_number():
    bad = good_answer(search_queries=["манометр 2,5 МПа", "манометр dm 02", "купить манометр"])
    client = FakeClient(bad, good_answer())
    result = generate_card(parse_product(PRODUCT), client)
    assert result.status == "ok" and client.calls == 2


def test_still_bad_after_retries_marked_for_review():
    bad = good_answer(search_queries=["манометр 2,5 МПа", "манометр dm 02", "купить манометр"])
    result = generate_card(parse_product(PRODUCT), FakeClient(bad, bad, bad))
    assert result.status == "needs_review" and result.problems


def test_garbage_answer_raises_llm_error():
    with pytest.raises(LLMError):
        generate_card(parse_product(PRODUCT), FakeClient("не json", "не json", "не json"))


def test_too_little_data_skips_model():
    client = FakeClient()
    result = generate_card(parse_product({"name": "Прибор"}), client)
    assert result.status == "insufficient_data" and client.calls == 0


def test_extract_json_handles_fences():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Вот ответ: {"a": 1} спасибо') == {"a": 1}


# ---- «опасные» слова ---------------------------------------------------------

def test_unsupported_claims_detected():
    from app.checks import find_unsupported_terms

    product = parse_product(PRODUCT)
    card = CardText("Манометр", "Сертифицированный прибор. Самый точный, с гарантией.", ["a", "b", "c"])
    assert set(find_unsupported_terms(card, product)) >= {"сертифи", "самый", "гарант"}


def test_claim_allowed_if_present_in_source():
    from app.checks import find_unsupported_terms

    data = dict(PRODUCT, description="Прибор внесён в реестр средств измерений.")
    card = CardText("Манометр", "Прибор внесён в реестр средств измерений.", ["a", "b", "c"])
    assert find_unsupported_terms(card, parse_product(data)) == []


def _product_with_range_in_description():
    return parse_product({
        "name": "Датчик Д-1",
        "specs": {"Напряжение питания": "24 В"},
        "description": "Прибор предназначен для измерения давления. Диапазон измерения: 0…0,6 МПа. Корпус полевой.",
    })


def _answer_for_d1(**extra):
    return good_answer(
        seo_title="Датчик Д-1 для измерения давления",
        seo_description=("Датчик Д-1 предназначен для измерения давления. " * 20).strip(),
        search_queries=["датчик д-1", "купить датчик д-1", "датчик давления"],
        **extra,
    )


def test_value_from_description_accepted_with_real_quote():
    answer = _answer_for_d1(spec_from_description=[{
        "group": "Диапазон измерений", "name": "Диапазон измерения", "value": "0…0,6 МПа",
        "quote": "Диапазон измерения: 0…0,6 МПа.",
    }])
    result = generate_card(_product_with_range_in_description(), FakeClient(answer))
    md = to_markdown(result)
    assert "0…0,6 МПа" in md and "(из описания)" in md
    assert not any("Диапазон измерений" in m for m in result.missing)


def test_value_from_description_rejected_with_fake_quote_or_value():
    fake_quote = {"group": "Диапазон измерений", "name": "Диапазон", "value": "0…1 МПа", "quote": "Диапазон 0…1 МПа"}
    wrong_value = {"group": "Диапазон измерений", "name": "Диапазон", "value": "0…1,6 МПа",
                   "quote": "Диапазон измерения: 0…0,6 МПа."}
    for bad in (fake_quote, wrong_value):
        result = generate_card(_product_with_range_in_description(),
                               FakeClient(_answer_for_d1(spec_from_description=[bad])))
        assert "(из описания)" not in to_markdown(result)
        assert any("Диапазон измерений" in m for m in result.missing)


def test_meta_phrases_in_public_text_flagged():
    from app.checks import find_meta_phrases

    card = CardText("Манометр", "Производитель не указан, поэтому уточните у менеджера.", ["a", "b", "c"])
    assert "не указан" in find_meta_phrases(card)


def test_english_words_flagged_but_model_names_allowed():
    from app.checks import find_foreign_words

    product = parse_product(dict(PRODUCT, specs={"Интерфейс": "RS-485"}))
    card = CardText("Манометр DM 02", "Для integrators, интерфейс RS-485.", ["a", "b", "c"])
    assert find_foreign_words(card, product) == ["integrators"]


def test_user_message_lists_empty_groups():
    from app.prompts import build_user_message

    text = build_user_message(parse_product(PRODUCT), ["Питание", "Масса"])
    assert "Питание; Масса" in text
