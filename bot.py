"""Telegram-бот салона красоты."""
import asyncio
import calendar
import logging
import os
from datetime import datetime, timedelta

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InputMediaPhoto,
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters,
)
from telegram.constants import ParseMode

import config
import db
import price_data
import aiosqlite

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════
#  Состояния ConversationHandler
# ══════════════════════════════════════════════════════════
(
    MAIN_MENU,
    SHOW_PRICE,
    SHOW_MASTERS,
    BOOK_SELECT_SERVICE,
    BOOK_SELECT_MASTER,
    BOOK_SELECT_DATE,
    BOOK_CONFIRM,
    RATE_SELECT_BOOKING,
    RATE_GIVE_SCORE,
    RATE_COMMENT,
    ADMIN_MENU,
    ADMIN_ADD_SERVICE_NAME,
    ADMIN_ADD_SERVICE_PRICE,
    ADMIN_ADD_SERVICE_DESC,
    ADMIN_ADD_MASTER_NAME,
    ADMIN_ADD_MASTER_SPEC,
    ADMIN_ADD_MASTER_PHOTO,
    ADMIN_VIEW_CLIENTS,
    ADMIN_SET_DISCOUNT_TGID,
    ADMIN_SET_DISCOUNT_VALUE,
    ADMIN_VIEW_REVIEWS,
    ADMIN_EDIT_CONTENT,
    ADMIN_EDIT_CONTENT_SAVE,
    PHONE_INPUT,
    ADMIN_MAILING_TEXT,
    ADMIN_MAILING_CONFIRM,
    BOOK_ASK_NAME,
    REVIEW_GIVE_SCORE,
    BOOK_SELECT_GENDER,
    ADMIN_MAILING_SEGMENT_TEXT,
    ADMIN_MAILING_SEGMENT_CONFIRM,
    BIRTHDAY_INPUT,
    EDIT_SELECT_BOOKING,
    ADMIN_SET_CUSTOM_HOURS,
    COWORKING_SELECT_DATE,
    COWORKING_SELECT_START,
    COWORKING_SELECT_END,
    COWORKING_CONFIRM,
    COWORKING_CANCEL_SELECT,
    BOOK_SELECT_START,
    BOOK_SELECT_END,
    WAITLIST,
) = range(42)


# ══════════════════════════════════════════════════════════
#  Утилиты
# ══════════════════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


async def _is_coworking_org() -> bool:
    flags = await db.get_feature_flags()
    return flags.get("ORG_TYPE", "beauty") == "coworking"


# Ресурс брони в коворкинге: master_name для слотов/расписания салона
_COWORKING_RESOURCE = "Пространство"


async def _book_btn_label() -> str:
    if await _is_coworking_org():
        return "🏢 Забронировать слот"
    return "📅 Записаться"


async def main_menu_kb(user_id: int | None = None):
    """Главное меню бота из БД (bot_menu) + флаги.
    В режиме Коворкинг кнопка «🔒 Коворкинг» добавляется во ВСЕХ ответах меню (консистентно)."""
    flags = await db.get_feature_flags()
    items = await db.get_bot_menu()
    buttons = []
    for item in items:
        if not item.get("enabled", 1):
            continue
        action_type = item.get("action_type") or "section"
        action_value = item.get("action_value") or ""
        label = item.get("label") or action_value
        emoji = (item.get("emoji") or "").strip()
        full_label = f"{emoji} {label}".strip() if emoji else label
        if action_type == "url":
            if action_value.startswith("http://") or action_value.startswith("https://"):
                buttons.append([InlineKeyboardButton(full_label, url=action_value)])
            continue
        # section
        flag = db.SECTION_FLAG_MAP.get(action_value)
        if flag and not flags.get(flag, True):
            continue
        buttons.append([InlineKeyboardButton(full_label, callback_data=action_value)])
    if not buttons:
        # fallback на старое поведение, если меню пустое
        return await _legacy_main_menu_kb(flags, user_id=user_id)
    # Кнопка ковopкинга — только в режиме coworking (везде, не только /start)
    if flags.get("COWORKING_ENABLED", True) and flags.get("ORG_TYPE", "beauty") == "coworking":
        already = any(
            getattr(b, "callback_data", None) == "coworking"
            for row in buttons for b in row
        )
        if not already:
            show = True
            if user_id is not None:
                is_admin = user_id in config.ADMIN_IDS
                master = await db.get_master_by_tg_id(user_id)
                show = bool(master or is_admin)
            if show:
                buttons.append([InlineKeyboardButton("🔒 Коворкинг", callback_data="coworking")])
    return InlineKeyboardMarkup(buttons)


async def _legacy_main_menu_kb(flags: dict, user_id: int | None = None):
    org = flags.get("ORG_TYPE", "beauty")
    if org == "coworking":
        buttons = [
            [InlineKeyboardButton("🏢 Забронировать слот", callback_data="menu_book")],
            [InlineKeyboardButton("💰 Тарифы", callback_data="menu_services")],
        ]
        if flags.get("MASTERS_ENABLED", True):
            buttons.append([InlineKeyboardButton("🪑 Пространства", callback_data="menu_masters")])
        if flags.get("GALLERY_ENABLED", True):
            buttons.append([InlineKeyboardButton("📸 Пространства в кадре", callback_data="menu_works")])
        if flags.get("MY_BOOKINGS_ENABLED", True):
            buttons.append([InlineKeyboardButton("📋 Мои брони", callback_data="menu_my_bookings")])
            buttons.append([InlineKeyboardButton("✏️ Изменить бронь", callback_data="menu_edit_booking")])
        if flags.get("HISTORY_ENABLED", True):
            buttons.append([InlineKeyboardButton("📋 История броней", callback_data="menu_history")])
        if flags.get("CONTACT_ENABLED", True):
            buttons.append([InlineKeyboardButton("📍 Как нас найти", callback_data="menu_location")])
        return InlineKeyboardMarkup(buttons)
    buttons = [
        [InlineKeyboardButton("📅 Записаться", callback_data="menu_book")],
        [InlineKeyboardButton("💇‍♀️ Услуги и цены", callback_data="menu_services")],
    ]
    if flags.get("MASTERS_ENABLED", True):
        buttons.append([InlineKeyboardButton("👩‍🎨 Наши мастера", callback_data="menu_masters")])
    if flags.get("GALLERY_ENABLED", True):
        buttons.append([InlineKeyboardButton("📸 Работы", callback_data="menu_works")])
    if flags.get("MY_BOOKINGS_ENABLED", True):
        buttons.append([InlineKeyboardButton("📋 Мои записи", callback_data="menu_my_bookings")])
        buttons.append([InlineKeyboardButton("✏️ Изменить запись", callback_data="menu_edit_booking")])
        buttons.append([InlineKeyboardButton("⏳ Лист ожидания", callback_data="menu_waitlist")])
    if flags.get("HISTORY_ENABLED", True):
        buttons.append([InlineKeyboardButton("📋 История визитов", callback_data="menu_history")])
    if flags.get("DISCOUNTS_ENABLED", True):
        buttons.append([InlineKeyboardButton("🎁 Мои скидки", callback_data="menu_discount")])
    if flags.get("BIRTHDAY_ENABLED", True):
        buttons.append([InlineKeyboardButton("🎂 Мой день рождения", callback_data="menu_birthday")])
    if flags.get("CONTACT_ENABLED", True):
        buttons.append([InlineKeyboardButton("📍 Как нас найти", callback_data="menu_location")])
    return InlineKeyboardMarkup(buttons)


async def main_menu_kb_with_coworking(user_id: int):
    """Совместимость: кнопка ковopкинга теперь внутри main_menu_kb()."""
    return await main_menu_kb(user_id)


def admin_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Управление услугами", callback_data="admin_services")],
        [InlineKeyboardButton("👩‍🎨 Управление мастерами", callback_data="admin_masters")],
        [InlineKeyboardButton("⭐ Рейтинг мастеров", callback_data="admin_ratings")],
        [InlineKeyboardButton("📅 График работ", callback_data="admin_schedule")],
        [InlineKeyboardButton("📋 Записи (ожидают)", callback_data="admin_bookings")],
        [InlineKeyboardButton("👥 База клиентов", callback_data="admin_clients")],
        [InlineKeyboardButton("🔍 Потерянные клиенты", callback_data="admin_lost_clients")],
        [InlineKeyboardButton("💬 Отзывы", callback_data="admin_reviews")],
        [InlineKeyboardButton("🎁 Управление скидками", callback_data="admin_discounts")],
        [InlineKeyboardButton("📨 Рассылка по сегментам", callback_data="admin_mailing_segments")],
        [InlineKeyboardButton("✏️ Контент (прайс, тексты)", callback_data="admin_content")],
        [InlineKeyboardButton("📊 Аналитика", callback_data="admin_analytics")],
        [InlineKeyboardButton("⚙️ Настройки функций", callback_data="admin_settings")],
        [InlineKeyboardButton("🔙 Назад в главное меню", callback_data="back_main")],
    ])


