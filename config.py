import os
from dotenv import load_dotenv

SALON_ID = os.getenv("SALON_ID", "kaskad")
salon_env = os.path.join(os.path.dirname(__file__), "salons", SALON_ID, ".env")
if os.path.exists(salon_env):
    load_dotenv(salon_env)
else:
    load_dotenv()

# ── Telegram ──────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# ── База данных ───────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "bot_cache.db")

# ── Суперадмин ─────────────────────────────────────────────
SUPERADMIN_PHONE = "+375298592000"
SUPERADMIN_TG_ID = 294308582

# ── CRM ───────────────────────────────────────────────────
CRM_PASSWORD = os.getenv("CRM_PASSWORD", "kaskad2026")
CRM_API_URL = os.getenv("CRM_API_URL", "")

# ── Прокси ────────────────────────────────────────────────
SOCKS5_PROXY = os.getenv("SOCKS5_PROXY", "")

# ── Салон: общая информация ───────────────────────────────
SALON_NAME = os.getenv("SALON_NAME", "КАСКАД")
LOGO_PATH = os.getenv("LOGO_PATH", os.path.join(os.path.dirname(__file__), "logo.png"))

SALON_ADDRESS = os.getenv("SALON_ADDRESS", "Минск, Кальварийская ул., 52 (цокольный этаж)")
SALON_PHONE = os.getenv("SALON_PHONE", "+375 29 120-61-01")
SALON_PHONE_SECONDARY = os.getenv("SALON_PHONE_SECONDARY", "+375 (17) 350-81-91")
SALON_METRO = os.getenv("SALON_METRO", "Молодёжная (680 м)")
SALON_MAP_URL = os.getenv("SALON_MAP_URL", "https://yandex.by/maps/org/kaskad/1176196517/")
SALON_WHATSAPP = os.getenv("SALON_WHATSAPP", "+375 29 120-61-01")

# ── Салон: часы работы (day_of_week: 0=Пн, 6=Вс) ─────────
SALON_HOURS_START = int(os.getenv("SALON_HOURS_START", "10"))
SALON_HOURS_END = int(os.getenv("SALON_HOURS_END", "21"))
SALON_HOURS_SAT_START = int(os.getenv("SALON_HOURS_SAT_START", "11"))
SALON_HOURS_SAT_END = int(os.getenv("SALON_HOURS_SAT_END", "20"))
SALON_HOURS_SUN_START = int(os.getenv("SALON_HOURS_SUN_START", "11"))
SALON_HOURS_SUN_END = int(os.getenv("SALON_HOURS_SUN_END", "17"))

SALON_HOURS = {
    0: (SALON_HOURS_START, SALON_HOURS_END),
    1: (SALON_HOURS_START, SALON_HOURS_END),
    2: (SALON_HOURS_START, SALON_HOURS_END),
    3: (SALON_HOURS_START, SALON_HOURS_END),
    4: (SALON_HOURS_START, SALON_HOURS_END),
    5: (SALON_HOURS_SAT_START, SALON_HOURS_SAT_END),
    6: (SALON_HOURS_SUN_START, SALON_HOURS_SUN_END),
}

# ── Салон: часы работы текстом ────────────────────────────
SALON_HOURS_TEXT = os.getenv("SALON_HOURS_TEXT",
    f"пн-пт {SALON_HOURS_START}:00–{SALON_HOURS_END}:00; "
    f"сб {SALON_HOURS_SAT_START}:00–{SALON_HOURS_SAT_END}:00; "
    f"вс {SALON_HOURS_SUN_START}:00–{SALON_HOURS_SUN_END}:00"
)

# ── Часовой пояс ──────────────────────────────────────────
SALON_TIMEZONE = os.getenv("SALON_TIMEZONE", "Europe/Moscow")
os.environ.setdefault("TZ", SALON_TIMEZONE)
try:
    import time as _time
    _time.tzset()
except AttributeError:
    pass  # Windows не поддерживает tzset

# ── Функции салона (вкл/выкл) ─────────────────────────────
DISCOUNTS_ENABLED = os.getenv("DISCOUNTS_ENABLED", "true").lower() == "true"
BIRTHDAY_DISCOUNT = os.getenv("BIRTHDAY_DISCOUNT", "true").lower() == "true"
REVIEW_DISCOUNT = os.getenv("REVIEW_DISCOUNT", "true").lower() == "true"
GALLERY_ENABLED = os.getenv("GALLERY_ENABLED", "true").lower() == "true"
MASTERS_ENABLED = os.getenv("MASTERS_ENABLED", "true").lower() == "true"
RATING_ENABLED = os.getenv("RATING_ENABLED", "true").lower() == "true"
MY_BOOKINGS_ENABLED = os.getenv("MY_BOOKINGS_ENABLED", "true").lower() == "true"
HISTORY_ENABLED = os.getenv("HISTORY_ENABLED", "true").lower() == "true"
BIRTHDAY_ENABLED = os.getenv("BIRTHDAY_ENABLED", "true").lower() == "true"
CONTACT_ENABLED = os.getenv("CONTACT_ENABLED", "true").lower() == "true"
WIDGET_ENABLED = os.getenv("WIDGET_ENABLED", "true").lower() == "true"
COWORKING_ENABLED = os.getenv("COWORKING_ENABLED", "true").lower() == "true"
ORG_TYPE = os.getenv("ORG_TYPE", "beauty")

# ── Буфер между записями (минуты, 0 = выкл) ──────────────
BUFFER_MINUTES = int(os.getenv("BUFFER_MINUTES", "0") or "0")

# ── Список всех флагов ────────────────────────────────────
FEATURE_FLAGS = [
    "DISCOUNTS_ENABLED", "BIRTHDAY_DISCOUNT", "REVIEW_DISCOUNT",
    "GALLERY_ENABLED", "MASTERS_ENABLED", "RATING_ENABLED",
    "MY_BOOKINGS_ENABLED", "HISTORY_ENABLED", "BIRTHDAY_ENABLED",
    "CONTACT_ENABLED", "WIDGET_ENABLED", "COWORKING_ENABLED",
]


async def load_settings_from_db():
    """Загрузить настройки из БД (перезаписать значения из .env)."""
    import aiosqlite
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT key, value FROM salon_settings")
            rows = await cur.fetchall()
            for key, value in rows:
                if key in FEATURE_FLAGS:
                    globals()[key] = value.lower() == "true"
    except Exception:
        pass  # Таблица ещё не создана — используем значения из .env
