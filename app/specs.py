"""Ключевые характеристики собирает КОД, а не модель.

Значения копируются из входных данных дословно, поэтому выдумать их невозможно.
Если для группы ничего не нашлось, пишем «данных нет».
"""
from __future__ import annotations

import re
from dataclasses import dataclass

NO_DATA = "данных нет"

# (название группы, регулярное выражение по НАЗВАНИЮ характеристики, важна ли группа)
KEY_SLOTS: list[tuple[str, str, bool]] = [
    ("Диапазон измерений", r"диапазон\s+(измер|преобраз)|предел\w*\s+измер|верхн\w+\s+предел", True),
    ("Точность", r"погрешност|класс\s+точност|класс\s+допуск", True),
    ("Питание", r"напряжени\w+\s+питани|питани|потребляем", True),
    ("Выходной сигнал / интерфейс", r"выходной\s+сигнал|интерфейс|rs-?485|modbus|выход", True),
    ("Степень защиты", r"степень\s+защиты|\bip\s?\d", True),
    ("Корпус, размеры, присоединение", r"габарит|корпус|размер|штуцер|присоедин|резьб|электрическ\w+\s+соедин", True),
    ("Условия эксплуатации", r"температур|влажност|атмосферн|климат", False),
    ("Ресурс и поверка", r"срок\s+службы|наработк|межповерочн", False),
    ("Масса", r"\bмасса\b|\bвес\b", False),
]


@dataclass
class KeySpecGroup:
    label: str
    items: list[tuple[str, str]]  # (название из источника, значение из источника)
    required: bool

    @property
    def missing(self) -> bool:
        return not self.items


def build_key_specs(specs: dict[str, str]) -> tuple[list[KeySpecGroup], list[tuple[str, str]]]:
    """Возвращает (группы ключевых характеристик, остальные характеристики)."""
    used: set[str] = set()
    groups: list[KeySpecGroup] = []
    for label, pattern, required in KEY_SLOTS:
        rx = re.compile(pattern, re.IGNORECASE)
        items = [(k, v) for k, v in specs.items() if k not in used and rx.search(k)]
        used.update(k for k, _ in items)
        groups.append(KeySpecGroup(label=label, items=items, required=required))
    rest = [(k, v) for k, v in specs.items() if k not in used]
    return groups, rest