def back_btn(callback_data: str = "back_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data=callback_data)]])


def ensure_back_last(rows, callback_data: str = "back_main", label: str = "◀️ Назад"):
    """Последняя строка клавиатуры всегда «Назад» (или уже back-like) — иначе кнопка теряется у UI."""
    if not rows:
        return [[InlineKeyboardButton(label, callback_data=callback_data)]]
    try:
        last_texts = " ".join(getattr(btn, "text", "") for btn in rows[-1])
    except Exception:
        last_texts = ""
    if any(s in last_texts for s in ("Назад", "Отмена", "Меню", "Начало", "В главное", "К категори", "К календар")):
        return rows
    rows.append([InlineKeyboardButton(label, callback_data=callback_data)])
    return rows


async def ensure_client(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> dict:
    user = update.effective_user
    client = await db.get_client(user.id)
    if client:
        # Обновляем имя если изменилось
        if user.full_name and user.full_name != client.get("name", ""):
            await db.update_client_name(user.id, user.full_name)
        return {"id": user.id, "telegram_id": user.id, "name": client.get("name", "") or user.full_name or ""}
    # Клиент не найден — создаём
    await db.upsert_client(user.id, user.full_name or "")
    return {"id": user.id, "telegram_id": user.id, "name": user.full_name or ""}


async def send_phone_request(update: Update, ctx: ContextTypes.DEFAULT_TYPE, next_state):
    kb = ReplyKeyboardMarkup(
        [[KeyboardButton("📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True,
    )
    await update.effective_chat.send_message(
        "📱 Пожалуйста, поделитесь номером телефона для записи:",
        reply_markup=kb,
    )
    return next_state


# ══════════════════════════════════════════════════════════
#  /start
# ══════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await ensure_client(update, ctx)
    # Фото: bot_start_photo из CRM, иначе логотип
    start_photo = await db.get_setting("bot_start_photo", "")
    photo_path = start_photo if start_photo and os.path.exists(
        start_photo if start_photo.startswith("/") else os.path.join(os.path.dirname(__file__), start_photo.lstrip("/"))
    ) else (config.LOGO_PATH if os.path.exists(config.LOGO_PATH) else "")
    if photo_path:
        try:
            with open(photo_path, "rb") as photo:
                # без кнопок на фото: меню уйдёт ниже текстом welcome (порядок в чате)
                await update.message.reply_photo(photo=photo)
        except Exception as e:
            log.warning(f"Не удалось отправить фото старта: {e}")
    # Текст: content key 'welcome' из CRM, иначе дефолт
    welcome = (await db.get_content("welcome") or "").strip()
    if welcome:
        text = welcome
    elif await _is_coworking_org():
        text = (
            "✨ Добро пожаловать!\n\n"
            "Я — бот коворкинга. Здесь вы можете:\n"
            "• Посмотреть тарифы\n"
            "• Выбрать пространство\n"
            "• Забронировать слот\n"
            "• Оценить обслуживание\n\n"
            "Выберите раздел:"
        )
    else:
        text = (
            "✨ Добро пожаловать!\n\n"
            "Я — бот салона красоты. Здесь вы можете:\n"
            "• Посмотреть услуги и цены\n"
            "• Узнать о наших мастерах\n"
            "• Записаться на процедуру\n"
            "• Оценить обслуживание\n\n"
            "Выберите раздел:"
        )
    kb = await main_menu_kb_with_coworking(update.effective_user.id)
    await update.message.reply_text(text, reply_markup=kb)
    return MAIN_MENU


# ══════════════════════════════════════════════════════════
#  Клиент: Услуги и цены
# ══════════════════════════════════════════════════════════

async def cb_services(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    prompt = "Тарифы для кого?" if await _is_coworking_org() else "Прайс-лист для кого?"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👩 Женщине", callback_data="price_gender_f")],
        [InlineKeyboardButton("👨 Мужчине", callback_data="price_gender_m")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text(prompt, reply_markup=kb)
    return BOOK_SELECT_GENDER


async def services_select_gender(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gender = query.data.replace("price_gender_", "")
    sections = await db.get_services_by_category()
    kb = []
    for i, section in enumerate(sections):
        title = section["title"]
        if gender == "m":
            if any(kw in title.lower() for kw in ["мужск", "стрижка", "окрашив", "барбер"]):
                kb.append([InlineKeyboardButton(title[:40], callback_data=f"price_sec_{i}")])
        else:
            if not any(kw in title.lower() for kw in ["мужск", "барбер"]):
                kb.append([InlineKeyboardButton(title[:40], callback_data=f"price_sec_{i}")])
    if not kb:
        kb.append([InlineKeyboardButton("Нет услуг", callback_data="back_main")])
    else:
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    await query.edit_message_text("Выберите раздел:", reply_markup=InlineKeyboardMarkup(kb))
    return BOOK_SELECT_SERVICE


async def services_select_section(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sec_idx = int(query.data.replace("price_sec_", ""))
    sections = await db.get_services_by_category()
    if sec_idx >= len(sections):
        await query.edit_message_text("Раздел не найден.", reply_markup=back_btn())
        return MAIN_MENU
    section = sections[sec_idx]
    lines = [f"*{section['title']}*"]
    if section.get("note"):
        lines.append(f"_{section['note']}_")
    lines.append("")
    for i, svc in enumerate(section["services"], 1):
        lines.append(f"{i}. {svc['name']} — {svc['price'] or '—'}")
    text = "\n".join(lines)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(await _book_btn_label(), callback_data="menu_book")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return MAIN_MENU


WORKS_DIR = os.path.join(os.path.dirname(__file__), "works_photos")


async def _input_media_photo(path: str, caption: str | None = None):
    """Лёгкое фото для Telegram: JPEG ≤1280px, ~≤400 КБ.
    Иначе sendMediaGroup → image_process_failed / тормоза на тяжёлых файлах."""
    try:
        from io import BytesIO
        from PIL import Image, ImageFile, ImageOps
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        img = Image.open(path)
        img.load()
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        if max(img.size) > 1280:
            img.thumbnail((1280, 1280))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        def _jpeg(im, q):
            b = BytesIO()
            im.save(b, format="JPEG", quality=q, optimize=True)
            return b

        buf = _jpeg(img, 78)
        if buf.tell() > 400 * 1024:
            # ещё легче: 1024px + q65
            im2 = img.copy()
            if max(im2.size) > 1024:
                im2.thumbnail((1024, 1024))
            buf = _jpeg(im2, 65)
        buf.seek(0)
        if caption:
            return InputMediaPhoto(buf, caption=caption)
        return InputMediaPhoto(buf)
    except Exception as e:
        log.warning(f"Не удалось перекодировать {path}: {e}")
        try:
            fh = open(path, "rb")
            if caption:
                return InputMediaPhoto(fh, caption=caption)
            return InputMediaPhoto(fh)
        except Exception as e2:
            log.warning(f"Не удалось открыть {path}: {e2}")
            return None

# Категории работ с подпапками
WORKS_CATEGORIES = [
    ("🔽 Загущение", "zagushchenie"),
    ("🔽 Наращивание", "narashchivanie"),
    ("🔽 Трихопигментация (SMP)", "smp"),
    ("🔽 Ботокс/Кератин", "botoks_keratin"),
]


async def cb_contact(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Связаться с администратором."""
    query = update.callback_query
    await query.answer()
    log.info(f"CONTACT: called, user={query.from_user.id}")
    text = (
        f"📞 *Связаться с администратором*\n\n"
        f"Телефон: {config.SALON_PHONE}\n"
        f"{config.SALON_HOURS_TEXT}"
    )
    phone_clean = config.SALON_PHONE.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📞 Позвонить", url=f"tel:{phone_clean}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.warning(f"CONTACT: edit failed: {e}")
        await query.message.reply_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return MAIN_MENU


async def cb_location(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать адрес и контакты салона."""
    query = update.callback_query
    await query.answer()
    salon_name = await db.get_setting("salon_name", config.SALON_NAME)
    text = (
        f"📍 *{salon_name} — Салон красоты*\n\n"
        f"📍 *Адрес:*\n{config.SALON_ADDRESS}\n\n"
        f"📞 *Телефоны:*\n{config.SALON_PHONE}\n{config.SALON_PHONE_SECONDARY}\n\n"
        f"🕐 *Режим работы:*\nПн-Пт: {config.SALON_HOURS_START}:00 – {config.SALON_HOURS_END}:00\n"
        f"Сб: {config.SALON_HOURS_SAT_START}:00 – {config.SALON_HOURS_SAT_END}:00\n"
        f"Вс: {config.SALON_HOURS_SUN_START}:00 – {config.SALON_HOURS_SUN_END}:00\n\n"
        f"🚇 *Метро:* {config.SALON_METRO}\n\n"
        f"📲 *Соцсети:*\nWhatsApp: {config.SALON_WHATSAPP}\nTelegram: {config.SALON_PHONE}\n\n"
        f"🌐 *Карты:*\n{config.SALON_MAP_URL}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(await _book_btn_label(), callback_data="menu_book")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return MAIN_MENU


async def cb_works(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать категории работ/пространств."""
    query = update.callback_query
    await query.answer()
    categories = await db.get_works_categories()
    kb = []
    for label, folder in categories:
        kb.append([InlineKeyboardButton(label, callback_data=f"works_cat_{folder}")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    if await _is_coworking_org():
        header = "📸 *Пространства*\nВыберите категорию:"
    else:
        header = "📸 *Наши работы*\nВыберите категорию:"
    await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    return MAIN_MENU


async def cb_works_category(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать фото из выбранной категории."""
    query = update.callback_query
    await query.answer()
    folder = query.data.replace("works_cat_", "")
    cat_dir = os.path.join(WORKS_DIR, folder)
    if not os.path.isdir(cat_dir):
        await query.edit_message_text("Фото скоро появятся.", reply_markup=back_btn())
        return MAIN_MENU
    # регистр расширений: .PNG / .JPG видит и CRM (suffix.lower), бот тоже должен
    photos = sorted(
        f for f in os.listdir(cat_dir)
        if f.lower().endswith((".webp", ".jpg", ".jpeg", ".png"))
    )
    if not photos:
        await query.edit_message_text("Фото в этой категории скоро появятся.", reply_markup=back_btn())
        return MAIN_MENU
    # Название категории
    categories = await db.get_works_categories()
    cat_name = next((label for label, f in categories if f == folder), folder)
    salon_name = await db.get_setting("salon_name", config.SALON_NAME)
    # 1) «Отправляю…» — БЕЗ кнопок: nav будет ниже фото, не выше
    await query.edit_message_text(f"📸 *{cat_name}* ({len(photos)} фото)\nОтправляю...", parse_mode=ParseMode.MARKDOWN)
    for i in range(0, min(len(photos), 15), 5):
        batch = photos[i:i+5]
        media = []
        for j, photo in enumerate(batch):
            path = os.path.join(cat_dir, photo)
            caption = f"📸 {cat_name} — {salon_name}" if (j == 0 and i == 0) else None
            item = await _input_media_photo(path, caption)
            if item is not None:
                media.append(item)
        if not media:
            continue
        try:
            await query.message.reply_media_group(media)
        except Exception as e:
            log.warning(f"Ошибка отправки фото: {e}")
    # 2) Кнопки — НОВЫМ сообщением ПОД фото (media_group не умеет reply_markup)
    kb_rows = [
        [InlineKeyboardButton(await _book_btn_label(), callback_data="menu_book")],
        [InlineKeyboardButton("◀️ К категориям", callback_data="menu_works")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ]
    await query.message.reply_text(
        "Нравится? Забронируйте слот!" if await _is_coworking_org() else "Нравится? Запишитесь!",
        reply_markup=InlineKeyboardMarkup(kb_rows),
    )
    return MAIN_MENU


# ══════════════════════════════════════════════════════════
#  Клиент: Мастера
# ══════════════════════════════════════════════════════════

async def cb_masters(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    flags = await db.get_feature_flags()
    org = flags.get("ORG_TYPE", "beauty")
    masters = await db.get_masters(org_type=org)
    if not masters:
        if await _is_coworking_org():
            text = "🪑 Пространства скоро появятся."
        else:
            text = "Информация о мастерах скоро появится."
        await query.edit_message_text(text, reply_markup=back_btn())
        return MAIN_MENU
    for m in masters:
        if await _is_coworking_org():
            caption = (
                f"🪑 *{m['name']}*\n"
                f"Тип: {m.get('specialization', '—')}\n"
                f"{m.get('description', '')}"
            )
        else:
            caption = (
                f"👩‍🎨 *{m['name']}*\n"
                f"Специализация: {m.get('specialization', '—')}\n"
                f"{m.get('description', '')}"
            )
        photo_file_id = (m.get("photo_file_id") or "").strip() if isinstance(m, dict) else ""
        if photo_file_id:
            try:
                await query.message.reply_photo(photo_file_id, caption=caption, parse_mode=ParseMode.MARKDOWN)
                continue
            except Exception as e:
                log.warning(f"Мастер {m.get('name')}: не удалось фото, шлю текст: {e}")
        await query.message.reply_text(caption, parse_mode=ParseMode.MARKDOWN)
    kb_rows = [
        [InlineKeyboardButton(await _book_btn_label(), callback_data="menu_book")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ]
    await query.message.reply_text("Выберите действие:", reply_markup=InlineKeyboardMarkup(kb_rows))
    return MAIN_MENU


# ══════════════════════════════════════════════════════════
#  Клиент: Консультация
# ══════════════════════════════════════════════════════════

MARINA_TG_ID = 294308582

async def cb_consultation(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Отправить запрос на консультацию."""
    query = update.callback_query
    log.info(f"CONSULTATION: called, user={query.from_user.id}, data={query.data}")
    await query.answer()
    user = update.effective_user
    client_phone = ""
    try:
        client = await db.get_client(user.id)
        if client:
            client_phone = client.get("phone", "")
    except Exception as e:
        log.warning(f"CONSULTATION: get_client error: {e}")
    name = user.first_name or user.username or str(user.id)
    if not client_phone:
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Отправить номер", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True,
        )
        await query.message.reply_text(
            "📱 Пожалуйста, поделитесь номером телефона для связи:",
            reply_markup=kb,
        )
        ctx.user_data["consultation_pending"] = True
        return PHONE_INPUT
    await _send_consultation(ctx, name, client_phone, user.username)
    await query.edit_message_text(
        "Спасибо за обращение, ближайшее время Вас проконсультируют.",
        reply_markup=back_btn(),
    )
    return MAIN_MENU


async def _send_consultation(ctx, name, phone, username):
    username_text = f"\nTelegram: @{username}" if username else ""
    msg = (
        f"💬 Требуется консультация!\n\n"
        f"Клиент: {name}\n"
        f"Телефон: {phone}{username_text}\n"
        f"Пожалуйста, свяжитесь с клиентом."
    )
    try:
        await ctx.bot.send_message(MARINA_TG_ID, msg)
        log.info(f"CONSULTATION: sent to {MARINA_TG_ID}")
    except Exception as e:
        log.error(f"CONSULTATION: bot.send_message FAILED: {e}")
        try:
            import httpx
            token = config.BOT_TOKEN
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            async with httpx.AsyncClient() as hc:
                r = await hc.post(url, json={"chat_id": MARINA_TG_ID, "text": msg})
                log.info(f"CONSULTATION: httpx status={r.status_code} body={r.text[:200]}")
        except Exception as e2:
            log.error(f"CONSULTATION: httpx also FAILED: {e2}")


# ══════════════════════════════════════════════════════════
#  Клиент: Запись
# ══════════════════════════════════════════════════════════

async def _booking_sections_kb(gender: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    """Клавиатура разделов при записи. gender=None — все разделы (коворкинг)."""
    sections = await db.get_services_by_category()
    kb = [[InlineKeyboardButton("💬 КОНСУЛЬТАЦИЯ", callback_data="consultation")]]
    for i, section in enumerate(sections):
        title = section["title"]
        if gender == "m":
            if "smp" in title.lower() or "трихопигмент" in title.lower():
                kb.append([InlineKeyboardButton(title[:40], callback_data=f"book_sec_{i}")])
        else:
            kb.append([InlineKeyboardButton(title[:40], callback_data=f"book_sec_{i}")])
    if len(kb) == 1 and not sections:
        kb = [[InlineKeyboardButton("Нет услуг", callback_data="back_main")]]
    else:
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    text = "Выберите тариф:" if gender is None else "Выберите раздел услуг:"
    return text, InlineKeyboardMarkup(kb)


async def cb_book(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log.info(f"BOOK: cb_book called, user={query.from_user.id}")
    ctx.user_data["booking"] = {}
    if await _is_coworking_org():
        # В коворкинге пол и мастера не выбираем — сразу тарифы
        text, kb = await _booking_sections_kb(None)
        await query.edit_message_text(text, reply_markup=kb)
        return BOOK_SELECT_SERVICE
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👩 Женщине", callback_data="gender_f")],
        [InlineKeyboardButton("👨 Мужчине", callback_data="gender_m")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text("Кому записываемся?", reply_markup=kb)
    return BOOK_SELECT_GENDER


async def book_select_gender(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    gender = query.data.replace("gender_", "")
    ctx.user_data["booking"]["gender"] = gender
    log.info(f"BOOK: gender selected = {gender}, state={ctx.user_data.get('booking', {})}")
    text, kb = await _booking_sections_kb(gender)
    await query.edit_message_text(text, reply_markup=kb)
    return BOOK_SELECT_SERVICE


async def book_select_section(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log.info(f"BOOK: select_section called, data={query.data}")
    sec_idx = int(query.data.replace("book_sec_", ""))
    sections = await db.get_services_by_category()
    if sec_idx >= len(sections):
        await query.edit_message_text("Раздел не найден.", reply_markup=back_btn())
        return MAIN_MENU
    section = sections[sec_idx]
    ctx.user_data["booking"] = {
        "section_idx": sec_idx,
        "multi_services": [],
        "gender": ctx.user_data.get("booking", {}).get("gender"),
    }
    kb = []
    for i, svc in enumerate(section["services"]):
        label = f"☐ {svc['name']} — {svc['price'] or '—'}"
        kb.append([InlineKeyboardButton(label[:60], callback_data=f"book_mtgl_{sec_idx}_{i}")])
    kb.append([InlineKeyboardButton("✅ Далее (выбрано: 0)", callback_data=f"book_mdone_{sec_idx}")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    await query.edit_message_text(
        f"*{section['title']}*\nОтметьте услуги (можно несколько):",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.MARKDOWN,
    )
    return BOOK_SELECT_SERVICE


async def book_select_service(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Legacy single-service callback — redirect to multi toggle UI."""
    query = update.callback_query
    await query.answer()
    parts = query.data.replace("book_svc_", "").split("_")
    sec_idx = int(parts[0])
    query.data = f"book_sec_{sec_idx}"
    return await book_select_section(update, ctx)


async def book_multi_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Буфер: вкл/выкл услугу в мульти-выборе."""
    query = update.callback_query
    await query.answer()
    parts = query.data.replace("book_mtgl_", "").split("_")
    sec_idx, svc_idx = int(parts[0]), int(parts[1])
    sections = await db.get_services_by_category()
    section = sections[sec_idx]
    svc = section["services"][svc_idx]
    booking = ctx.user_data.setdefault("booking", {})
    multi: list = booking.get("multi_services") or []
    existing = next((m for m in multi if m.get("id") == svc.get("id")), None)
    if existing:
        multi = [m for m in multi if m.get("id") != svc.get("id")]
    else:
        multi = multi + [{
            "id": svc.get("id"),
            "name": svc["name"],
            "price": svc.get("price") or "—",
            "duration_minutes": svc.get("duration_minutes") or 0,
        }]
    booking["multi_services"] = multi
    booking["section_idx"] = sec_idx

    kb = []
    for i, s in enumerate(section["services"]):
        checked = any(m.get("id") == s.get("id") for m in multi)
        mark = "☑" if checked else "☐"
        label = f"{mark} {s['name']} — {s['price'] or '—'}"
        kb.append([InlineKeyboardButton(label[:60], callback_data=f"book_mtgl_{sec_idx}_{i}")])
    kb.append([InlineKeyboardButton(
        f"✅ Далее (выбрано: {len(multi)})",
        callback_data=f"book_mdone_{sec_idx}",
    )])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    try:
        await query.edit_message_text(
            f"*{section['title']}*\nОтметьте услуги (можно несколько):",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        pass
    return BOOK_SELECT_SERVICE


async def book_multi_done(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Подтвердить мульти-выбор → мастера / календарь."""
    query = update.callback_query
    await query.answer()
    booking = ctx.user_data.setdefault("booking", {})
    multi = booking.get("multi_services") or []
    if not multi:
        await query.answer("Отметьте хотя бы одну услугу", show_alert=True)
        return BOOK_SELECT_SERVICE

    booking["service_name"] = " + ".join(m["name"] for m in multi)
    booking["service_price"] = " + ".join(str(m["price"]) for m in multi)
    booking["service_ids"] = [m["id"] for m in multi if m.get("id") is not None]
    booking["duration_minutes"] = sum(
        (max(0, int(m.get("duration_minutes") or 0)) + 14) // 15 * 15
        if int(m.get("duration_minutes") or 0) > 0 else 15
        for m in multi
    )
    sec_idx = booking.get("section_idx", 0)

    if await _is_coworking_org():
        booking["master_name"] = _COWORKING_RESOURCE
        now = datetime.now()
        text, kb = await _build_calendar_kb(
            _COWORKING_RESOURCE, now.year, now.month,
            duration_minutes=booking.get("duration_minutes") or 0,
        )
        await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        return BOOK_SELECT_DATE

    _flags = await db.get_feature_flags()
    masters = await db.get_masters_by_category(sec_idx, org_type=_flags.get("ORG_TYPE", "beauty"))
    if not masters:
        await query.edit_message_text(
            "К сожалению, нет свободных мастеров по этой услуге.",
            reply_markup=back_btn(),
        )
        return MAIN_MENU
    kb = []
    for m in masters:
        kb.append([InlineKeyboardButton(m["name"], callback_data=f"book_m_{m['id']}")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    await query.edit_message_text(
        f"Выбрано: {booking['service_name']}\nВыберите мастера:",
        reply_markup=InlineKeyboardMarkup(kb),
    )
    return BOOK_SELECT_MASTER


async def _build_calendar_kb(master_name: str, year: int = None, month: int = None,
                              duration_minutes: int = 0) -> tuple:
    """Построить квадратный календарь (7x6) для выбора даты."""
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    # Получаем расписание мастера
    schedule = await db.get_master_schedule(master_name)
    off_days = {s["day_of_week"] for s in schedule if s.get("is_day_off")}
    sched_map = {}
    for s in schedule:
        dow = s["day_of_week"]
        sel = s.get("selected_hours", "")
        if sel:
            sched_map[dow] = [h.strip() for h in sel.split(",") if h.strip()]
        else:
            sh = int(s["start_time"].split(":")[0])
            eh = int(s["end_time"].split(":")[0])
            slots = []
            for h in range(sh, eh):
                for m in (0, 15, 30, 45):
                    slots.append(f"{h:02d}:{m:02d}")
            sched_map[dow] = slots
    # Для дней без расписания мастера — используем часы салона
    for d in range(7):
        if d not in sched_map and d not in off_days:
            sched_map[d] = db.get_salon_slots(d)
    # Обрезаем все слоты по часам салона
    for d in sched_map:
        sched_map[d] = db._clamp_to_salon(sched_map[d], d)

    # Собираем все даты месяца
    cal = calendar.monthcalendar(year, month)
    month_name = [
        "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ][month]

    # Собираем даты для проверки занятости
    dates_in_month = []
    for week in cal:
        for day in week:
            if day != 0:
                d = datetime(year, month, day)
                ds = d.strftime("%Y-%m-%d")
                if d >= now.replace(hour=0, minute=0, second=0, microsecond=0):
                    dates_in_month.append(ds)

    # Получаем кастомные расписания на даты месяца
    date_schedules = {}
    if dates_in_month:
        async with aiosqlite.connect(config.DB_PATH) as adb:
            ph = ",".join("?" * len(dates_in_month))
            cur = await adb.execute(
                f"SELECT date, time_slots, is_day_off FROM master_date_schedule WHERE master_name = ? AND date IN ({ph})",
                [master_name] + dates_in_month,
            )
            for r in await cur.fetchall():
                date_schedules[r[0]] = {"time_slots": r[1] or "", "is_day_off": r[2]}

    # Получаем занятые окна за весь месяц (длительность + salon buffer)
    occupied_by_date: dict = {}
    buffer_minutes = await db.get_buffer_minutes()
    if dates_in_month:
        async with aiosqlite.connect(config.DB_PATH) as adb:
            adb.row_factory = aiosqlite.Row
            ph = ",".join("?" * len(dates_in_month))
            cur = await adb.execute(
                f"SELECT date, time, duration_minutes FROM bookings WHERE master_name = ? AND date IN ({ph})",
                [master_name] + dates_in_month,
            )
            for r in await cur.fetchall():
                row = dict(r)
                occupied_by_date.setdefault(row["date"], set()).update(
                    db._occupied_with_buffer(row, buffer_minutes)
                )

    # Определяем доступность каждого дня
    day_avail = {}
    for week in cal:
        for day in week:
            if day == 0:
                continue
            d = datetime(year, month, day)
            ds = d.strftime("%Y-%m-%d")
            dow = d.weekday()  # 0=Пн

            # Прошедшие дни
            if d < now.replace(hour=0, minute=0, second=0, microsecond=0):
                day_avail[day] = False
                continue

            # Проверяем кастомное расписание на дату
            ds_entry = date_schedules.get(ds)
            if ds_entry:
                if ds_entry["is_day_off"]:
                    day_avail[day] = False
                    continue
                slots_str = ds_entry["time_slots"]
                if slots_str:
                    all_slots = [h.strip() for h in slots_str.split(",") if h.strip()]
                else:
                    all_slots = []
            else:
                # Выходные мастера (по недельному расписанию)
                if dow in off_days:
                    day_avail[day] = False
                    continue
                all_slots = sched_map.get(dow, [])

            booked = occupied_by_date.get(ds, set())
            if ds == now.strftime("%Y-%m-%d"):
                now_str = now.strftime("%H:%M")
                candidates = [t for t in all_slots if t > now_str]
            else:
                candidates = all_slots
            day_avail[day] = any(
                db.window_is_free(t, duration_minutes, all_slots, booked)
                for t in candidates
            )

    # Строим текст
    if await _is_coworking_org() or master_name == _COWORKING_RESOURCE:
        text = f"📅 *{month_name} {year}*\nВыберите дату брони:"
    else:
        text = f"📅 *{month_name} {year}*\nВыберите дату для записи к {master_name}:"

    # Строим клавиатуру
    kb = []

    # Навигация по месяцам
    prev_month = month - 1
    prev_year = year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year += 1

    # Не даём листать в прошлое
    nav_row = []
    if (prev_year > now.year) or (prev_year == now.year and prev_month >= now.month):
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"cal_month_{prev_year}_{prev_month:02d}"))
    nav_row.append(InlineKeyboardButton(f"{month_name} {year}", callback_data="cal_ignore"))
    nav_row.append(InlineKeyboardButton("▶️", callback_data=f"cal_month_{next_year}_{next_month:02d}"))
    kb.append(nav_row)

    # Дни недели
    kb.append([
        InlineKeyboardButton("Пн", callback_data="cal_ignore"),
        InlineKeyboardButton("Вт", callback_data="cal_ignore"),
        InlineKeyboardButton("Ср", callback_data="cal_ignore"),
        InlineKeyboardButton("Чт", callback_data="cal_ignore"),
        InlineKeyboardButton("Пт", callback_data="cal_ignore"),
        InlineKeyboardButton("Сб", callback_data="cal_ignore"),
        InlineKeyboardButton("Вс", callback_data="cal_ignore"),
    ])

    # Недели месяца
    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
            elif day_avail.get(day, False):
                # Сегодня — выделяем
                if day == now.day and month == now.month and year == now.year:
                    row.append(InlineKeyboardButton(f"📍{day}", callback_data=f"cal_day_{year}-{month:02d}-{day:02d}"))
                else:
                    row.append(InlineKeyboardButton(str(day), callback_data=f"cal_day_{year}-{month:02d}-{day:02d}"))
            else:
                row.append(InlineKeyboardButton("·", callback_data="cal_ignore"))
        kb.append(row)

    # Кнопка назад
    if await _is_coworking_org() or master_name == _COWORKING_RESOURCE:
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    else:
        kb.append([InlineKeyboardButton("◀️ К мастерам", callback_data="back_main")])

    return text, InlineKeyboardMarkup(kb)


async def _build_slots_kb(master_name: str, date_str: str, selected: set | None = None,
                          duration_minutes: int = 0) -> tuple:
    """Сетка слотов. В ков.: toggle-выбор + кнопка брони; beauty: одиночный клик."""
    now = datetime.now()
    d = datetime.strptime(date_str, "%Y-%m-%d")
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    day_name = days_ru[d.weekday()]
    month_name = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря"
    ][d.month]

    # Коворкинг всегда 0 (мультивыбор слотами); beauty — длительность услуги
    is_cow_probe = await _is_coworking_org() or master_name == _COWORKING_RESOURCE
    eff_dur = 0 if is_cow_probe else duration_minutes
    avail = await db.get_master_available_hours(master_name, date_str, duration_minutes=eff_dur)
    if date_str == now.strftime("%Y-%m-%d"):
        now_str = now.strftime("%H:%M")
        avail = [t for t in avail if t > now_str]

    if not avail:
        return (
            f"📅 *{d.day} {month_name} ({day_name})*\n\n"
            f"Нет свободного времени на эту дату.",
            InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ К календарю", callback_data=f"cal_back_{d.year}_{d.month:02d}")]
            ])
        )

    is_cow = is_cow_probe
    selected = selected or set()
    # отфильтровать выбранное, что больше не avail
    selected = {s for s in selected if s in set(avail)}

    if is_cow:
        n = len(selected)
        if n:
            s_min = min(selected)
            # конец = последний выбранный + 15 мин
            sh, sm = map(int, s_min.split(":"))
            last = max(selected)
            lh, lm = map(int, last.split(":"))
            lm += 15
            if lm >= 60:
                lh += 1
                lm = 0
            end_label = f"{lh:02d}:{lm:02d}"
            # длительность
            total = n * 15
            hours, mins = divmod(total, 60)
            dur = f"{hours} ч" if mins == 0 else f"{hours} ч {mins} мин"
            text = (
                f"📅 *{d.day} {month_name} ({day_name})*\n"
                f"✅ Выбрано: *{s_min} – {end_label}* ({dur}, {n} сл.)\n"
                f"Кликайте слоты, чтобы выбрать/снять.\n"
                f"Когда готово — жмите кнопку ниже:"
            )
        else:
            text = (
                f"📅 *{d.day} {month_name} ({day_name})*\n"
                f"⏰ Отметьте нужные слоты (кликом), затем «Забронировать»:"
            )
        cb_prefix = "book_tgl_"
    else:
        text = f"📅 *{d.day} {month_name} ({day_name})*\n⏰ Выберите время:"
        if eff_dur > 15:
            text += f"\n⏱ Запись займёт *{db.format_duration(eff_dur)}* — доступны только подходящие старта:"
        cb_prefix = "book_slot_"

    kb = []
    row = []
    for slot in avail:
        if is_cow and slot in selected:
            label = f"✅ {slot}"
        else:
            label = slot
        row.append(InlineKeyboardButton(label, callback_data=f"{cb_prefix}{date_str}_{slot}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)

    if is_cow and selected:
        s_min = min(selected)
        last = max(selected)
        lh, lm = map(int, last.split(":"))
        lm += 15
        if lm >= 60:
            lh += 1
            lm = 0
        end_label = f"{lh:02d}:{lm:02d}"
        kb.append([InlineKeyboardButton(
            f"🔒 Забронировать: {s_min}–{end_label} ({len(selected)})",
            callback_data="book_commit",
        )])
    elif is_cow:
        kb.append([InlineKeyboardButton("🔒 Забронировать", callback_data="book_commit_nop")])

    kb.append([InlineKeyboardButton("◀️ К календарю", callback_data=f"cal_back_{d.year}_{d.month:02d}")])
    return text, InlineKeyboardMarkup(kb)


async def book_select_master(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    m_id = int(query.data.replace("book_m_", ""))
    ctx.user_data["booking"]["master_id"] = m_id
    masters = await db.get_masters()
    master = next((m for m in masters if m["id"] == m_id), None)
    ctx.user_data["booking"]["master_name"] = master["name"] if master else "—"
    now = datetime.now()
    text, kb = await _build_calendar_kb(
        ctx.user_data["booking"]["master_name"], now.year, now.month,
        duration_minutes=ctx.user_data["booking"].get("duration_minutes") or 0,
    )
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return BOOK_SELECT_DATE


async def book_cal_month(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Навигация по месяцам календаря."""
    query = update.callback_query
    await query.answer()
    parts = query.data.replace("cal_month_", "").split("_")
    year, month = int(parts[0]), int(parts[1])
    master_name = ctx.user_data["booking"].get("master_name", "")
    text, kb = await _build_calendar_kb(
        master_name, year, month,
        duration_minutes=ctx.user_data["booking"].get("duration_minutes") or 0,
    )
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass
    return BOOK_SELECT_DATE


async def book_cal_day(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Выбор даты — показать слоты времени."""
    query = update.callback_query
    await query.answer()
    date_str = query.data.replace("cal_day_", "")
    master_name = ctx.user_data["booking"].get("master_name", "")
    ctx.user_data["cal_date"] = date_str
    booking = ctx.user_data.setdefault("booking", {})
    booking["date"] = date_str
    booking["selected_slots"] = set()
    booking.pop("start_time", None)
    booking.pop("end_time", None)
    booking.pop("time", None)
    text, kb = await _build_slots_kb(
        master_name, date_str, booking.get("selected_slots"),
        duration_minutes=booking.get("duration_minutes") or 0,
    )
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass
    return BOOK_SELECT_DATE


async def book_cal_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Вернуться к календарю из слотов."""
    query = update.callback_query
    await query.answer()
    parts = query.data.replace("cal_back_", "").split("_")
    year, month = int(parts[0]), int(parts[1])
    booking = ctx.user_data.setdefault("booking", {})
    booking.pop("selected_slots", None)
    booking.pop("start_time", None)
    booking.pop("end_time", None)
    booking.pop("time", None)
    master_name = booking.get("master_name", "")
    text, kb = await _build_calendar_kb(
        master_name, year, month,
        duration_minutes=booking.get("duration_minutes") or 0,
    )
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass
    return BOOK_SELECT_DATE


async def book_cal_slot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Выбор одиночного слота (beauty)."""
    query = update.callback_query
    await query.answer()
    parts = query.data.replace("book_slot_", "").split("_")
    if len(parts) < 2:
        log.warning(f"BOOK: некорректный callback слота: {query.data}")
        return BOOK_SELECT_DATE
    booking = ctx.user_data["booking"]
    booking["date"] = parts[0]
    booking["time"] = parts[1]
    booking.pop("start_time", None)
    booking.pop("end_time", None)
    booking.pop("selected_slots", None)
    client = await ensure_client(update, ctx)
    local = await db.get_client(update.effective_user.id)
    has_phone = local and local.get("phone", "") not in ("", "не указан")
    if not has_phone:
        await query.edit_message_text("Сначала укажите номер телефона.")
        return await send_phone_request(update, ctx, PHONE_INPUT)
    dur = booking.get("duration_minutes") or 0
    if dur > 15:
        end = db.end_time_for_booking(parts[1], dur)
        return await _show_book_confirm(
            query, ctx, booking,
            range_text=f"{parts[1]} – {end}",
            duration=db.format_duration(dur),
            slot_count=db.slots_needed(dur),
        )
    return await _show_book_confirm(query, ctx, booking)


async def book_toggle_slot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ков.: вкл/выкл слот в выборе (подсветка ✅)."""
    query = update.callback_query
    await query.answer()
    data = query.data.replace("book_tgl_", "")
    parts = data.split("_", 1)
    if len(parts) < 2:
        return BOOK_SELECT_DATE
    date_str, slot = parts[0], parts[1]
    booking = ctx.user_data.setdefault("booking", {})
    booking["date"] = date_str
    selected: set = booking.get("selected_slots") or set()
    if slot in selected:
        selected.discard(slot)
    else:
        selected.add(slot)
    booking["selected_slots"] = selected
    booking.pop("start_time", None)
    booking.pop("end_time", None)
    booking["time"] = slot

    master_name = booking.get("master_name", _COWORKING_RESOURCE)
    text, kb = await _build_slots_kb(
        master_name, date_str, selected,
        duration_minutes=booking.get("duration_minutes") or 0,
    )
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        log.warning(f"BOOK: toggle edit failed: {e}")
    return BOOK_SELECT_DATE


async def book_commit_nop(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ков.: нажали «Забронировать» без выбранных слотов."""
    query = update.callback_query
    await query.answer("Сначала отметьте время", show_alert=True)
    return BOOK_SELECT_DATE


async def book_commit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ков.: зафиксировать выбранные слоты → confirm."""
    query = update.callback_query
    await query.answer()
    booking = ctx.user_data.setdefault("booking", {})
    selected: set = set(booking.get("selected_slots") or set())
    if not selected:
        await query.answer("Сначала отметьте время", show_alert=True)
        return BOOK_SELECT_DATE

    slots = sorted(selected)
    # непрерывность с шагом 15 мин
    def _to_min(t: str) -> int:
        h, m = map(int, t.split(":"))
        return h * 60 + m
    minutes = [_to_min(s) for s in slots]
    for a, b in zip(minutes, minutes[1:]):
        if b - a != 15:
            await query.edit_message_text(
                "😔 Слоты должны идти подряд без разрывов.\n"
                "Снимите лишние или выберите сплошной диапазон.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ К календарю", callback_data=f"cal_day_{booking.get('date', '')}")]
                ]),
            )
            booking["selected_slots"] = set()
            return BOOK_SELECT_DATE

    start_time = slots[0]
    last = slots[-1]
    lh, lm = map(int, last.split(":"))
    lm += 15
    if lm >= 60:
        lh += 1
        lm = 0
    end_time = f"{lh:02d}:{lm:02d}"
    booking["start_time"] = start_time
    booking["end_time"] = end_time
    booking["time"] = start_time

    slots_list = db.slots_between(start_time, end_time)
    total = len(slots_list) * 15
    hours, mins = divmod(total, 60)
    dur = f"{hours} ч" if mins == 0 else f"{hours} ч {mins} мин"

    # все ли свободны
    master_name = booking.get("master_name", _COWORKING_RESOURCE)
    avail = await db.get_master_available_hours(master_name, booking.get("date", ""))
    avail_set = set(avail)
    missing = [s for s in slots_list if s not in avail_set and s != end_time]
    # end_time может отсутствовать в avail (это граница) — проверяем только слоты брони
    missing = [s for s in slots_list if s not in avail_set]
    if missing:
        await query.edit_message_text(
            f"😔 Часть времени уже занята ({missing[0]}).",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ К дате", callback_data=f"cal_day_{booking.get('date', '')}")]
            ]),
        )
        booking["selected_slots"] = set()
        return BOOK_SELECT_DATE

    client = await ensure_client(update, ctx)
    local = await db.get_client(update.effective_user.id)
    has_phone = local and local.get("phone", "") not in ("", "не указан")
    if not has_phone:
        await query.edit_message_text("Сначала укажите номер телефона.")
        return await send_phone_request(update, ctx, PHONE_INPUT)

    return await _show_book_confirm(
        query, ctx, booking,
        range_text=f"{start_time} – {end_time}",
        duration=dur,
        slot_count=len(slots_list),
    )


async def _show_book_confirm(query, ctx, booking, range_text: str | None = None, duration: str | None = None, slot_count: int | None = None):
    """Экран подтверждения записи/брони (телефон проверяется до вызова)."""
    is_cow = await _is_coworking_org()
    if booking.get("master_name") == _COWORKING_RESOURCE or is_cow:
        org_line = f"Пространство: {booking.get('master_name', _COWORKING_RESOURCE)}\n"
    else:
        org_line = f"Мастер: {booking.get('master_name', '—')}\n"
    title = "Подтвердите бронь:" if is_cow else "Подтвердите запись:"
    btn_yes = "✅ Да, забронировать" if is_cow else "✅ Да, записаться"
    time_line = range_text or booking.get("time", "—")
    extra = ""
    if duration and slot_count is not None:
        extra = f" ({duration}, {slot_count} слотов)"
    text = (
        f"📋 *{title}*\n\n"
        f"Услуга: {booking.get('service_name', '—')}\n"
        f"Цена: {booking.get('service_price', '—')}\n"
        f"{org_line}"
        f"Дата: {booking.get('date', '—')}\n"
        f"Время: {time_line}{extra}\n\n"
        f"Всё верно?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(btn_yes, callback_data="book_confirm_yes")],
        [InlineKeyboardButton("❌ Отмена", callback_data="back_main")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return BOOK_CONFIRM


async def book_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log.info(f"BOOK: confirm called, data={query.data}")
    if "yes" not in query.data:
        if await _is_coworking_org():
            await query.edit_message_text("Бронь отменена.", reply_markup=await main_menu_kb())
        else:
            await query.edit_message_text("Запись отменена.", reply_markup=await main_menu_kb())
        return MAIN_MENU

    # Проверяем контакт клиента
    client = await ensure_client(update, ctx)
    client_data = await db.get_client(update.effective_user.id)
    has_phone = client_data and client_data.get("phone", "")

    if not has_phone:
        kb = ReplyKeyboardMarkup(
            [[KeyboardButton("📱 Поделиться номером", request_contact=True)]],
            resize_keyboard=True, one_time_keyboard=True,
        )
        await query.message.reply_text(
            "📱 Чтобы завершить запись, поделитесь номером телефона:",
            reply_markup=kb,
        )
        return PHONE_INPUT

    # Проверяем имя
    name = client_data.get("name", "") if client_data else ""
    if not name:
        await query.message.reply_text(
            "Как вас зовут? (имя для записи):"
        )
        return BOOK_ASK_NAME

    # Создаём запись
    return await _create_booking(update, ctx)


async def book_ask_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2:
        await update.message.reply_text("Введите имя (минимум 2 символа):")
        return BOOK_ASK_NAME
    client = await ensure_client(update, ctx)
    await db.update_client_name(update.effective_user.id, name)
    return await _create_booking(update, ctx)


async def _create_booking(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    booking = ctx.user_data.get("booking", {})
    is_edit = ctx.user_data.pop("edit_old_booking_id", None)
    log.info(f"BOOK: _create_booking called, booking={booking}, is_edit={is_edit}")
    client = await ensure_client(update, ctx)
    client_data = await db.get_client(update.effective_user.id)
    name = (client_data.get("name", "") if client_data else "") or update.effective_user.full_name or ""
    phone = (client_data.get("phone", "") if client_data else "") or "не указан"

    master_name = booking.get("master_name", "—")
    manage_link = ""

    # При изменении — удаляем старую запись
    old_booking_info = ""
    if is_edit:
        old = await db.get_booking_by_id(is_edit)
        if old:
            old_booking_info = f"{old.get('master_name', '—')} | {old.get('date', '')} {old.get('time', '')}"
        await db.cancel_booking(is_edit)
        log.info(f"BOOK EDIT: deleted old booking #{is_edit}")

    # Сохраняем запись локально
    if booking.get("end_time") and booking.get("start_time"):
        count = await db.book_range(
            master_name=master_name,
            date=booking.get("date", ""),
            start_time=booking["start_time"],
            end_time=booking["end_time"],
            client_name=name,
            telegram_id=update.effective_user.id,
            service_name=booking.get("service_name", ""),
        )
        booking_id = 1 if count else None  # truthy для общего path
        log.info(f"BOOK: range saved, slots={count}")
        range_slots = count
    else:
        booking_id = await db.try_book_slot(
            master_name=master_name,
            date=booking.get("date", ""),
            time=booking.get("time", ""),
            client_name=name,
            telegram_id=update.effective_user.id,
            service_name=booking.get("service_name", ""),
            duration_minutes=booking.get("duration_minutes") or 0,
        )
        range_slots = db.slots_needed(booking.get("duration_minutes") or 0) if booking_id else 0
        log.info(f"BOOK: booking saved, booking_id={booking_id}")
        # multi-service join rows
        if booking_id and booking.get("service_ids"):
            ids = booking.get("service_ids") or []
            svcs = await db.resolve_services_by_ids(ids)
            if svcs:
                await db.set_booking_services(booking_id, [
                    {
                        "service_id": s["id"],
                        "name": s["name"],
                        "price": s.get("price") or "",
                        "duration_minutes": s.get("duration_minutes") or 0,
                    }
                    for s in svcs
                ])
        # self-service manage link (D1)
        if booking_id and booking_id != 1:
            try:
                import hashlib as _hl
                import hmac as _hm
                secret = os.getenv("CRM_SECRET", "")
                if secret:
                    msg = f"manage:{booking_id}".encode()
                    tok = _hm.new(secret.encode(), msg, _hl.sha256).hexdigest()[:32]
                    base_url = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
                    manage_link = f"\n\n🔗 Управление: {base_url}/manage-booking?id={booking_id}&token={tok}"
            except Exception:
                manage_link = ""

    # Автоподтверждение если запись менее чем за 24 часа
    if booking_id:
        from datetime import datetime as dt
        booking_date = booking.get("date", "")
        booking_time = booking.get("start_time") or booking.get("time", "")
        if booking_date and booking_time:
            hours_until = 999
            try:
                booking_dt = dt.strptime(f"{booking_date} {booking_time}", "%Y-%m-%d %H:%M")
                hours_until = (booking_dt - dt.now()).total_seconds() / 3600
                if hours_until < 24:
                    if booking.get("end_time") and booking.get("start_time"):
                        import aiosqlite
                        async with aiosqlite.connect(config.DB_PATH) as adb:
                            await adb.execute(
                                "UPDATE bookings SET confirmed=1 WHERE master_name=? AND date=? AND time>=? AND time<?",
                                (master_name, booking["date"], booking["start_time"], booking["end_time"]),
                            )
                            await adb.commit()
                    else:
                        await db.confirm_booking(booking_id)
                    log.info(f"BOOK: auto-confirmed booking ({hours_until:.1f}h until)")
            except Exception as e:
                log.warning(f"BOOK: auto-confirm error: {e}")

    # Проверяем, что запись действительно создана
    if not booking_id:
        chat_id = update.effective_chat.id
        log.warning(f"BOOK: slot already taken for {master_name} {booking.get('date')} {booking.get('time')}")
        try:
            await ctx.bot.send_message(chat_id, " ", reply_markup=ReplyKeyboardRemove())
        except Exception:
            pass
        await ctx.bot.send_message(
            chat_id,
            "😔 К сожалению, этот слот только что занял другой клиент.\n"
            "Пожалуйста, выберите другое время.",
            reply_markup=await main_menu_kb(),
        )
        return MAIN_MENU

    # Промотируем лида в клиенты
    await db.promote_to_client(update.effective_user.id)

    # Уведомляем администратора
    bot = ctx.bot
    for admin_id in config.ADMIN_IDS:
        try:
            if is_edit:
                await bot.send_message(
                    admin_id,
                    f"✏️ *Запись изменена!*\n\n"
                    f"Клиент: {name}\n"
                    f"Было: {old_booking_info}\n"
                    f"Стало: {master_name} | {booking.get('date', '—')} {booking.get('time', '—')}\n"
                    f"Услуга: {booking.get('service_name', '—')}",
                    parse_mode=ParseMode.MARKDOWN,
                )
            else:
                role_label = "Пространство" if (await _is_coworking_org() or master_name == _COWORKING_RESOURCE) else "Мастер"
                if booking.get("end_time"):
                    time_line = f"{booking.get('start_time', '—')} – {booking.get('end_time', booking.get('time', '—'))}"
                elif (booking.get("duration_minutes") or 0) > 15:
                    start_t = booking.get("time", "—")
                    time_line = f"{start_t} – {db.end_time_for_booking(start_t, booking['duration_minutes'])} ({db.format_duration(booking['duration_minutes'])})"
                else:
                    time_line = booking.get("time", "—")
                await bot.send_message(
                    admin_id,
                    f"📅 *Новая {'бронь' if role_label == 'Пространство' else 'запись'}!*\n\n"
                    f"Клиент: {name}\n"
                    f"Телефон: {phone}\n"
                    f"Услуга: {booking.get('service_name', '—')}\n"
                    f"Цена: {booking.get('service_price', '—')}\n"
                    f"{role_label}: {master_name}\n"
                    f"Дата: {booking.get('date', '—')}\n"
                    f"Время: {time_line}",
                    parse_mode=ParseMode.MARKDOWN,
                )
        except Exception as e:
            log.warning(f"Не удалось уведомить админа {admin_id}: {e}")

    # Убираем клавиатуру с контактом и отправляем подтверждение
    chat_id = update.effective_chat.id
    log.info(f"BOOK: sending confirmation to chat_id={chat_id}")
    try:
        await bot.send_message(chat_id, " ", reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass

    if is_edit:
        await bot.send_message(
            chat_id,
            "✅ *Запись изменена!*\n\n"
            f"Было: {old_booking_info}\n"
            f"Стало: {master_name} | {booking.get('date', '—')} {booking.get('time', '—')}\n\n"
            "Мы свяжемся с вами для подтверждения.",
            reply_markup=await main_menu_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
    elif await _is_coworking_org() or master_name == _COWORKING_RESOURCE:
        time_line = (
            f"{booking.get('start_time', '—')} – {booking.get('end_time', booking.get('time', '—'))}"
            if booking.get("end_time")
            else booking.get("time", "—")
        )
        await bot.send_message(
            chat_id,
            "✅ *Бронь создана!*\n\n"
            f"Пространство: {master_name}\n"
            f"Дата: {booking.get('date', '—')}\n"
            f"Время: {time_line}\n"
            f"Услуга: {booking.get('service_name', '—')}\n\n"
            "Администратор подтвердит бронь.",
            reply_markup=await main_menu_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        success_time = booking.get("time", "—")
        if (booking.get("duration_minutes") or 0) > 15 and booking.get("time"):
            success_time = (
                f"{booking['time']} – {db.end_time_for_booking(booking['time'], booking['duration_minutes'])} "
                f"({db.format_duration(booking['duration_minutes'])})"
            )
        await bot.send_message(
            chat_id,
            "✅ *Запись создана!*\n\n"
            f"Время: {success_time}\n"
            "Мы свяжемся с вами для подтверждения.\n"
            "Спасибо, что выбираете нас!"
            f"{manage_link}",
            reply_markup=await main_menu_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
    log.info(f"BOOK: confirmation sent successfully")
    return MAIN_MENU


# ══════════════════════════════════════════════════════════
#  Клиент: Мои записи
# ══════════════════════════════════════════════════════════

async def cb_waitlist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Клиент хочет в лист ожидания на свободное окно."""
    query = update.callback_query
    await query.answer()
    ctx.user_data["waitlist"] = {}
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👩 Любой мастер", callback_data="wl_master_any")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text(
        "⏳ *Лист ожидания*\n\nСообщим, когда освободится окно.\nВыберите мастера:",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )
    return WAITLIST


async def cb_waitlist_master(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.replace("wl_master_", "")
    wl = ctx.user_data.setdefault("waitlist", {})
    if data == "any":
        wl["master_name"] = ""
        wl["master_label"] = "Любой"
    else:
        # book_m_{id} reuse — not used here
        wl["master_name"] = data
        wl["master_label"] = data
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 На ближайший день", callback_data="wl_date_asap")],
        [InlineKeyboardButton("📅 Без даты (любой день)", callback_data="wl_date_any")],
        [InlineKeyboardButton("◀️ Назад", callback_data="menu_waitlist")],
    ])
    await query.edit_message_text(
        f"Мастер: {wl['master_label']}\nКогда ищем окно?",
        reply_markup=kb,
    )
    return WAITLIST


async def cb_waitlist_date(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    wl = ctx.user_data.setdefault("waitlist", {})
    if query.data == "wl_date_asap":
        wl["date_pref"] = datetime.now().strftime("%Y-%m-%d")
    else:
        wl["date_pref"] = ""
    client = await ensure_client(update, ctx)
    local = await db.get_client(update.effective_user.id)
    phone = (local or {}).get("phone", "")
    wid = await db.add_waitlist(
        master_name=wl.get("master_name", ""),
        date_pref=wl.get("date_pref", ""),
        service_name="",
        telegram_id=update.effective_user.id,
        phone=phone or "",
        duration_minutes=0,
    )
    await query.edit_message_text(
        f"✅ Вы в листе ожидания (#{wid}).\n"
        f"Мастер: {wl.get('master_label', 'Любой')}\n"
        f"Дата: {wl.get('date_pref') or 'любая'}\n\n"
        f"Напишем, когда освободится окно.",
        reply_markup=await main_menu_kb(),
    )
    return MAIN_MENU


async def cb_my_bookings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    client = await ensure_client(update, ctx)
    bookings = await db.get_bookings_by_telegram_id(update.effective_user.id)
    if not bookings:
        text = "У вас пока нет записей."
    else:
        lines = ["📋 *Ваши записи:*\n"]
        for b in bookings[:10]:
            status = "✅ Подтверждено" if b.get("confirmed") else "⏳ Ожидает"
            lines.append(f"• {b.get('master_name', '—')} | {b.get('date', '')} {b.get('time', '')} — {status}")
        text = "\n".join(lines)
    await query.edit_message_text(text, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
    return MAIN_MENU


# ══════════════════════════════════════════════════════════
#  Клиент: Изменить запись
# ══════════════════════════════════════════════════════════

async def cb_edit_booking(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать активные записи клиента для изменения."""
    query = update.callback_query
    await query.answer()
    client = await ensure_client(update, ctx)
    bookings = await db.get_active_bookings(update.effective_user.id)
    if not bookings:
        await query.edit_message_text(
            "У вас нет активных записей для изменения.",
            reply_markup=back_btn(),
        )
        return MAIN_MENU
    kb = []
    for b in bookings[:10]:
        label = f"{b.get('master_name', '—')} | {b.get('date', '')} {b.get('time', '')}"
        kb.append([InlineKeyboardButton(label, callback_data=f"edit_pick_{b['id']}")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    await query.edit_message_text(
        "✏️ *Выберите запись для изменения:*",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode=ParseMode.MARKDOWN,
    )
    return EDIT_SELECT_BOOKING


async def cb_edit_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Выбрана запись — проверить 2ч и запустить флоу изменения."""
    query = update.callback_query
    await query.answer()
    booking_id = int(query.data.replace("edit_pick_", ""))

    can = await db.can_modify_booking(booking_id)
    if not can:
        await query.edit_message_text(
            "⛔ Нельзя изменить запись менее чем за 2 часа до визита.\n\n"
            "Свяжитесь с салоном для изменений.",
            reply_markup=back_btn(),
        )
        return MAIN_MENU

    ctx.user_data["edit_old_booking_id"] = booking_id
    ctx.user_data["booking"] = {}

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👩 Женщине", callback_data="gender_f")],
        [InlineKeyboardButton("👨 Мужчине", callback_data="gender_m")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text("Кому записываемся?", reply_markup=kb)
    return BOOK_SELECT_GENDER


# ══════════════════════════════════════════════════════════
#  Мастер: Коворкинг (блокировка времени)
# ══════════════════════════════════════════════════════════

async def cb_cal_ignore(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Пустые/недоступные кнопки календаря — просто гасим спиннер."""
    query = update.callback_query
    await query.answer()


async def cb_coworking(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Кнопка 'Коворкинг' — только в режиме coworking."""
    query = update.callback_query
    await query.answer()
    if not await _is_coworking_org():
        await query.answer(
            "Доступно только в режиме «Ковopкинг» (Настройки → Режим работы)",
            show_alert=True,
        )
        return MAIN_MENU
    telegram_id = update.effective_user.id
    master = await db.get_master_by_tg_id(telegram_id)
    if master:
        master_name = master["name"]
    elif telegram_id in config.ADMIN_IDS:
        master_name = "АДМИН"
    else:
        await query.answer("Эта функция доступна только для мастеров", show_alert=True)
        return MAIN_MENU

    ctx.user_data["coworking"] = {"master_name": master_name}
    now = datetime.now()
    kb = await _build_coworking_calendar_kb(master_name, now.year, now.month)
    text = f"🔒 *Коворкинг — {master_name}*\n\nВыберите дату:"
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return COWORKING_SELECT_DATE


async def _build_coworking_calendar_kb(master_name: str, year: int = None, month: int = None):
    """Построить календарь для коворкинга (с cow_ префиксом)."""
    now = datetime.now()
    if year is None:
        year = now.year
    if month is None:
        month = now.month

    schedule = await db.get_master_schedule(master_name)
    off_days = {s["day_of_week"] for s in schedule if s.get("is_day_off")}
    sched_map = {}
    for s in schedule:
        dow = s["day_of_week"]
        sel = s.get("selected_hours", "")
        if sel:
            sched_map[dow] = [h.strip() for h in sel.split(",") if h.strip()]
        else:
            sh = int(s["start_time"].split(":")[0])
            eh = int(s["end_time"].split(":")[0])
            slots = []
            for h in range(sh, eh):
                for m in (0, 15, 30, 45):
                    slots.append(f"{h:02d}:{m:02d}")
            sched_map[dow] = slots
    for d in range(7):
        if d not in sched_map and d not in off_days:
            sched_map[d] = db.get_salon_slots(d)
    for d in sched_map:
        sched_map[d] = db._clamp_to_salon(sched_map[d], d)

    cal = calendar.monthcalendar(year, month)
    month_name = [
        "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
        "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
    ][month]

    dates_in_month = []
    for week in cal:
        for day in week:
            if day != 0:
                d_obj = datetime(year, month, day)
                if d_obj >= now.replace(hour=0, minute=0, second=0, microsecond=0):
                    dates_in_month.append(d_obj.strftime("%Y-%m-%d"))

    date_schedules = {}
    if dates_in_month:
        async with aiosqlite.connect(config.DB_PATH) as adb:
            ph = ",".join("?" * len(dates_in_month))
            cur = await adb.execute(
                f"SELECT date, time_slots, is_day_off FROM master_date_schedule WHERE master_name = ? AND date IN ({ph})",
                [master_name] + dates_in_month,
            )
            for r in await cur.fetchall():
                date_schedules[r[0]] = {"time_slots": r[1] or "", "is_day_off": r[2]}

    # Коворкинг: отдельный календарь — длительность услуги не применяется (мультивыбор)
    booked_counts = {}
    if dates_in_month:
        async with aiosqlite.connect(config.DB_PATH) as adb:
            ph = ",".join("?" * len(dates_in_month))
            cur = await adb.execute(
                f"SELECT date, COUNT(*) FROM bookings WHERE master_name = ? AND date IN ({ph}) GROUP BY date",
                [master_name] + dates_in_month,
            )
            booked_counts = {r[0]: r[1] for r in await cur.fetchall()}

    day_avail = {}
    for week in cal:
        for day in week:
            if day == 0:
                continue
            d_obj = datetime(year, month, day)
            ds = d_obj.strftime("%Y-%m-%d")
            dow = d_obj.weekday()
            if d_obj < now.replace(hour=0, minute=0, second=0, microsecond=0):
                day_avail[day] = False
                continue
            ds_entry = date_schedules.get(ds)
            if ds_entry:
                if ds_entry["is_day_off"]:
                    day_avail[day] = False
                    continue
                slots_str = ds_entry["time_slots"]
                all_slots = [h.strip() for h in slots_str.split(",") if h.strip()] if slots_str else []
            else:
                if dow in off_days:
                    day_avail[day] = False
                    continue
                all_slots = sched_map.get(dow, [])
            booked_count = booked_counts.get(ds, 0)
            if ds == now.strftime("%Y-%m-%d"):
                now_str = now.strftime("%H:%M")
                future_slots = [t for t in all_slots if t > now_str]
                day_avail[day] = len(future_slots) > booked_count
            else:
                day_avail[day] = len(all_slots) > booked_count

    kb = []
    nav_row = []
    prev_month = month - 1
    prev_year = year
    if prev_month < 1:
        prev_month = 12
        prev_year -= 1
    next_month = month + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year += 1
    if (prev_year > now.year) or (prev_year == now.year and prev_month >= now.month):
        nav_row.append(InlineKeyboardButton("◀️", callback_data=f"cow_cal_month_{prev_year}_{prev_month:02d}"))
    nav_row.append(InlineKeyboardButton(f"{month_name} {year}", callback_data="cal_ignore"))
    nav_row.append(InlineKeyboardButton("▶️", callback_data=f"cow_cal_month_{next_year}_{next_month:02d}"))
    kb.append(nav_row)

    kb.append([
        InlineKeyboardButton("Пн", callback_data="cal_ignore"),
        InlineKeyboardButton("Вт", callback_data="cal_ignore"),
        InlineKeyboardButton("Ср", callback_data="cal_ignore"),
        InlineKeyboardButton("Чт", callback_data="cal_ignore"),
        InlineKeyboardButton("Пт", callback_data="cal_ignore"),
        InlineKeyboardButton("Сб", callback_data="cal_ignore"),
        InlineKeyboardButton("Вс", callback_data="cal_ignore"),
    ])

    for week in cal:
        row = []
        for day in week:
            if day == 0:
                row.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
            elif day_avail.get(day, False):
                if day == now.day and month == now.month and year == now.year:
                    row.append(InlineKeyboardButton(f"📍{day}", callback_data=f"cow_cal_day_{year}-{month:02d}-{day:02d}"))
                else:
                    row.append(InlineKeyboardButton(str(day), callback_data=f"cow_cal_day_{year}-{month:02d}-{day:02d}"))
            else:
                row.append(InlineKeyboardButton("·", callback_data="cal_ignore"))
        kb.append(row)

    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(kb)


async def cow_cal_month(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Навигация по месяцам в календаре коворкинга."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    year = int(parts[3])
    month = int(parts[4])
    master_name = ctx.user_data["coworking"]["master_name"]
    kb = await _build_coworking_calendar_kb(master_name, year, month)
    text = f"🔒 *Коворкинг — {master_name}*\n\nВыберите дату:"
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return COWORKING_SELECT_DATE


async def cow_cal_day(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Мастер выбрал дату — показать свободные слоты для выбора начала."""
    query = update.callback_query
    await query.answer()
    date_str = query.data.replace("cow_cal_day_", "")
    ctx.user_data["coworking"]["date"] = date_str
    master_name = ctx.user_data["coworking"]["master_name"]

    now = datetime.now()
    d = datetime.strptime(date_str, "%Y-%m-%d")
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    day_name = days_ru[d.weekday()]
    month_name = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря"
    ][d.month]

    avail = await db.get_master_available_hours(master_name, date_str)
    if date_str == now.strftime("%Y-%m-%d"):
        now_str = now.strftime("%H:%M")
        avail = [t for t in avail if t > now_str]

    if not avail:
        text = f"🔒 *{d.day} {month_name} ({day_name})*\n\nНет свободного времени на эту дату."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ К календарю", callback_data=f"cow_cal_back_{d.year}_{d.month:02d}")]
        ])
        await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        return COWORKING_SELECT_DATE

    text = f"🔒 *{d.day} {month_name} ({day_name})*\n⏰ Выберите **начало** коворкинга:"
    kb = []
    row = []
    for slot in avail:
        row.append(InlineKeyboardButton(slot, callback_data=f"cow_start_{date_str}_{slot}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton("◀️ К календарю", callback_data=f"cow_cal_back_{d.year}_{d.month:02d}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    return COWORKING_SELECT_START


async def cow_cal_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Возврат к календарю коворкинга."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    year = int(parts[3])
    month = int(parts[4])
    master_name = ctx.user_data["coworking"]["master_name"]
    kb = await _build_coworking_calendar_kb(master_name, year, month)
    text = f"🔒 *Коворкинг — {master_name}*\n\nВыберите дату:"
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return COWORKING_SELECT_DATE


async def cow_select_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Мастер выбрал начало — показать слоты для выбора конца."""
    query = update.callback_query
    await query.answer()
    data = query.data.replace("cow_start_", "")
    parts = data.split("_", 1)
    date_str = parts[0]
    start_time = parts[1]
    ctx.user_data["coworking"]["start_time"] = start_time

    master_name = ctx.user_data["coworking"]["master_name"]
    avail = await db.get_master_available_hours(master_name, date_str)
    end_slots = [s for s in avail if s > start_time]

    if not end_slots:
        end_slots = [start_time]

    now = datetime.now()
    d = datetime.strptime(date_str, "%Y-%m-%d")
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    day_name = days_ru[d.weekday()]
    month_name = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря"
    ][d.month]

    text = f"🔒 *{d.day} {month_name} ({day_name})*\nНачало: *{start_time}*\n\nВыберите **конец** коворкинга:"
    kb = []
    row = []
    for slot in end_slots:
        row.append(InlineKeyboardButton(slot, callback_data=f"cow_end_{date_str}_{slot}"))
        if len(row) == 3:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([InlineKeyboardButton("◀️ К началу", callback_data=f"cow_cal_day_{date_str}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    return COWORKING_SELECT_END


async def cow_select_end(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Мастер выбрал конец — показать подтверждение."""
    query = update.callback_query
    await query.answer()
    data = query.data.replace("cow_end_", "")
    parts = data.split("_", 1)
    date_str = parts[0]
    end_time = parts[1]
    ctx.user_data["coworking"]["end_time"] = end_time

    master_name = ctx.user_data["coworking"]["master_name"]
    start_time = ctx.user_data["coworking"]["start_time"]

    sh, sm = map(int, start_time.split(":"))
    eh, em = map(int, end_time.split(":"))
    total_minutes = (eh * 60 + em) - (sh * 60 + sm)
    slot_count = total_minutes // 15

    now = datetime.now()
    d = datetime.strptime(date_str, "%Y-%m-%d")
    days_ru = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    day_name = days_ru[d.weekday()]
    month_name = [
        "", "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря"
    ][d.month]

    hours = total_minutes // 60
    mins = total_minutes % 60
    duration_text = f"{hours} ч" if mins == 0 else f"{hours} ч {mins} мин"

    text = (
        f"🔒 *Подтверждение коворкинга*\n\n"
        f"📅 {d.day} {month_name} ({day_name})\n"
        f"⏰ {start_time} – {end_time}\n"
        f"⏱ {duration_text} ({slot_count} слотов)\n\n"
        f"Заблокировать это время?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Заблокировать", callback_data="cow_confirm")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cow_cancel")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return COWORKING_CONFIRM


async def cow_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Подтверждение — создать блокировки коворкинга."""
    query = update.callback_query
    await query.answer()
    if not await _is_coworking_org():
        await query.answer("Доступно только в режиме «Ковopкинг»", show_alert=True)
        return MAIN_MENU
    data = ctx.user_data.get("coworking", {})
    if not data:
        await query.edit_message_text("Ошибка. Начните заново.", reply_markup=back_btn())
        return MAIN_MENU

    count = await db.block_coworking(
        data["master_name"], data["date"], data["start_time"], data["end_time"]
    )

    try:
        for admin_id in config.ADMIN_IDS:
            await ctx.bot.send_message(
                admin_id,
                f"🔒 *Коворкинг*\n"
                f"Мастер: {data['master_name']}\n"
                f"Дата: {data['date']}\n"
                f"Время: {data['start_time']} – {data['end_time']}\n"
                f"Заблокировано слотов: {count}",
                parse_mode=ParseMode.MARKDOWN,
            )
    except Exception:
        pass

    text = (
        f"✅ *Коворкинг заблокирован!*\n\n"
        f"📅 {data['date']}\n"
        f"⏰ {data['start_time']} – {data['end_time']}\n"
        f"Заблокировано слотов: {count}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 Ещё коворкинг", callback_data="coworking")],
        [InlineKeyboardButton("◀️ Меню", callback_data="back_main")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    ctx.user_data.pop("coworking", None)
    return MAIN_MENU


async def cow_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Отмена коворкинга — вернуться в меню."""
    query = update.callback_query
    await query.answer()
    ctx.user_data.pop("coworking", None)
    await query.edit_message_text("Отменено.", reply_markup=back_btn())
    return MAIN_MENU


# ══════════════════════════════════════════════════════════
#  Клиент: История визитов
# ══════════════════════════════════════════════════════════

async def cb_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать историю визитов клиента."""
    query = update.callback_query
    await query.answer()
    bookings = await db.get_bookings_by_telegram_id(update.effective_user.id)
    # Показываем все записи (и подтверждённые, и ожидающие)
    if not bookings:
        if await _is_coworking_org():
            text = "📋 У вас пока нет броней.\n\nЗабронируйте слот и здесь появится история!"
        else:
            text = "📋 У вас пока нет визитов.\n\nЗапишитесь на процедуру и здесь появится история!"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(await _book_btn_label(), callback_data="menu_book")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
        ])
    else:
        if await _is_coworking_org():
            lines = ["📋 *Ваша история броней:*\n"]
        else:
            lines = ["📋 *Ваша история визитов:*\n"]
        for b in bookings[:10]:
            status = "✅" if b.get("confirmed") else "⏳"
            svc = b.get("service_name", "")
            svc_text = f" — {svc}" if svc else ""
            lines.append(f"{status} {b.get('date', '')} {b.get('time', '')} | {b.get('master_name', '—')}{svc_text}")
        text = "\n".join(lines)
        # Кнопка "Повторить последний"
        last = bookings[0]
        master = last.get("master_name", "")
        service = last.get("service_name", "")
        again = "🏢 Забронировать заново" if await _is_coworking_org() else "📅 Записаться заново"
        rebook_label = "🔄 Повторить последнюю бронь" if await _is_coworking_org() else "🔄 Повторить последний визит"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(rebook_label, callback_data=f"rebook_{master}")],
            [InlineKeyboardButton(again, callback_data="menu_book")],
            [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
        ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return MAIN_MENU


async def cb_rebook(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Повторная запись к тому же мастеру — открыть календарь."""
    query = update.callback_query
    await query.answer()
    master_name = query.data.replace("rebook_", "")
    ctx.user_data["booking"] = {"master_name": master_name}
    now = datetime.now()
    text, kb = await _build_calendar_kb(master_name, now.year, now.month, duration_minutes=0)
    try:
        await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        pass
    return BOOK_SELECT_DATE


# ══════════════════════════════════════════════════════════
#  Клиент: Оценка
# ══════════════════════════════════════════════════════════

async def cb_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log.info(f"RATE: cb_rate called, user={query.from_user.id}")
    try:
        client = await ensure_client(update, ctx)
        log.info(f"RATE: client={client}")
        bookings = await db.get_bookings_by_telegram_id(update.effective_user.id)
        log.info(f"RATE: bookings={len(bookings)}")
        if not bookings:
            await query.edit_message_text("Нет записей для оценки.", reply_markup=back_btn())
            return MAIN_MENU
        kb = []
        for b in bookings[:5]:
            label = f"{b.get('master_name', '—')} | {b.get('date', '')} {b.get('time', '')}"
            kb.append([InlineKeyboardButton(label, callback_data=f"rate_d_{b['id']}")])
        kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
        await query.edit_message_text("Выберите запись для оценки:", reply_markup=InlineKeyboardMarkup(kb))
        return RATE_SELECT_BOOKING
    except Exception as e:
        log.error(f"RATE: error: {e}")
        await query.edit_message_text("Произошла ошибка. Попробуйте /start", reply_markup=await main_menu_kb())
        return MAIN_MENU


async def rate_select_booking(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    deal_id = int(query.data.replace("rate_d_", ""))
    ctx.user_data["rate_deal_id"] = deal_id
    booking_row = await db.get_booking_by_id(deal_id)
    ctx.user_data["rate_master"] = booking_row.get("master_name", "") if booking_row else ""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'⭐' * i}", callback_data=f"rate_s_{i}")]
        for i in range(1, 6)
    ])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="back_main")])
    await query.edit_message_text("Поставьте оценку:", reply_markup=kb)
    return RATE_GIVE_SCORE


async def rate_give_score(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    score = int(query.data.replace("rate_s_", ""))
    ctx.user_data["rate_score"] = score
    if score <= 3:
        # Негативный отзыв — уведомляем админа
        client = await ensure_client(update, ctx)
        client_data = await db.get_client(update.effective_user.id)
        phone = client_data.get("phone", "не указан") if client_data else "не указан"
        for admin_id in config.ADMIN_IDS:
            try:
                await ctx.bot.send_message(
                    admin_id,
                    f"🚨 *Негативный отзыв!*\n\n"
                    f"Клиент: {update.effective_user.full_name}\n"
                    f"Телефон: {phone}\n"
                    f"Оценка: {'⭐' * score}\n"
                    f"Сделка: #{ctx.user_data['rate_deal_id']}\n\n"
                    f"⚠️ Рекомендуется связаться с клиентом!",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                pass
        await query.edit_message_text(
            "Нам очень жаль, что вам не понравилось.\n"
            "Администратор свяжется с вами для решения вопроса.\n"
            "Пожалуйста, оставьте комментарий, чтобы мы стали лучше:",
        )
        return RATE_COMMENT
    else:
        # Сохраняем положительный отзыв в БД
        await db.add_review(
            master_name=ctx.user_data.get("rate_master", ""),
            client_name=update.effective_user.full_name or "",
            score=score,
            comment="",
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Готово", callback_data="back_main")],
        ])
        await query.edit_message_text(
            "🎉 Спасибо, что выбираете нас!\n"
            "Рады, что вам понравилось!",
            reply_markup=kb,
        )
        return MAIN_MENU


async def rate_comment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    client = await ensure_client(update, ctx)
    comment = update.message.text
    score = ctx.user_data.get("rate_score", 0)
    deal_id = ctx.user_data.get("rate_deal_id", 0)
    # Сохраняем отзыв в локальную БД
    client_name = update.effective_user.full_name or ""
    # Получаем имя мастера из записи
    async with aiosqlite.connect(config.DB_PATH) as adb:
        adb.row_factory = aiosqlite.Row
        cur = await adb.execute("SELECT master_name FROM bookings WHERE id = ?", (deal_id,))
        row = await cur.fetchone()
        master_name = row["master_name"] if row else "—"
    await db.add_review(master_name, client_name, score, comment)
    await update.message.reply_text(
        "Спасибо за обратную связь!\nМы обязательно учтём ваш отзыв.",
        reply_markup=await main_menu_kb(),
    )
    return MAIN_MENU


# ══════════════════════════════════════════════════════════
#  Клиент: Скидки
# ══════════════════════════════════════════════════════════

async def cb_discount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    client = await ensure_client(update, ctx)
    discount = await db.get_discount(client["id"])
    visits = await db.get_visit_count(client["id"])
    text = (
        f"🎁 *Ваши скидки:*\n\n"
        f"Визитов: {visits}\n"
        f"Текущая скидка: {discount}%\n\n"
    )
    if discount > 0:
        text += f"Скидка {discount}% автоматически применена к вашей следующей записи!"
    else:
        text += "Скидка появится после 3 посещений."
    await query.edit_message_text(text, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
    return MAIN_MENU


# ══════════════════════════════════════════════════════════
#  Телефон
# ══════════════════════════════════════════════════════════

async def phone_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    import re
    contact_msg = update.message.contact
    if contact_msg:
        phone = contact_msg.phone_number
    else:
        phone = update.message.text.strip()
        # Валидация номера телефона
        if not re.match(r'^\+?\d{10,15}$', phone):
            await update.message.reply_text(
                "❌ Введите корректный номер телефона (например, +375291206101):"
            )
            return PHONE_INPUT
    client = await ensure_client(update, ctx)
    await db.update_client_phone(update.effective_user.id, phone)
    await update.message.reply_text(
        f"✅ Номер {phone} сохранён!",
        reply_markup=ReplyKeyboardRemove(),
    )
    # Если это запрос на консультацию — отправить уведомление
    if ctx.user_data.get("consultation_pending"):
        ctx.user_data.pop("consultation_pending", None)
        user = update.effective_user
        name = user.first_name or user.username or str(user.id)
        await _send_consultation(ctx, name, phone, user.username)
        await update.message.reply_text(
            "Спасибо за обращение, ближайшее время Вас проконсультируют.",
            reply_markup=await main_menu_kb(),
        )
        return MAIN_MENU
    # Проверяем имя
    client_data = await db.get_client(update.effective_user.id)
    name = client_data.get("name", "") if client_data else ""
    if not name:
        await update.message.reply_text("Как вас зовут? (имя для записи):")
        return BOOK_ASK_NAME
    # Если есть данные записи — продолжаем
    booking = ctx.user_data.get("booking")
    if booking and "date" in booking and "time" in booking:
        return await _create_booking(update, ctx)
    # Иначе — показываем главное меню
    if await _is_coworking_org():
        text = (
            "✨ Добро пожаловать!\n\n"
            "Я — бот коворкинга. Здесь вы можете:\n"
            "• Посмотреть тарифы\n"
            "• Выбрать пространство\n"
            "• Забронировать слот\n"
            "• Оценить обслуживание\n\n"
            "Выберите раздел:"
        )
    else:
        text = (
            "✨ Добро пожаловать!\n\n"
            "Я — бот салона красоты. Здесь вы можете:\n"
            "• Посмотреть услуги и цены\n"
            "• Узнать о наших мастерах\n"
            "• Записаться на процедуру\n"
            "• Оценить обслуживание\n\n"
            "Выберите раздел:"
        )
    await update.message.reply_text(text, reply_markup=await main_menu_kb())
    return MAIN_MENU


# ══════════════════════════════════════════════════════════
#  Админ-панель
# ══════════════════════════════════════════════════════════

async def cb_admin_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    log.info(f"ADMIN: cb_admin_menu called, user_id={user_id}, admin_ids={config.ADMIN_IDS}")
    if not is_admin(user_id):
        log.info(f"ADMIN: access denied for user_id={user_id}")
        await query.edit_message_text("⛔ Доступ запрещён.")
        return ConversationHandler.END
    log.info(f"ADMIN: access granted, showing menu")
    await query.edit_message_text("⚙️ *Админ-панель*\nВыберите раздел:", reply_markup=admin_menu_kb(), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


async def cb_admin_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать настройки функций из меню админа."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Доступ запрещён.")
        return ADMIN_MENU
    flags = await db.get_feature_flags()
    labels = db.FLAG_LABELS
    lines = ["⚙️ *Настройки функций:*\n"]
    kb = []
    for key, value in flags.items():
        if key == "ORG_TYPE":
            continue  # строковый флаг, не boolean-toggle
        icon = "✅" if value else "❌"
        label = labels.get(key, key)
        lines.append(f"{icon} {label}")
        toggle_text = "Выкл" if value else "Вкл"
        kb.append([InlineKeyboardButton(f"{icon} {label} → {toggle_text}", callback_data=f"set_{key}_{not value}")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


# ── Отладка: /debug_db ──
async def cmd_debug_db(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать состояние БД (только для админов)."""
    if not is_admin(update.effective_user.id):
        return
    masters = await db.get_masters()
    lines = [f"*Мастеров в БД: {len(masters)}*\n"]
    for m in masters:
        lines.append(f"• {m['name']} (id={m['id']}) — категории: `{m.get('categories', 'пусто')}`")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ── Настройки: /settings ──
async def cmd_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать настройки функций салона (только для админов)."""
    if not is_admin(update.effective_user.id):
        return
    flags = await db.get_feature_flags()
    labels = db.FLAG_LABELS
    lines = ["⚙️ *Настройки функций:*\n"]
    kb = []
    for key, value in flags.items():
        if key == "ORG_TYPE":
            continue  # строковый флаг, не boolean-toggle
        icon = "✅" if value else "❌"
        label = labels.get(key, key)
        lines.append(f"{icon} {label}")
        toggle_text = "Выкл" if value else "Вкл"
        kb.append([InlineKeyboardButton(f"{icon} {label} → {toggle_text}", callback_data=f"set_{key}_{not value}")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")])
    await update.message.reply_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


async def cb_toggle_setting(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Переключить настройку."""
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Доступ запрещён.")
        return ADMIN_MENU
    # Парсим: set_KEY_true / set_KEY_false
    data = query.data.replace("set_", "")
    # Разделяем последний _true/_false
    if data.endswith("_True"):
        key = data[:-5]
        value = "true"
    elif data.endswith("_False"):
        key = data[:-6]
        value = "false"
    else:
        await query.edit_message_text("Ошибка парсинга.", reply_markup=admin_menu_kb())
        return ADMIN_MENU
    await db.set_setting(key, value)
    # Обновляем config в runtime
    setattr(config, key, value == "true")
    # Показываем обновлённый список
    flags = await db.get_feature_flags()
    labels = db.FLAG_LABELS
    lines = ["⚙️ *Настройки функций:*\n"]
    kb = []
    for k, v in flags.items():
        if k == "ORG_TYPE":
            continue
        icon = "✅" if v else "❌"
        label = labels.get(k, k)
        lines.append(f"{icon} {label}")
        toggle_text = "Выкл" if v else "Вкл"
        kb.append([InlineKeyboardButton(f"{icon} {label} → {toggle_text}", callback_data=f"set_{k}_{not v}")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


# ── Прайс-лист: /sync_price ──
async def cmd_sync_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать статистику прайс-листа (только для админов)."""
    if not is_admin(update.effective_user.id):
        return
    services = await db.get_all_services()
    sections = await db.get_services_by_category()
    await update.message.reply_text(
        f"📋 *Прайс-лист:*\n\n"
        f"Разделов: {len(sections)}\n"
        f"Услуг: {len(services)}\n\n"
        f"Данные загружаются из БД",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── График работ ──

async def cb_admin_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать расписание всех мастеров."""
    query = update.callback_query
    await query.answer()
    masters = await db.get_masters()
    schedules = await db.get_all_schedules()
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    lines = ["📅 *График работы мастеров:*\n"]
    for m in masters:
        name = m["name"]
        sched = schedules.get(name, [])
        sched_dict = {s["day_of_week"]: s for s in sched}
        schedule_line = ""
        for i, day in enumerate(days):
            if i in sched_dict:
                s = sched_dict[i]
                if s["is_day_off"]:
                    schedule_line += "❌"
                else:
                    schedule_line += f"✅{s['start_time']}-{s['end_time']}"
            else:
                schedule_line += "—"
            schedule_line += " "
        lines.append(f"*{name}:* {schedule_line}")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Настроить расписание", callback_data="admin_set_schedule")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text("\n".join(lines), reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


async def cb_admin_set_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Выбор мастера для настройки расписания."""
    query = update.callback_query
    await query.answer()
    masters = await db.get_masters()
    kb = []
    for m in masters:
        kb.append([InlineKeyboardButton(m["name"], callback_data=f"sched_{m['name']}")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")])
    await query.edit_message_text("Выберите мастера:", reply_markup=InlineKeyboardMarkup(kb))
    return ADMIN_MENU


async def cb_select_master_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать расписание выбранного мастера."""
    query = update.callback_query
    await query.answer()
    master_name = query.data.replace("sched_", "")
    ctx.user_data["schedule_master"] = master_name
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    sched = await db.get_master_schedule(master_name)
    sched_dict = {s["day_of_week"]: s for s in sched}
    lines = [f"📅 *График: {master_name}*\n"]
    kb = []
    for i, day in enumerate(days):
        if i in sched_dict:
            s = sched_dict[i]
            if s["is_day_off"]:
                status = "❌ Выходной"
            else:
                status = f"✅ {s['start_time']}–{s['end_time']}"
        else:
            status = "— (по умолчанию 10:00–20:00)"
        lines.append(f"*{day}:* {status}")
        kb.append([InlineKeyboardButton(f"{day}: {status}", callback_data=f"sched_day_{i}")])
    kb.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


async def cb_edit_day_schedule(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Настройка конкретного дня."""
    query = update.callback_query
    await query.answer()
    day_idx = int(query.data.replace("sched_day_", ""))
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    master_name = ctx.user_data.get("schedule_master", "")
    ctx.user_data["schedule_day"] = day_idx
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Рабочий день (10:00–20:00)", callback_data="sched_work_default")],
        [InlineKeyboardButton("✅ Рабочий (свои часы)", callback_data="sched_work_custom")],
        [InlineKeyboardButton("❌ Выходной", callback_data="sched_off")],
        [InlineKeyboardButton("◀️ Назад", callback_data=f"sched_{master_name}")],
    ])
    await query.edit_message_text(f"Настроить *{days[day_idx]}* для {master_name}:", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


async def cb_set_work_default(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Установить рабочий день 10:00-20:00."""
    query = update.callback_query
    await query.answer()
    master_name = ctx.user_data.get("schedule_master", "")
    day_idx = ctx.user_data.get("schedule_day", 0)
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    await db.set_master_schedule(master_name, day_idx, "10:00", "20:00", 0)
    await query.edit_message_text(f"✅ {days[day_idx]}: 10:00–20:00 для {master_name}", reply_markup=back_btn("admin_menu"))
    return ADMIN_MENU


async def cb_set_day_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Установить выходной."""
    query = update.callback_query
    await query.answer()
    master_name = ctx.user_data.get("schedule_master", "")
    day_idx = ctx.user_data.get("schedule_day", 0)
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    await db.set_master_day_off(master_name, day_idx)
    await query.edit_message_text(f"❌ {days[day_idx]}: выходной для {master_name}", reply_markup=back_btn("admin_menu"))
    return ADMIN_MENU


async def cb_set_work_custom(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Запросить свои часы."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите время начала и конца (например: 9:00-18:00):")
    return ADMIN_SET_CUSTOM_HOURS


async def admin_custom_hours_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Ввод своих часов в формате 9:00-18:00."""
    import re
    text = update.message.text.strip()
    m = re.match(r"^(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})$", text)
    if not m:
        await update.message.reply_text("❌ Неверный формат. Введите как 9:00-18:00:")
        return ADMIN_SET_CUSTOM_HOURS
    sh, sm, eh, em = map(int, m.groups())
    if not (0 <= sh <= 23 and 0 <= eh <= 24 and sm in (0, 15, 30, 45)):
        await update.message.reply_text("❌ Часы 0–24, минуты кратны 15. Попробуйте ещё раз:")
        return ADMIN_SET_CUSTOM_HOURS
    start_time = f"{sh:02d}:{sm:02d}"
    end_time = f"{eh:02d}:{em:02d}"
    master_name = ctx.user_data.get("schedule_master", "")
    day_idx = ctx.user_data.get("schedule_day", 0)
    days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    await db.set_master_schedule(master_name, day_idx, start_time, end_time, 0)
    await update.message.reply_text(
        f"✅ {days[day_idx]}: {start_time}–{end_time} для {master_name}",
        reply_markup=admin_menu_kb(),
    )
    return ADMIN_MENU


# ── Услуги ──

async def cb_admin_services(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sections = await db.get_services_by_category()
    lines = ["📝 *Прайс-лист салона:*\n"]
    for i, section in enumerate(sections, 1):
        count = len(section["services"])
        lines.append(f"{i}. {section['title']} ({count} услуг)")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text("\n".join(lines), reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


async def cb_admin_add_svc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Управление услугами доступно через CRM:\nhttp://94.141.98.224:8000/",
                                  reply_markup=admin_menu_kb())
    return ADMIN_MENU


# cb_admin_sync_bitrix удалён — синхронизация с Битриксом не нужна


async def admin_add_svc_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_svc_name"] = update.message.text
    await update.message.reply_text("Введите цену (число):")
    return ADMIN_ADD_SERVICE_PRICE


async def admin_add_svc_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Введите число. Попробуйте ещё раз:")
        return ADMIN_ADD_SERVICE_PRICE
    ctx.user_data["new_svc_price"] = price
    await update.message.reply_text("Введите описание (или — для пропуска):")
    return ADMIN_ADD_SERVICE_DESC


async def admin_add_svc_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Управление услугами доступно через CRM:\nhttp://94.141.98.224:8000/",
        reply_markup=admin_menu_kb(),
    )
    return ADMIN_MENU


# ── Мастера ──

async def cb_admin_masters(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    masters = await db.get_masters()
    lines = ["👩‍🎨 *Мастера:*\n"]
    for i, m in enumerate(masters, 1):
        lines.append(f"{i}. {m['name']} — {m.get('specialization', '—')}")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить мастера", callback_data="admin_add_master")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text("\n".join(lines) or "Нет мастеров", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


async def cb_admin_add_master(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите имя мастера:")
    return ADMIN_ADD_MASTER_NAME


async def admin_add_master_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_master_name"] = update.message.text
    await update.message.reply_text("Введите специализацию:")
    return ADMIN_ADD_MASTER_SPEC


async def admin_add_master_spec(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["new_master_spec"] = update.message.text
    await update.message.reply_text("Отправьте фото мастера (или /skip для пропуска):")
    return ADMIN_ADD_MASTER_PHOTO


async def admin_add_master_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    photo_id = ""
    if update.message.photo:
        photo_id = update.message.photo[-1].file_id
    await db.add_master(
        name=ctx.user_data["new_master_name"],
        specialization=ctx.user_data["new_master_spec"],
        photo_file_id=photo_id,
    )
    await update.message.reply_text(
        f"✅ Мастер «{ctx.user_data['new_master_name']}» добавлен!",
        reply_markup=admin_menu_kb(),
    )
    return ADMIN_MENU


# ── Записи ──

async def cb_admin_bookings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pending = await db.get_pending_bookings()
    if not pending:
        text = "Нет ожидающих записей."
    else:
        lines = ["📋 *Ожидают обработки:*\n"]
        for b in pending[:10]:
            lines.append(f"#{b['id']} — {b.get('master_name', '—')} | {b.get('date', '')} {b.get('time', '')} | {b.get('client_name', '—')}")
        text = "\n".join(lines)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Подтвердить все", callback_data="admin_process_all")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


async def cb_admin_process_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Обрабатываю...")
    pending = await db.get_pending_bookings()
    count = 0
    for b in pending:
        await db.confirm_booking(b["id"])
        count += 1
    await query.edit_message_text(f"✅ Подтверждено {count} записей.", reply_markup=admin_menu_kb())
    return ADMIN_MENU





# ── Клиенты ──

async def cb_admin_clients(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    clients = await db.get_all_clients()
    if not clients:
        text = "Нет клиентов."
    else:
        lines = ["👥 *Клиенты:*\n"]
        for c in clients[:15]:
            name = c.get("name", "—") or "—"
            phone = c.get("phone", "—") or "—"
            ctype = c.get("client_type", "lead")
            tag = "✅" if ctype == "client" else "🔹"
            lines.append(f"{tag} {name} — {phone}")
        text = "\n".join(lines)
    await query.edit_message_text(text, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


# ── Рейтинг мастеров ──

async def cb_admin_ratings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать рейтинг всех мастеров."""
    query = update.callback_query
    await query.answer()
    masters = await db.get_masters()
    lines = ["⭐ *Рейтинг мастеров:*\n"]
    for m in masters:
        rating = await db.get_master_rating(m["name"])
        if rating["count"] > 0:
            stars = "⭐" * int(rating["avg"])
            lines.append(f"*{m['name']}*: {stars} {rating['avg']} ({rating['count']} отзывов)")
        else:
            lines.append(f"*{m['name']}*: нет отзывов")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text("\n".join(lines), reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


# ── Отзывы ──

async def cb_admin_reviews(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    reviews = await db.get_reviews(limit=10)
    if not reviews:
        text = "Нет отзывов."
    else:
        lines = ["⭐ *Отзывы:*\n"]
        for r in reviews:
            stars = "⭐" * r.get("score", 0)
            lines.append(f"• {stars} {r.get('client_name', '—')}: {r.get('comment', '—')[:80]}")
        text = "\n".join(lines)
    await query.edit_message_text(text, reply_markup=back_btn(), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


async def cb_client_reviews(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать отзывов клиентов (публичная версия)."""
    query = update.callback_query
    await query.answer()
    reviews = await db.get_reviews(limit=10)
    if not reviews:
        text = "💬 Отзывов пока нет.\nБудем рады вашему отзыву после визита!"
    else:
        if await _is_coworking_org():
            lines = ["💬 *Отзывы наших арендаторов:*\n"]
        else:
            lines = ["💬 *Отзывы наших клиентов:*\n"]
        for r in reviews:
            stars = "⭐" * r.get("score", 0)
            comment = r.get("comment", "")[:100]
            lines.append(f"{stars} {r.get('client_name', '—')}: {comment}")
        text = "\n\n".join(lines)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(await _book_btn_label(), callback_data="menu_book")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return MAIN_MENU


# ── Скидки ──

async def cb_admin_discounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎁 *Управление скидками*\n\n"
        "Автоматические скидки:\n"
        "• 3 визита → 5%\n"
        "• 5 визитов → 10%\n"
        "• 10 визитов → 15%\n\n"
        "Для ручного назначения введите Telegram ID клиента:",
        reply_markup=back_btn(),
        parse_mode=ParseMode.MARKDOWN,
    )
    return ADMIN_SET_DISCOUNT_TGID


async def admin_set_discount_tgid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["discount_tgid"] = update.message.text
    await update.message.reply_text("Введите размер скидки (%, число):")
    return ADMIN_SET_DISCOUNT_VALUE


async def admin_set_discount_value(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        value = int(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Введите число.")
        return ADMIN_SET_DISCOUNT_VALUE
    tgid = int(ctx.user_data["discount_tgid"])
    await db.set_discount(tgid, value)
    await update.message.reply_text(
        f"✅ Скидка {value}% назначена клиенту {tgid}",
        reply_markup=admin_menu_kb(),
    )
    return ADMIN_MENU


# ── Контент ──

async def cb_admin_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Текст приветствия", callback_data="edit_welcome")],
        [InlineKeyboardButton("💬 Текст после оценки 4-5", callback_data="edit_good_review")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back_main")],
    ])
    await query.edit_message_text("Выберите, что хотите изменить:", reply_markup=kb)
    return ADMIN_EDIT_CONTENT


async def cb_edit_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.replace("edit_", "")
    ctx.user_data["editing_content"] = key
    current = await db.get_content(key)
    await query.edit_message_text(
        f"Текущий текст:\n\n{current or '(пусто)'}\n\nОтправьте новый текст:"
    )
    return ADMIN_EDIT_CONTENT_SAVE


async def admin_save_content(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    key = ctx.user_data.get("editing_content", "")
    await db.set_content(key, update.message.text)
    await update.message.reply_text("✅ Сохранено!", reply_markup=admin_menu_kb())
    return ADMIN_MENU


# ══════════════════════════════════════════════════════════
#  Админ: Рассылка клиентам
# ══════════════════════════════════════════════════════════

async def cb_admin_mailing(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    client_ids = await db.get_all_client_ids()
    if not client_ids:
        await query.edit_message_text(
            "📭 Нет клиентов для рассылки.\n"
            "Клиенты появятся после первого обращения к боту.",
            reply_markup=admin_menu_kb(),
        )
        return ADMIN_MENU
    await query.edit_message_text(
        f"📨 *Рассылка клиентам*\n\n"
        f"Клиентов в базе: {len(client_ids)}\n\n"
        f"Введите текст рассылки:",
        reply_markup=back_btn(),
        parse_mode=ParseMode.MARKDOWN,
    )
    return ADMIN_MAILING_TEXT


async def admin_mailing_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["mailing_text"] = update.message.text
    client_ids = await db.get_all_client_ids()
    preview = (
        f"📨 *Предпросмотр рассылки:*\n\n"
        f"{update.message.text}\n\n"
        f"─────────────────\n"
        f"Получателей: {len(client_ids)}\n\n"
        f"Отправить?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Отправить", callback_data="mailing_confirm_yes")],
        [InlineKeyboardButton("❌ Отмена", callback_data="back_main")],
    ])
    await update.message.reply_text(preview, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MAILING_CONFIRM


async def admin_mailing_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if "yes" not in query.data:
        await query.edit_message_text("Рассылка отменена.", reply_markup=admin_menu_kb())
        return ADMIN_MENU

    text = ctx.user_data.get("mailing_text", "")
    client_ids = await db.get_all_client_ids()
    await query.edit_message_text("⏳ Отправляю рассылку...")

    sent = 0
    failed = 0
    for tg_id in client_ids:
        try:
            await ctx.bot.send_message(tg_id, text)
            sent += 1
        except Exception as e:
            failed += 1
            log.warning(f"Рассылка {tg_id}: {e}")

    result = (
        f"✅ *Рассылка завершена!*\n\n"
        f"Отправлено: {sent}\n"
        f"Не доставлено: {failed}"
    )
    await query.message.reply_text(result, reply_markup=admin_menu_kb(), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


# ══════════════════════════════════════════════════════════
#  Потерянные клиенты
# ══════════════════════════════════════════════════════════

async def cb_admin_lost_clients(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать потерянных клиентов (не были 60+ дней)."""
    query = update.callback_query
    await query.answer()
    lost = await db.get_lost_clients(60)
    if not lost:
        text = "🔍 Потерянных клиентов нет! Все активны."
    else:
        lines = [f"🔍 *Потерянные клиенты (60+ дней):* {len(lost)}\n"]
        for c in lost[:10]:
            name = c.get("name", "—") or "—"
            phone = c.get("phone", "—") or "—"
            last = c.get("last_visit", "нет визитов") or "нет визитов"
            lines.append(f"• {name} | {phone} | последний визит: {last}")
        text = "\n".join(lines)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Напоминание потерянным", callback_data="admin_mail_lost")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


async def cb_admin_mail_lost(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Рассылка потерянным клиентам."""
    query = update.callback_query
    await query.answer()
    ctx.user_data["mailing_segment"] = "lost"
    lost = await db.get_lost_clients(60)
    await query.edit_message_text(
        f"📨 *Рассылка потерянным клиентам*\n\n"
        f"Получателей: {len(lost)}\n\n"
        f"Введите текст напоминания (например, со скидкой):",
        reply_markup=back_btn(),
        parse_mode=ParseMode.MARKDOWN,
    )
    return ADMIN_MAILING_SEGMENT_TEXT


# ══════════════════════════════════════════════════════════
#  Рассылка по сегментам
# ══════════════════════════════════════════════════════════

async def cb_admin_mailing_segments(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Выбор сегмента для рассылки."""
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 Всем клиентам", callback_data="seg_all")],
        [InlineKeyboardButton("🔍 Не были 60+ дней", callback_data="seg_lost")],
        [InlineKeyboardButton("🆕 Новым (1 визит)", callback_data="seg_new")],
        [InlineKeyboardButton("⭐ Постоянным (3+ визита)", callback_data="seg_regular")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")],
    ])
    await query.edit_message_text(
        "📨 *Выберите сегмент для рассылки:*",
        reply_markup=kb,
        parse_mode=ParseMode.MARKDOWN,
    )
    return ADMIN_MENU


async def cb_seg_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Выбран сегмент — запросить текст."""
    query = update.callback_query
    await query.answer()
    segment = query.data.replace("seg_", "")
    ctx.user_data["mailing_segment"] = segment
    clients = await db.get_clients_by_segment(segment)
    segment_names = {
        "all": "всем клиентам",
        "lost": "потерянным клиентам",
        "new": "новым клиентам",
        "regular": "постоянным клиентам",
    }
    await query.edit_message_text(
        f"📨 *Рассылка {segment_names.get(segment, segment)}*\n\n"
        f"Получателей: {len(clients)}\n\n"
        f"Введите текст рассылки:",
        reply_markup=back_btn(),
        parse_mode=ParseMode.MARKDOWN,
    )
    return ADMIN_MAILING_SEGMENT_TEXT


async def admin_mailing_segment_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Текст рассылки введён — показать предпросмотр."""
    ctx.user_data["mailing_segment_text"] = update.message.text
    segment = ctx.user_data.get("mailing_segment", "all")
    clients = await db.get_clients_by_segment(segment)
    segment_names = {
        "all": "всем клиентам",
        "lost": "потерянным",
        "new": "новым",
        "regular": "постоянным",
    }
    preview = (
        f"📨 *Предпросмотр ({segment_names.get(segment, segment)}):*\n\n"
        f"{update.message.text}\n\n"
        f"─────────────────\n"
        f"Получателей: {len(clients)}\n\n"
        f"Отправить?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Отправить", callback_data="seg_confirm_yes")],
        [InlineKeyboardButton("❌ Отмена", callback_data="back_main")],
    ])
    await update.message.reply_text(preview, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MAILING_SEGMENT_CONFIRM


async def admin_mailing_segment_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Подтверждение рассылки по сегменту."""
    query = update.callback_query
    await query.answer()
    if "yes" not in query.data:
        await query.edit_message_text("Рассылка отменена.", reply_markup=admin_menu_kb())
        return ADMIN_MENU

    text = ctx.user_data.get("mailing_segment_text", "")
    segment = ctx.user_data.get("mailing_segment", "all")
    clients = await db.get_clients_by_segment(segment)
    await query.edit_message_text("⏳ Отправляю рассылку...")

    sent = 0
    failed = 0
    for c in clients:
        tg_id = c.get("telegram_id", 0)
        if tg_id <= 0:
            continue
        try:
            await ctx.bot.send_message(tg_id, text)
            sent += 1
        except Exception as e:
            failed += 1
            log.warning(f"Рассылка {tg_id}: {e}")

    result = (
        f"✅ *Рассылка завершена!*\n\n"
        f"Отправлено: {sent}\n"
        f"Не доставлено: {failed}"
    )
    await query.message.reply_text(result, reply_markup=admin_menu_kb(), parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


# ══════════════════════════════════════════════════════════
#  Аналитика
# ══════════════════════════════════════════════════════════

async def cb_admin_analytics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показать аналитику клиентов."""
    query = update.callback_query
    await query.answer()
    stats = await db.get_clients_stats()
    text = (
        f"📊 *Аналитика клиентов*\n\n"
        f"👥 Всего клиентов: {stats['total']}\n"
        f"🆕 Новых за месяц: {stats['new_this_month']}\n"
        f"🔍 Потерянных (60+ дней): {stats['lost_60_days']}\n"
        f"⭐ Постоянных (3+ визита): {stats['regular_3plus']}\n"
        f"📈 Среднее визитов: {stats['avg_visits']}\n\n"
    )
    if stats.get("top_services"):
        text += "🏆 *Топ услуги:*\n"
        for s in stats["top_services"][:5]:
            text += f"  • {s['name']}: {s['count']} записей\n"
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Открыть в CRM", url="http://94.141.98.224:8000/analytics")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_menu")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
    return ADMIN_MENU


# ══════════════════════════════════════════════════════════
#  День рождения клиента
# ══════════════════════════════════════════════════════════

async def cb_birthday(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Запрос дня рождения."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎂 *Введите вашу дату рождения*\n\n"
        "Формат: ДД.ММ (например, 15.03)\n\n"
        "Это нужно для персональных поздравлений и.special offers!",
        reply_markup=back_btn(),
        parse_mode=ParseMode.MARKDOWN,
    )
    return BIRTHDAY_INPUT


async def birthday_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Сохранить день рождения."""
    text = update.message.text.strip()
    # Валидация формата ДД.ММ
    import re
    if not re.match(r'^\d{2}\.\d{2}$', text):
        await update.message.reply_text("❌ Неверный формат. Введите ДД.ММ (например, 15.03):")
        return BIRTHDAY_INPUT
    day, month = map(int, text.split("."))
    if day < 1 or day > 31 or month < 1 or month > 12:
        await update.message.reply_text("❌ Неверная дата. Введите ДД.ММ (например, 15.03):")
        return BIRTHDAY_INPUT

    await db.update_client_birthday(update.effective_user.id, text)
    await update.message.reply_text(
        f"🎂 День рождения сохранён: {text}\n\n"
        f"Мы обязательно поздравим вас!",
        reply_markup=await main_menu_kb(),
    )
    return MAIN_MENU


# ══════════════════════════════════════════════════════════
#  Back / Cancel
# ══════════════════════════════════════════════════════════

async def cb_back_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    log.info(f"BACK: cb_back_main called, user={query.from_user.id}, data={query.data}")
    kb = await main_menu_kb_with_coworking(query.from_user.id)
    await query.edit_message_text("Выберите раздел:", reply_markup=kb)
    log.info("BACK: returned to main menu")
    return MAIN_MENU


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = await main_menu_kb_with_coworking(update.effective_user.id)
    await update.message.reply_text("Действие отменено.", reply_markup=kb)
    return MAIN_MENU


# ══════════════════════════════════════════════════════════
#  main
# ══════════════════════════════════════════════════════════

async def post_init(app: Application):
    log.info("POST_INIT: started")
    await db.init()
    log.info("POST_INIT: db.init done")


async def sync_missed_messages(context: ContextTypes.DEFAULT_TYPE):
    """Синхронизация при старте: отправить пропущенные напоминания и опросы."""
    from datetime import datetime, timedelta
    try:
        now = datetime.now()
        sent_count = 0

        # 1. Напоминания за 24 часа (для записей завтра, которые ещё не напоминали)
        bookings_24h = db.group_consecutive_slots(await db.get_upcoming_bookings(hours_ahead=24))
        for b in bookings_24h:
            tl = b["start_time"] if b["start_time"] == b["end_time"] else f'{b["start_time"]} – {b["end_time"]}'
            text = (
                f"📅 *Напоминание о записи*\n\n"
                f"Завтра у вас запись:\n"
                f"Мастер: {b['master_name']}\n"
                f"Дата: {b['date']}\n"
                f"Время: {tl}\n\n"
                f"Подтвердите или отмените запись:"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить", callback_data=f"remind_confirm_{b['id']}")],
                [InlineKeyboardButton("❌ Отменить", callback_data=f"remind_cancel_{b['id']}")],
            ])
            try:
                await context.bot.send_message(
                    b["telegram_id"], text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN
                )
                await db.db_mark_reminders_sent(b["ids"], "reminder_sent")
                sent_count += 1
                log.info(f"SYNC: 24h напоминание -> {b['client_name']} (id={b['telegram_id']}) slots={len(b['ids'])}")
            except Exception as e:
                log.warning(f"SYNC: ошибка 24h {b['telegram_id']}: {e}")

        # 2. Напоминания за 2 часа
        bookings_2h = db.group_consecutive_slots(await db.get_upcoming_bookings_2h())
        for b in bookings_2h:
            tl = b["start_time"] if b["start_time"] == b["end_time"] else f'{b["start_time"]} – {b["end_time"]}'
            text = (
                f"⏰ *Напоминание*\n\n"
                f"Через 2 часа у вас запись!\n"
                f"Мастер: {b['master_name']}\n"
                f"Время: {tl}\n\n"
                f"Ждём вас!"
            )
            try:
                await context.bot.send_message(
                    b["telegram_id"], text, parse_mode=ParseMode.MARKDOWN
                )
                await db.db_mark_reminders_sent(b["ids"], "reminder_2h_sent")
                sent_count += 1
                log.info(f"SYNC: 2h напоминание -> {b['client_name']} (id={b['telegram_id']}) slots={len(b['ids'])}")
            except Exception as e:
                log.warning(f"SYNC: ошибка 2h {b['telegram_id']}: {e}")

        # 3. Повторное напоминание через 2ч (если не подтвердил)
        async with aiosqlite.connect(config.DB_PATH) as adb:
            adb.row_factory = aiosqlite.Row
            cur = await adb.execute(
                """SELECT * FROM bookings
                   WHERE reminder_sent = 1 AND reminder_repeat_sent = 0
                   AND confirmed = 0 AND telegram_id > 0""",
            )
            unconfirmed = db.group_consecutive_slots([dict(r) for r in await cur.fetchall()])
        for b in unconfirmed:
            tl = b["start_time"] if b["start_time"] == b["end_time"] else f'{b["start_time"]} – {b["end_time"]}'
            text = (
                f"⏰ *Напоминание*\n\n"
                f"Вы не подтвердили запись на завтра:\n"
                f"Мастер: {b['master_name']}\n"
                f"Время: {tl}\n\n"
                f"Пожалуйста, подтвердите или отмените запись:"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить", callback_data=f"remind_confirm_{b['id']}")],
                [InlineKeyboardButton("❌ Отменить", callback_data=f"remind_cancel_{b['id']}")],
            ])
            try:
                await context.bot.send_message(
                    b["telegram_id"], text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN
                )
                await db.db_mark_reminders_sent(b["ids"], "reminder_repeat_sent")
                sent_count += 1
                log.info(f"SYNC: повторное напоминание -> {b['client_name']} (id={b['telegram_id']}) slots={len(b['ids'])}")
            except Exception as e:
                log.warning(f"SYNC: ошибка повторного {b['telegram_id']}: {e}")

        # 4. Запрос оценки — обрабатывается в check_reminders (job_queue каждые 5 мин)

        if sent_count > 0:
            log.info(f"SYNC: отправлено {sent_count} сообщений")
        else:
            log.info("SYNC: все сообщения уже доставлены")

    except Exception as e:
        log.error(f"SYNC: ошибка синхронизации: {e}")


async def debug_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    log.info(f"DEBUG: Received update {update.update_id}, message={update.message}, callback={update.callback_query}")
    if update.message:
        log.info(f"DEBUG: text={update.message.text}, user={update.effective_user.id}")
    if update.callback_query:
        log.info(f"DEBUG: callback_data={update.callback_query.data}, user={update.callback_query.from_user.id}")


async def error_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    log.error(f"Unhandled error: {ctx.error}", exc_info=ctx.error)


_last_birthday_run = {"date": ""}


async def check_birthdays(bot):
    """Поздравление клиентов с днём рождения (вызывается из reminder_loop раз в сутки)."""
    if not config.BIRTHDAY_DISCOUNT:
        return
    try:
        birthdays = await db.get_birthdays_today()
        if not birthdays:
            return
        log.info(f"BIRTHDAY: found {len(birthdays)} birthdays today")
        for client in birthdays:
            tg_id = client.get("telegram_id", 0)
            name = client.get("name", "") or "дорогой клиент"
            if tg_id <= 0:
                continue
            try:
                # Начисляем скидку на день рождения (не затираем если уже выше)
                current = await db.get_discount(tg_id)
                if current < 15:
                    await db.set_discount(tg_id, 15)
                text = (
                    f"🎂 *С днём рождения, {name}!*\n\n"
                    f"Поздравляем вас! Желаем красоты и сияния!\n\n"
                    f"🎁 *Ваш подарок: скидка 15%* на любую процедуру!\n"
                    f"Скидка действует весь месяц.\n\n"
                    f"Запишитесь прямо сейчас и порадуйте себя!"
                )
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton(await _book_btn_label(), callback_data="menu_book")],
                ])
                await bot.send_message(tg_id, text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
                log.info(f"BIRTHDAY: sent to {name} (id={tg_id})")
            except Exception as e:
                log.warning(f"BIRTHDAY: error sending to {tg_id}: {e}")
    except Exception as e:
        log.error(f"BIRTHDAY: error checking birthdays: {e}")


async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Фоновая задача: напоминания за 24ч, за 2ч, и об оценке."""
    log.info("CHECK_REMINDERS: started")
    from datetime import datetime, timedelta
    try:
        # Напоминание за 24 часа
        bookings = db.group_consecutive_slots(await db.get_upcoming_bookings(hours_ahead=24))
        for b in bookings:
            tl = b["start_time"] if b["start_time"] == b["end_time"] else f'{b["start_time"]} – {b["end_time"]}'
            text = (
                f"📅 *Напоминание о записи*\n\n"
                f"Завтра у вас запись:\n"
                f"Мастер: {b['master_name']}\n"
                f"Дата: {b['date']}\n"
                f"Время: {tl}\n\n"
                f"Подтвердите или отмените запись:"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Подтвердить", callback_data=f"remind_confirm_{b['id']}")],
                [InlineKeyboardButton("❌ Отменить", callback_data=f"remind_cancel_{b['id']}")],
            ])
            try:
                await context.bot.send_message(
                    b["telegram_id"], text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN
                )
                await db.db_mark_reminders_sent(b["ids"], "reminder_sent")
                log.info(f"Напоминание 24ч: {b['client_name']} (id={b['telegram_id']}) slots={len(b['ids'])}")
            except Exception as e:
                log.warning(f"Ошибка напоминания 24ч {b['telegram_id']}: {e}")

        # Напоминание за 2 часа
        bookings_2h = db.group_consecutive_slots(await db.get_upcoming_bookings_2h())
        for b in bookings_2h:
            tl = b["start_time"] if b["start_time"] == b["end_time"] else f'{b["start_time"]} – {b["end_time"]}'
            text = (
                f"⏰ *Напоминание*\n\n"
                f"Через 2 часа у вас запись!\n"
                f"Мастер: {b['master_name']}\n"
                f"Время: {tl}\n\n"
                f"Ждём вас!"
            )
            try:
                await context.bot.send_message(
                    b["telegram_id"], text, parse_mode=ParseMode.MARKDOWN
                )
                await db.db_mark_reminders_sent(b["ids"], "reminder_2h_sent")
                log.info(f"Напоминание 2ч: {b['client_name']} (id={b['telegram_id']}) slots={len(b['ids'])}")
            except Exception as e:
                log.warning(f"Ошибка напоминания 2ч {b['telegram_id']}: {e}")

        # Запрос оценки (следующий день, 9:00-21:00)
        if config.RATING_ENABLED:
            now = datetime.now()
            if 9 <= now.hour < 21:
                yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
                async with aiosqlite.connect(config.DB_PATH) as adb:
                    adb.row_factory = aiosqlite.Row
                    cur = await adb.execute(
                        "SELECT * FROM bookings WHERE date = ? AND confirmed = 1 AND telegram_id > 0 AND review_sent = 0",
                        (yesterday,),
                    )
                    completed = db.group_consecutive_slots([dict(r) for r in await cur.fetchall()])
                for b in completed:
                    tl = b["start_time"] if b["start_time"] == b["end_time"] else f'{b["start_time"]} – {b["end_time"]}'
                    text = (
                        f"⭐ *Как прошла ваша запись?*\n\n"
                        f"Мастер: {b['master_name']}\n"
                        f"Дата: {b['date']}\n"
                        f"Время: {tl}\n\n"
                        f"Пожалуйста, оцените обслуживание от 1 до 5 звёзд:"
                    )
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{'⭐' * i}", callback_data=f"review_s_{b['id']}_{i}")]
                        for i in range(1, 6)
                    ])
                    try:
                        await context.bot.send_message(
                            b["telegram_id"], text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN
                        )
                        await db.db_mark_reminders_sent(b["ids"], "review_sent")
                        log.info(f"Запрос оценки: {b['client_name']} (id={b['telegram_id']}) slots={len(b['ids'])}")
                    except Exception as e:
                        log.warning(f"Ошибка запроса оценки {b['telegram_id']}: {e}")

                # Автоочистка ОТКЛЮЧЕНА (24.08.2026): история записей больше не удаляется.
                # Ранее здесь удалялись записи старше 2 дней с отправленным запросом оценки,
                # из-за чего пропадали старые записи в CRM.

    except Exception as e:
        log.error(f"Ошибка проверки напоминаний: {e}")


async def cb_review_score(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Обработка оценки от клиента (review_s_{id}_{score})."""
    query = update.callback_query
    await query.answer()
    parts = query.data.replace("review_s_", "").split("_")
    booking_id, score = int(parts[0]), int(parts[1])
    log.info(f"REVIEW: booking_id={booking_id}, score={score}")

    # Получаем данные записи
    all_bookings = await db.get_all_bookings()
    b = next((x for x in all_bookings if x["id"] == booking_id), None)

    if not b:
        await query.edit_message_text("Запись не найдена.", reply_markup=await main_menu_kb())
        return MAIN_MENU

    client = await ensure_client(update, ctx)
    master_name = b.get("master_name", "—")
    client_name = b.get("client_name", "—")

    # Сохраняем отзыв в локальную БД
    await db.add_review(master_name, client_name, score)

    if score <= 3:
        # Негативный отзыв — благодарим и уведомляем админа
        await query.edit_message_text(
            "🙏 Спасибо за вашу оценку!\n\n"
            "Нам жаль, что вам не понравилось.\n"
            "Администратор свяжется с вами для решения вопроса.",
            reply_markup=await main_menu_kb(),
        )
        # Уведомляем админа
        client_data = await db.get_client(update.effective_user.id)
        phone = client_data.get("phone", "не указан") if client_data else "не указан"
        for admin_id in config.ADMIN_IDS:
            try:
                await ctx.bot.send_message(
                    admin_id,
                    f"⚠️ *Низкая оценка!*\n\n"
                    f"Клиент: {client_name}\n"
                    f"Телефон: {phone}\n"
                    f"Мастер: {master_name}\n"
                    f"Оценка: {'⭐' * score}\n\n"
                    f"📞 Рекомендуется связаться с клиентом!",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                pass
    else:
        # Высокая оценка — начисляем скидку 10% на 50 дней
        if config.REVIEW_DISCOUNT:
            await db.set_review_discount(client["id"], percent=10, days=50)
            discount_info = await db.get_review_discount(client["id"])
            await query.edit_message_text(
                f"🎉 Спасибо за высокую оценку!\n\n"
                f"Вам начислена скидка 10% на следующую процедуру!\n"
                f"Действует до: {discount_info['expires']}\n\n"
                f"Ждём вас снова!",
                reply_markup=await main_menu_kb(),
            )
        else:
            await query.edit_message_text(
                "🎉 Спасибо за высокую оценку!\n\n"
                "Рады, что вам понравилось! Ждём вас снова!",
                reply_markup=await main_menu_kb(),
            )
        log.info(f"REVIEW: высокая оценка client_id={client['id']}")

    # Помечаем что запрос оценки отправлен (весь range одной записью)
    await db.db_mark_reminders_sent(await db.get_range_ids_for_booking(booking_id), "review_sent")
    return MAIN_MENU


async def cb_remind_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    booking_id = int(query.data.replace("remind_confirm_", ""))
    ids = await db.get_range_ids_for_booking(booking_id)
    await db.confirm_bookings(ids)

    log.info(f"CONFIRM: запись #{booking_id} подтверждена (slots={len(ids)})")

    await query.edit_message_text(
        "✅ Запись подтверждена! Ждём вас.\n"
        "Если что-то изменится — напишите нам.",
        reply_markup=await main_menu_kb(),
    )
    return MAIN_MENU


async def cb_remind_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    booking_id = int(query.data.replace("remind_cancel_", ""))
    ids = await db.get_range_ids_for_booking(booking_id)
    # Получаем данные записи для уведомления админа
    all_bookings = await db.get_all_bookings()
    b = next((x for x in all_bookings if x["id"] == booking_id), None) or {}
    times = sorted(x.get("time", "") for x in all_bookings if x.get("id") in ids and x.get("time"))
    time_line = times[0] if len(times) == 1 else (f"{times[0]} – {db._add_minutes(times[-1], 15)}" if times else b.get("time", "—"))

    # Удаляем весь range
    await db.cancel_bookings(ids)
    # Лист ожидания → сообщить об освободившемся окне
    try:
        free_time = times[0] if times else b.get("time", "")
        matches = await db.notify_waitlist_for_slot(
            b.get("master_name", ""), b.get("date", ""), free_time,
        )
        for m in matches:
            try:
                await ctx.bot.send_message(
                    m["telegram_id"],
                    f"🔔 Освободилось окно!\n\n"
                    f"Мастер: {b.get('master_name', '—')}\n"
                    f"Дата: {b.get('date', '—')}\n"
                    f"Время: {free_time}\n\n"
                    f"Записывайтесь: /start → Записаться",
                )
            except Exception:
                pass
    except Exception:
        pass
    # Уведомляем админа
    for admin_id in config.ADMIN_IDS:
        try:
            await ctx.bot.send_message(
                admin_id,
                f"❌ *Запись отменена клиентом*\n\n"
                f"Клиент: {b.get('client_name', '—')}\n"
                f"Мастер: {b.get('master_name', '—')}\n"
                f"Дата: {b.get('date', '—')}\n"
                f"Время: {time_line}",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass
    await query.edit_message_text(
        "❌ Запись отменена.\n"
        "Если захотите записаться снова — я к вашим услугам!",
        reply_markup=await main_menu_kb(),
    )
    return MAIN_MENU


def build_application():
    """Build and configure the Telegram bot application."""
    from telegram.request import HTTPXRequest

    # Use SOCKS5 proxy if configured (needed for serverspace.by)
    if config.SOCKS5_PROXY:
        request = HTTPXRequest(proxy=config.SOCKS5_PROXY, connect_timeout=30, read_timeout=30)
    else:
        request = HTTPXRequest(connect_timeout=30, read_timeout=30)

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .updater(None)
        .post_init(post_init)
        .request(request)
        .build()
    )
    app.add_error_handler(error_handler)

    # ── Главное меню + клиентские функции ──
    # Обработчики ВНЕ ConversationHandler (регистрируются ПЕРВЫМИ)
    app.add_handler(CallbackQueryHandler(cb_remind_confirm, pattern="^remind_confirm_"))
    app.add_handler(CallbackQueryHandler(cb_remind_cancel, pattern="^remind_cancel_"))
    app.add_handler(CallbackQueryHandler(cb_review_score, pattern="^review_s_"))
    app.add_handler(CallbackQueryHandler(cb_cal_ignore, pattern="^cal_ignore$"))

    # ConversationHandler
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("debug_db", cmd_debug_db),
            CommandHandler("sync_price", cmd_sync_price),
            CommandHandler("settings", cmd_settings),
        ],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(cb_services, pattern="^menu_services$"),
                CallbackQueryHandler(cb_masters, pattern="^menu_masters$"),
                CallbackQueryHandler(cb_works, pattern="^menu_works$"),
                CallbackQueryHandler(cb_works_category, pattern="^works_cat_"),
                CallbackQueryHandler(cb_consultation, pattern="^consultation$"),
                CallbackQueryHandler(cb_book, pattern="^menu_book$"),
                CallbackQueryHandler(cb_waitlist, pattern="^menu_waitlist$"),
                CallbackQueryHandler(cb_waitlist_master, pattern="^wl_master_"),
                CallbackQueryHandler(cb_waitlist_date, pattern="^wl_date_"),
                CallbackQueryHandler(cb_my_bookings, pattern="^menu_my_bookings$"),
                CallbackQueryHandler(cb_edit_booking, pattern="^menu_edit_booking$"),
                CallbackQueryHandler(cb_history, pattern="^menu_history$"),
                CallbackQueryHandler(cb_rebook, pattern="^rebook_"),
                CallbackQueryHandler(cb_discount, pattern="^menu_discount$"),
                CallbackQueryHandler(cb_birthday, pattern="^menu_birthday$"),
                CallbackQueryHandler(cb_location, pattern="^menu_location$"),
                CallbackQueryHandler(cb_admin_menu, pattern="^admin_menu$"),
                CallbackQueryHandler(cb_admin_settings, pattern="^admin_settings$"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
                CallbackQueryHandler(cb_remind_confirm, pattern="^remind_confirm_"),
                CallbackQueryHandler(cb_remind_cancel, pattern="^remind_cancel_"),
                CallbackQueryHandler(cb_review_score, pattern="^review_s_"),
                CallbackQueryHandler(cb_coworking, pattern="^coworking$"),
            ],
            WAITLIST: [
                CallbackQueryHandler(cb_waitlist_master, pattern="^wl_master_"),
                CallbackQueryHandler(cb_waitlist_date, pattern="^wl_date_"),
                CallbackQueryHandler(cb_waitlist, pattern="^menu_waitlist$"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            BOOK_SELECT_GENDER: [
                CallbackQueryHandler(book_select_gender, pattern="^gender_"),
                CallbackQueryHandler(services_select_gender, pattern="^price_gender_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            BOOK_SELECT_SERVICE: [
                CallbackQueryHandler(cb_consultation, pattern="^consultation$"),
                CallbackQueryHandler(book_select_section, pattern="^book_sec_"),
                CallbackQueryHandler(book_select_service, pattern="^book_svc_"),
                CallbackQueryHandler(book_multi_toggle, pattern="^book_mtgl_"),
                CallbackQueryHandler(book_multi_done, pattern="^book_mdone_"),
                CallbackQueryHandler(services_select_section, pattern="^price_sec_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            BOOK_SELECT_MASTER: [
                CallbackQueryHandler(book_select_master, pattern="^book_m_"),
                CallbackQueryHandler(cb_book, pattern="^menu_book$"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            BOOK_SELECT_DATE: [
                CallbackQueryHandler(book_cal_slot, pattern="^book_slot_"),
                CallbackQueryHandler(book_toggle_slot, pattern="^book_tgl_"),
                CallbackQueryHandler(book_commit, pattern="^book_commit$"),
                CallbackQueryHandler(book_commit_nop, pattern="^book_commit_nop$"),
                CallbackQueryHandler(book_cal_day, pattern="^cal_day_"),
                CallbackQueryHandler(book_cal_month, pattern="^cal_month_"),
                CallbackQueryHandler(book_cal_back, pattern="^cal_back_"),
                CallbackQueryHandler(cb_book, pattern="^menu_book$"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            BOOK_SELECT_START: [
                CallbackQueryHandler(book_toggle_slot, pattern="^book_tgl_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            BOOK_SELECT_END: [
                CallbackQueryHandler(book_commit, pattern="^book_commit$"),
                CallbackQueryHandler(book_cal_day, pattern="^cal_day_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            BOOK_CONFIRM: [
                CallbackQueryHandler(book_confirm, pattern="^book_confirm_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            RATE_SELECT_BOOKING: [
                CallbackQueryHandler(rate_select_booking, pattern="^rate_d_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            RATE_GIVE_SCORE: [
                CallbackQueryHandler(rate_give_score, pattern="^rate_s_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            RATE_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rate_comment),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            PHONE_INPUT: [
                MessageHandler(filters.CONTACT, phone_received),
                MessageHandler(filters.TEXT & ~filters.COMMAND, phone_received),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            BOOK_ASK_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, book_ask_name),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            EDIT_SELECT_BOOKING: [
                CallbackQueryHandler(cb_edit_pick, pattern="^edit_pick_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            # ── Коворкинг ──
            COWORKING_SELECT_DATE: [
                CallbackQueryHandler(cow_cal_day, pattern="^cow_cal_day_"),
                CallbackQueryHandler(cow_cal_month, pattern="^cow_cal_month_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            COWORKING_SELECT_START: [
                CallbackQueryHandler(cow_select_start, pattern="^cow_start_"),
                CallbackQueryHandler(cow_cal_back, pattern="^cow_cal_back_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            COWORKING_SELECT_END: [
                CallbackQueryHandler(cow_select_end, pattern="^cow_end_"),
                CallbackQueryHandler(cow_cal_day, pattern="^cow_cal_day_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            COWORKING_CONFIRM: [
                CallbackQueryHandler(cow_confirm, pattern="^cow_confirm$"),
                CallbackQueryHandler(cow_cancel, pattern="^cow_cancel$"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            # ── Админ ──
            ADMIN_MENU: [
                CallbackQueryHandler(cb_admin_services, pattern="^admin_services$"),
                CallbackQueryHandler(cb_admin_add_svc, pattern="^admin_add_svc$"),
                CallbackQueryHandler(cb_admin_masters, pattern="^admin_masters$"),
                CallbackQueryHandler(cb_admin_add_master, pattern="^admin_add_master$"),
                CallbackQueryHandler(cb_admin_ratings, pattern="^admin_ratings$"),
                CallbackQueryHandler(cb_admin_schedule, pattern="^admin_schedule$"),
                CallbackQueryHandler(cb_admin_set_schedule, pattern="^admin_set_schedule$"),
                CallbackQueryHandler(cb_edit_day_schedule, pattern="^sched_day_"),
                CallbackQueryHandler(cb_select_master_schedule, pattern="^sched_"),
                CallbackQueryHandler(cb_set_work_default, pattern="^sched_work_default$"),
                CallbackQueryHandler(cb_set_day_off, pattern="^sched_off$"),
                CallbackQueryHandler(cb_set_work_custom, pattern="^sched_work_custom$"),
                CallbackQueryHandler(cb_admin_bookings, pattern="^admin_bookings$"),
                CallbackQueryHandler(cb_admin_process_all, pattern="^admin_process_all$"),

                CallbackQueryHandler(cb_admin_clients, pattern="^admin_clients$"),
                CallbackQueryHandler(cb_admin_lost_clients, pattern="^admin_lost_clients$"),
                CallbackQueryHandler(cb_admin_mail_lost, pattern="^admin_mail_lost$"),
                CallbackQueryHandler(cb_admin_mailing_segments, pattern="^admin_mailing_segments$"),
                CallbackQueryHandler(cb_seg_select, pattern="^seg_"),
                CallbackQueryHandler(cb_admin_analytics, pattern="^admin_analytics$"),
                CallbackQueryHandler(cb_admin_reviews, pattern="^admin_reviews$"),
                CallbackQueryHandler(cb_admin_discounts, pattern="^admin_discounts$"),
                CallbackQueryHandler(cb_admin_mailing, pattern="^admin_mailing$"),
                CallbackQueryHandler(cb_admin_content, pattern="^admin_content$"),
                CallbackQueryHandler(cb_contact, pattern="^menu_contact$"),
                CallbackQueryHandler(cb_admin_menu, pattern="^admin_menu$"),
                CallbackQueryHandler(cb_admin_settings, pattern="^admin_settings$"),
                CallbackQueryHandler(cb_toggle_setting, pattern="^set_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_ADD_SERVICE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_svc_name),
                CallbackQueryHandler(cb_contact, pattern="^menu_contact$"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_ADD_SERVICE_PRICE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_svc_price),
                CallbackQueryHandler(cb_contact, pattern="^menu_contact$"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_ADD_SERVICE_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_svc_desc),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_ADD_MASTER_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_master_name),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_ADD_MASTER_SPEC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_master_spec),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_ADD_MASTER_PHOTO: [
                MessageHandler(filters.PHOTO | (filters.TEXT & ~filters.COMMAND), admin_add_master_photo),
                CommandHandler("skip", admin_add_master_photo),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_SET_DISCOUNT_TGID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_discount_tgid),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_SET_DISCOUNT_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_discount_value),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_EDIT_CONTENT: [
                CallbackQueryHandler(cb_edit_content, pattern="^edit_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_EDIT_CONTENT_SAVE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_save_content),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_MAILING_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_mailing_text),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_MAILING_CONFIRM: [
                CallbackQueryHandler(admin_mailing_confirm, pattern="^mailing_confirm_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_MAILING_SEGMENT_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_mailing_segment_text),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_MAILING_SEGMENT_CONFIRM: [
                CallbackQueryHandler(admin_mailing_segment_confirm, pattern="^seg_confirm_"),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            BIRTHDAY_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, birthday_received),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
            ADMIN_SET_CUSTOM_HOURS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_custom_hours_input),
                CallbackQueryHandler(cb_back_main, pattern="^back_main$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            CommandHandler("start", cmd_start),
        ],
        allow_reentry=True,
        conversation_timeout=600,
    )
    app.add_handler(conv, group=0)
    app.add_handler(CallbackQueryHandler(cb_consultation, pattern="^consultation$"), group=1)

    return app


async def polling_loop(app):
    """Custom polling loop with logging and error handling."""
    import httpx

    if config.SOCKS5_PROXY:
        http_client = httpx.AsyncClient(
            proxy=config.SOCKS5_PROXY, timeout=httpx.Timeout(connect=30, read=60, write=30, pool=5),
        )
    else:
        http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=30, read=60, write=30, pool=5),
        )

    async def tg_send(chat_id: int, text: str, reply_markup=None):
        """Отправить сообщение через Telegram API напрямую."""
        body = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup:
            body["reply_markup"] = reply_markup
        try:
            await http_client.post(
                f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage", json=body
            )
        except Exception as e:
            log.warning(f"tg_send error to {chat_id}: {e}")

    async def reminder_loop():
        """Фоновая задача: напоминания каждые 5 минут."""
        await asyncio.sleep(30)
        log.info("REMINDER_LOOP: started")
        while True:
            try:
                from datetime import datetime, timedelta
                now = datetime.now()
                try:
                    ncfg = await db.get_notify_config()
                except Exception:
                    ncfg = {}

                # Heartbeat для статуса в CRM
                try:
                    await db.set_setting("bot_heartbeat_at", now.strftime("%Y-%m-%d %H:%M:%S"))
                except Exception:
                    pass

                # 1. Напоминание за lead_hours (2h)
                if db.is_notify_enabled(ncfg, "remind_2h"):
                    bookings_2h = db.group_consecutive_slots(await db.get_upcoming_bookings_2h())
                    for b in bookings_2h:
                        tl = b["start_time"] if b["start_time"] == b["end_time"] else f'{b["start_time"]} – {b["end_time"]}'
                        tmpl = (ncfg.get("remind_2h") or {}).get("template") or ""
                        text = db.render_notify_template(tmpl, {
                            "master_name": b.get("master_name", ""),
                            "time": tl,
                            "date": b.get("date", ""),
                            "client_name": b.get("client_name", ""),
                        }) or (
                            f"⏰ *Напоминание*\n\n"
                            f"Через 2 часа у вас запись!\n"
                            f"Мастер: {b['master_name']}\n"
                            f"Время: {tl}\n\n"
                            f"Ждём вас!"
                        )
                        await tg_send(b["telegram_id"], text)
                        await db.db_mark_reminders_sent(b["ids"], "reminder_2h_sent")
                        log.info(f"REMINDER: 2h sent to {b['client_name']} ({b['telegram_id']}) slots={len(b['ids'])}")

                # 2. Напоминание за lead_hours (24h)
                if db.is_notify_enabled(ncfg, "remind_24h"):
                    bookings_24h = db.group_consecutive_slots(await db.get_upcoming_bookings(hours_ahead=24))
                    for b in bookings_24h:
                        tl = b["start_time"] if b["start_time"] == b["end_time"] else f'{b["start_time"]} – {b["end_time"]}'
                        tmpl = (ncfg.get("remind_24h") or {}).get("template") or ""
                        text = db.render_notify_template(tmpl, {
                            "master_name": b.get("master_name", ""),
                            "time": tl,
                            "date": b.get("date", ""),
                            "client_name": b.get("client_name", ""),
                        }) or (
                            f"📅 *Напоминание о записи*\n\n"
                            f"Завтра у вас запись:\n"
                            f"Мастер: {b['master_name']}\n"
                            f"Время: {tl}\n\n"
                            f"Подтвердите или отмените запись:"
                        )
                        kb = {"inline_keyboard": [
                            [{"text": "✅ Подтвердить", "callback_data": f"remind_confirm_{b['id']}"}],
                            [{"text": "❌ Отменить", "callback_data": f"remind_cancel_{b['id']}"}],
                        ]}
                        await tg_send(b["telegram_id"], text, reply_markup=kb)
                        await db.db_mark_reminders_sent(b["ids"], "reminder_sent")
                        log.info(f"REMINDER: 24h sent to {b['client_name']} ({b['telegram_id']}) slots={len(b['ids'])}")

                # 3. Запрос оценки (вчерашние записи, quiet hours из notify_config)
                review_cfg = ncfg.get("review") or {}
                review_qs = int(review_cfg.get("quiet_start", 9))
                review_qe = int(review_cfg.get("quiet_end", 21))
                if (config.RATING_ENABLED and db.is_notify_enabled(ncfg, "review")
                        and review_qs <= now.hour < review_qe):
                    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
                    async with aiosqlite.connect(config.DB_PATH) as adb:
                        adb.row_factory = aiosqlite.Row
                        cur = await adb.execute(
                            "SELECT * FROM bookings WHERE date = ? AND confirmed = 1 AND telegram_id > 0 AND review_sent = 0",
                            (yesterday,),
                        )
                        completed = db.group_consecutive_slots([dict(r) for r in await cur.fetchall()])
                    for b in completed:
                        tl = b["start_time"] if b["start_time"] == b["end_time"] else f'{b["start_time"]} – {b["end_time"]}'
                        tmpl = (review_cfg or {}).get("template") or ""
                        text = db.render_notify_template(tmpl, {
                            "master_name": b.get("master_name", ""),
                            "time": tl,
                            "date": b.get("date", ""),
                            "client_name": b.get("client_name", ""),
                        }) or (
                            f"⭐ *Как прошла ваша запись?*\n\n"
                            f"Мастер: {b['master_name']}\n"
                            f"Дата: {b['date']}\n"
                            f"Время: {tl}\n\n"
                            f"Пожалуйста, оцените обслуживание от 1 до 5 звёзд:"
                        )
                        stars_kb = {"inline_keyboard": [
                            [{"text": "⭐", "callback_data": f"review_s_{b['id']}_1"}],
                            [{"text": "⭐⭐", "callback_data": f"review_s_{b['id']}_2"}],
                            [{"text": "⭐⭐⭐", "callback_data": f"review_s_{b['id']}_3"}],
                            [{"text": "⭐⭐⭐⭐", "callback_data": f"review_s_{b['id']}_4"}],
                            [{"text": "⭐⭐⭐⭐⭐", "callback_data": f"review_s_{b['id']}_5"}],
                        ]}
                        try:
                            await tg_send(b["telegram_id"], text, reply_markup=stars_kb)
                            await db.db_mark_reminders_sent(b["ids"], "review_sent")
                            log.info(f"REVIEW: sent to {b['client_name']} ({b['telegram_id']}) slots={len(b['ids'])}")
                        except Exception as e:
                            log.warning(f"REVIEW: error {b['telegram_id']}: {e}")

                    # Автоочистка ОТКЛЮЧЕНА (24.08.2026): история записей больше не удаляется.
                    # Ранее здесь удалялись записи старше 2 дней с отправленным запросом оценки,
                    # из-за чего пропадали старые записи в CRM.

                # 4. Автозакрытие прошедших записей
                closed = await db.auto_close_bookings()
                if closed:
                    log.info(f"REMINDER: auto-closed {closed} записей")

                # 5. Поздравления с днём рождения (раз в сутки, quiet hours из notify_config)
                bday_cfg = ncfg.get("birthday") or {}
                bday_qs = int(bday_cfg.get("quiet_start", 10))
                bday_qe = int(bday_cfg.get("quiet_end", 21))
                if (config.BIRTHDAY_DISCOUNT and db.is_notify_enabled(ncfg, "birthday")
                        and bday_qs <= now.hour < bday_qe
                        and _last_birthday_run["date"] != now.strftime("%Y-%m-%d")):
                    _last_birthday_run["date"] = now.strftime("%Y-%m-%d")
                    await check_birthdays(app.bot)

            except Exception as e:
                log.error(f"REMINDER_LOOP error: {e}")
            await asyncio.sleep(300)

    asyncio.create_task(reminder_loop())

    # Load offset from file to avoid losing updates on restart
    offset_file = os.path.join(os.path.dirname(__file__), ".polling_offset")
    offset = 0
    if os.path.exists(offset_file):
        try:
            with open(offset_file, "r") as f:
                offset = int(f.read().strip())
            log.info(f"POLLING: loaded offset={offset} from file")
        except:
            pass
    log.info("Polling loop started")

    while True:
        try:
            url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/getUpdates"
            params = {"offset": offset, "timeout": 30}
            log.info(f"POLLING: getUpdates offset={offset}")
            resp = await http_client.get(url, params=params)
            data = resp.json()

            if not data.get("ok"):
                log.error(f"POLLING: API error: {data}")
                await asyncio.sleep(5)
                continue

            updates = data.get("result", [])
            if updates:
                log.info(f"POLLING: received {len(updates)} updates")
                for update_data in updates:
                    try:
                        from telegram import Update
                        update = Update.de_json(update_data, app.bot)
                        await app.process_update(update)
                        offset = update.update_id + 1
                        # Save offset to file to survive restarts
                        try:
                            with open(offset_file, "w") as f:
                                f.write(str(offset))
                        except:
                            pass
                    except Exception as e:
                        log.error(f"POLLING: error processing update: {e}", exc_info=True)
            else:
                log.debug("POLLING: no updates")

        except httpx.TimeoutException:
            log.warning("POLLING: timeout (normal for long-poll)")
        except httpx.ConnectError as e:
            log.error(f"POLLING: connection error: {e}")
            await asyncio.sleep(5)
        except Exception as e:
            log.error(f"POLLING: unexpected error: {e}", exc_info=True)
            await asyncio.sleep(5)


def main():
    app = build_application()
    log.info("Бот запускается...")

    # Initialize without polling
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def run():
        await app.initialize()
        # post_init из builder НЕ вызывается при ручном initialize() —
        # миграции вызываем явно, иначе db.init() на проде не выполняется
        log.info("POST_INIT: started")
        await db.init()
        log.info("POST_INIT: db.init done")
        await app.start()
        await polling_loop(app)

    try:
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        log.info("Bot stopped by user")
    finally:
        loop.run_until_complete(app.shutdown())
        loop.close()


if __name__ == "__main__":
    main()
