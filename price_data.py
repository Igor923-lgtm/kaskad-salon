"""Прайс-лист салона — загружается из price.json или используется по умолчанию."""
import json
import os
import config

# Путь к файлу прайса — сначала ищем per-salon, потом общий
SALON_PRICE_FILE = os.path.join(os.path.dirname(__file__), "salons", config.SALON_ID, "price.json")
DEFAULT_PRICE_FILE = os.path.join(os.path.dirname(__file__), "price.json")
PRICE_FILE = SALON_PRICE_FILE if os.path.exists(SALON_PRICE_FILE) else DEFAULT_PRICE_FILE


def _load_price():
    """Загрузить прайс из JSON-файла. Если файла нет — вернуть пустой список."""
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Конвертируем services из списков в кортежи
        for section in data:
            section["services"] = [tuple(s) for s in section.get("services", [])]
        return data
    return []


# Загружаем прайс при импорте
PRICE_SECTIONS = _load_price()


def format_price(price):
    """Форматировать цену для вывода."""
    if isinstance(price, int):
        return f"{price} руб."
    return f"{price} руб."


def get_all_services_flat() -> list[dict]:
    """Плоский список всех услуг."""
    result = []
    for section in PRICE_SECTIONS:
        for name, price in section["services"]:
            result.append({
                "name": name,
                "price": price,
                "section": section["title"],
            })
    return result


def format_section(section: dict) -> str:
    """Отформатировать раздел прайса для Telegram."""
    lines = [f"*{section['title']}*"]
    if section.get("note"):
        lines.append(f"_{section['note']}_")
    lines.append("")
    for i, (name, price) in enumerate(section["services"], 1):
        lines.append(f"{i}. {name} — {format_price(price)}")
    return "\n".join(lines)
