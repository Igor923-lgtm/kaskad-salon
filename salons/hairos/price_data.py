"""Прайс-лист салона «HairOS Studio» — структурированные данные."""

PRICE_SECTIONS = [
    {
        "title": "✨ Наращивание волос",
        "note": "капсульное и голливудское наращивание",
        "services": [
            ("Капсульное наращивание волос", "от 200"),
            ("Голливудское наращивание волос", "от 250"),
            ("Коррекция наращивания", "от 100"),
            ("Снятие наращивания", "от 50"),
        ],
    },
    {
        "title": "💆 Восстановление волос",
        "note": "профессиональные процедуры",
        "services": [
            ("Кератиновое восстановление", "от 120"),
            ("Ботокс для волос", "от 100"),
            ("Холодное восстановление", "от 100"),
            ("Тотальная реконструкция", "от 150"),
        ],
    },
    {
        "title": "💇 Трихопигментация (SMP)",
        "note": "для мужчин и женщин",
        "services": [
            ("Трихопигментация (SMP)", "от 150"),
        ],
    },
    {
        "title": "📚 Обучение",
        "note": "курсы и мастер-классы",
        "services": [
            ("Обучение трихопигментации", "по запросу"),
            ("Мастер-класс по наращиванию", "по запросу"),
        ],
    },
]


def format_price(price):
    """Форматировать цену."""
    if isinstance(price, int):
        return f"{price} BYN"
    return str(price)


def format_section(section):
    """Форматировать секцию прайса в текст."""
    text = f"**{section['title']}**\n"
    if section.get("note"):
        text += f"_{section['note']}_\n\n"
    else:
        text += "\n"
    for name, price in section["services"]:
        text += f"• {name} — {format_price(price)}\n"
    return text


def get_price(service_name):
    """Получить числовую цену по названию услуги."""
    for section in PRICE_SECTIONS:
        for name, price in section["services"]:
            if name.lower() in service_name.lower() or service_name.lower() in name.lower():
                import re
                match = re.search(r'\d+', str(price))
                if match:
                    return int(match.group())
    return 0
