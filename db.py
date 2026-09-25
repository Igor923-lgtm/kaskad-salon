"""Локальная база данных — клиенты, мастера, записи, скидки, отзывы, расписание.
Основное хранилище для Telegram-бота и CRM (api.py)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import aiosqlite
import config

log = logging.getLogger(__name__)

# Кэш salon_settings в памяти процесса — снимает CREATE TABLE + connect с hot path (p95)
_settings_cache = None  # type: dict | None
_settings_cache_ts = 0.0  # monotonic; TTL для кросс-процессной свежести (API ↔ bot)
_settings_ready = False
_SETTINGS_TTL_SEC = 5.0


async def _apply_sqlite_pragmas(db):
    try:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA busy_timeout=5000")
    except Exception:
        pass


async def init():
    async with aiosqlite.connect(config.DB_PATH) as db:
        await _apply_sqlite_pragmas(db)
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS clients (
                telegram_id INTEGER PRIMARY KEY,
                contact_id INTEGER NOT NULL,
                name TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                client_type TEXT DEFAULT 'lead',
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS masters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                specialization TEXT DEFAULT '',
                photo_file_id TEXT DEFAULT '',
                description TEXT DEFAULT '',
                categories TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS content (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS discounts (
                contact_id INTEGER PRIMARY KEY,
                percent INTEGER DEFAULT 0,
                visit_count INTEGER DEFAULT 0,
                discount_expires TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                master_name TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                client_name TEXT DEFAULT '',
                telegram_id INTEGER DEFAULT 0,
                external_id INTEGER DEFAULT 0,
                reminder_sent INTEGER DEFAULT 0,
                reminder_2h_sent INTEGER DEFAULT 0,
                reminder_repeat_sent INTEGER DEFAULT 0,
                review_sent INTEGER DEFAULT 0,
                confirmed INTEGER DEFAULT 0,
                duration_minutes INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS master_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                master_name TEXT NOT NULL,
                day_of_week INTEGER NOT NULL,
                start_time TEXT DEFAULT '10:00',
                end_time TEXT DEFAULT '20:00',
                is_day_off INTEGER DEFAULT 0,
                UNIQUE(master_name, day_of_week)
            );

            CREATE TABLE IF NOT EXISTS master_date_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                master_name TEXT NOT NULL,
                date TEXT NOT NULL,
                time_slots TEXT NOT NULL DEFAULT '',
                is_day_off INTEGER DEFAULT 0,
                UNIQUE(master_name, date)
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                master_name TEXT NOT NULL,
                client_name TEXT DEFAULT '',
                score INTEGER DEFAULT 5,
                comment TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_title TEXT NOT NULL,
                category_note TEXT DEFAULT '',
                category_index INTEGER NOT NULL,
                service_index INTEGER NOT NULL,
                name TEXT NOT NULL,
                price TEXT NOT NULL DEFAULT '',
                gender TEXT DEFAULT 'all',
                sort_order INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                duration_minutes INTEGER DEFAULT 0,
                UNIQUE(category_index, service_index)
            );

            CREATE TABLE IF NOT EXISTS booking_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                name TEXT DEFAULT '',
                price TEXT DEFAULT '',
                duration_minutes INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS waitlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                master_name TEXT DEFAULT '',
                date_pref TEXT DEFAULT '',
                service_name TEXT DEFAULT '',
                telegram_id INTEGER DEFAULT 0,
                phone TEXT DEFAULT '',
                duration_minutes INTEGER DEFAULT 0,
                status TEXT DEFAULT 'open',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                percent INTEGER DEFAULT 0,
                max_uses INTEGER DEFAULT 0,
                used INTEGER DEFAULT 0,
                expires_at TEXT DEFAULT '',
                active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS client_tags (
                client_key TEXT NOT NULL,
                tag TEXT NOT NULL,
                PRIMARY KEY (client_key, tag)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT DEFAULT '',
                action TEXT DEFAULT '',
                entity TEXT DEFAULT '',
                entity_id TEXT DEFAULT '',
                detail TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()

        # Migration: add review_sent column if missing
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN review_sent INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass  # column already exists

        # Migration: add reminder_repeat_sent column if missing
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN reminder_repeat_sent INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass  # column already exists

        # Migration: add phone column to clients if missing
        try:
            await db.execute("ALTER TABLE clients ADD COLUMN phone TEXT DEFAULT ''")
            await db.commit()
        except Exception:
            pass  # column already exists

        # Migration: add selected_hours to master_schedule if missing
        try:
            await db.execute("ALTER TABLE master_schedule ADD COLUMN selected_hours TEXT DEFAULT ''")
            await db.commit()
        except Exception:
            pass

        # Migration: add service_name and price to bookings if missing
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN service_name TEXT DEFAULT ''")
            await db.commit()
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN price TEXT DEFAULT ''")
            await db.commit()
        except Exception:
            pass

        # Client notes table
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS client_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_telegram_id INTEGER NOT NULL,
                author TEXT DEFAULT '',
                text TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()

        # Transactions table for finance tracking
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER DEFAULT 0,
                master_name TEXT DEFAULT '',
                service_name TEXT DEFAULT '',
                amount REAL DEFAULT 0,
                payment_type TEXT DEFAULT 'cash',
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        await db.commit()

        # Migration: add commission_percent to masters if missing
        try:
            await db.execute("ALTER TABLE masters ADD COLUMN commission_percent INTEGER DEFAULT 50")
            await db.commit()
        except Exception:
            pass

        # Migration: add telegram_id to masters if missing
        try:
            await db.execute("ALTER TABLE masters ADD COLUMN telegram_id INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass

        # Migration: add phone to masters if missing
        try:
            await db.execute("ALTER TABLE masters ADD COLUMN phone TEXT DEFAULT ''")
            await db.commit()
        except Exception:
            pass

        # Migration: org_type для фильтра салон/коворкинг
        try:
            await db.execute("ALTER TABLE masters ADD COLUMN org_type TEXT DEFAULT ''")
            await db.commit()
        except Exception:
            pass

        # Migration: add booking_type to bookings for coworking
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN booking_type TEXT DEFAULT 'client'")
            await db.commit()
        except Exception:
            pass

        # Migration: phone для bookings (нужен try_book_slot и /api/clients)
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN phone TEXT DEFAULT ''")
            await db.commit()
        except Exception:
            pass

        # Migration: rename legacy column names in clients
        try:
            await db.execute("ALTER TABLE clients RENAME COLUMN bitrix_contact_id TO contact_id")
            await db.commit()
        except Exception:
            pass

        # Migration: rename legacy column names in bookings
        try:
            await db.execute("ALTER TABLE bookings RENAME COLUMN bitrix_deal_id TO external_id")
            await db.commit()
        except Exception:
            pass

        # Migration: add client_type to clients (lead / client)
        try:
            await db.execute("ALTER TABLE clients ADD COLUMN client_type TEXT DEFAULT 'lead'")
            await db.commit()
        except Exception:
            pass

        # Migration: add birthday to clients
        try:
            await db.execute("ALTER TABLE clients ADD COLUMN birthday TEXT DEFAULT ''")
            await db.commit()
        except Exception:
            pass

        # Migration: add completed flag to bookings
        # (автозакрытие помечает запись completed = 1 вместо удаления — история сохраняется)
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN completed INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass

        # Migration: add cancelled flag to bookings
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN cancelled INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass

        # Migration: add role to masters (super_admin / director / admin / master_view / master_edit)
        try:
            await db.execute("ALTER TABLE masters ADD COLUMN role TEXT DEFAULT 'master_edit'")
            await db.commit()
        except Exception:
            pass

        # Migration: add role to master_sessions
        try:
            await db.execute("ALTER TABLE master_sessions ADD COLUMN role TEXT DEFAULT 'master_edit'")
            await db.commit()
        except Exception:
            pass

        # Migration: длительность услуги (0 = 15 мин по умолчанию)
        try:
            await db.execute("ALTER TABLE services ADD COLUMN duration_minutes INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass

        # Migration: длительность записи (копия услуги на момент брони)
        try:
            await db.execute("ALTER TABLE bookings ADD COLUMN duration_minutes INTEGER DEFAULT 0")
            await db.commit()
        except Exception:
            pass

        # User permissions table (granular access control)
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS user_permissions (
                master_id INTEGER PRIMARY KEY,
                view_clients TEXT DEFAULT 'own',
                edit_bookings TEXT DEFAULT 'own',
                edit_schedule TEXT DEFAULT 'own',
                finance INTEGER DEFAULT 0,
                broadcast INTEGER DEFAULT 0,
                manage_masters INTEGER DEFAULT 0
            );
        """)
        await db.commit()

        await db.commit()

    # Импорт услуг из price_data.py если таблица пуста
    await import_services_from_price_data()
    # Таблицы self-serve CRM (меню бота / оповещения)
    await init_bot_tables()
    await init_settings_table()
    # Прогреть кэш настроек (p95: без CREATE TABLE на каждом чтении)
    global _settings_cache, _settings_ready
    _settings_ready = True
    try:
        await get_all_settings(force_db=True)
    except Exception as e:
        log.warning(f"settings cache warm failed: {e}")


async def get_client(telegram_id: int) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def save_client(telegram_id: int, contact_id: int, name: str = "", phone: str = ""):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO clients (telegram_id, contact_id, name, phone) VALUES (?, ?, ?, ?)",
            (telegram_id, contact_id, name, phone),
        )
        await db.commit()


async def upsert_client(telegram_id: int, name: str = "", phone: str = ""):
    """Создать или обновить клиента. Не затирает существующие поля пустыми."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,))
        existing = await cur.fetchone()
        if existing:
            new_name = name if name else existing["name"]
            new_phone = phone if phone else existing["phone"]
            await db.execute(
                "UPDATE clients SET name = ?, phone = ?, updated_at = datetime('now') WHERE telegram_id = ?",
                (new_name, new_phone, telegram_id),
            )
        else:
            await db.execute(
                "INSERT INTO clients (telegram_id, contact_id, name, phone, client_type) VALUES (?, ?, ?, ?, 'lead')",
                (telegram_id, telegram_id, name, phone),
            )
        await db.commit()


async def promote_to_client(telegram_id: int):
    """Перевести лида в статус 'client' (записался)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE clients SET client_type = 'client', updated_at = datetime('now') WHERE telegram_id = ? AND client_type != 'client'",
            (telegram_id,),
        )
        await db.commit()


async def get_leads() -> list:
    """Вернуть всех лидов (нажали /start, но не записались)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM clients WHERE client_type = 'lead' ORDER BY updated_at DESC"
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_booked_clients() -> list:
    """Вернуть всех клиентов (записались хотя бы раз)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM clients WHERE client_type = 'client' ORDER BY updated_at DESC"
        )
        return [dict(r) for r in await cur.fetchall()]


async def update_client_phone(telegram_id: int, phone: str):
    if not phone.startswith("+"):
        phone = "+" + phone
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE clients SET phone = ?, updated_at = datetime('now') WHERE telegram_id = ?",
            (phone, telegram_id),
        )
        await db.commit()


async def get_masters(org_type: str | None = None) -> list:
    """Активные мастера. org_type: фильтр по типу организации (пустой org_type у мастера = показывать всем)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM masters WHERE is_active = 1 AND phone != ? ORDER BY name",
            (config.SUPERADMIN_PHONE,),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    if org_type:
        rows = [
            m for m in rows
            if not (m.get("org_type") or "").strip() or (m.get("org_type") or "").strip() == org_type
        ]
    return rows


async def get_master_by_id(master_id: int) -> dict | None:
    """Получить мастера по ID."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM masters WHERE id = ? AND is_active = 1", (master_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_masters_by_category(category_idx: int, org_type: str | None = None) -> list:
    """Вернуть мастеров, которые работают в указанной категории (индекс раздела прайса)."""
    all_masters = await get_masters(org_type=org_type)
    result = []
    for m in all_masters:
        cats = m.get("categories", "")
        if not cats:
            result.append(m)
            continue
        cat_list = [int(c.strip()) for c in cats.split(",") if c.strip().isdigit()]
        if category_idx in cat_list:
            result.append(m)
    return result


async def add_master(name: str, specialization: str = "", photo_file_id: str = "",
                     description: str = "", categories: str = "", org_type: str = ""):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO masters (name, specialization, photo_file_id, description, categories, org_type) VALUES (?, ?, ?, ?, ?, ?)",
            (name, specialization, photo_file_id, description, categories, org_type),
        )
        await db.commit()


async def delete_master(master_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE masters SET is_active = 0 WHERE id = ?", (master_id,))
        await db.commit()


async def update_master_photo(master_id: int, photo_file_id: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE masters SET photo_file_id = ? WHERE id = ?", (photo_file_id, master_id))
        await db.commit()


async def get_content(key: str) -> str:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT value FROM content WHERE key = ?", (key,))
        row = await cur.fetchone()
        return row[0] if row else ""


async def set_content(key: str, value: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO content (key, value) VALUES (?, ?)", (key, value))
        await db.commit()


async def get_discount(contact_id: int) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT percent FROM discounts WHERE contact_id = ?", (contact_id,))
        row = await cur.fetchone()
        return row[0] if row else 0


async def set_discount(contact_id: int, percent: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO discounts (contact_id, percent) VALUES (?, ?)",
            (contact_id, percent),
        )
        await db.commit()


async def get_visit_count(contact_id: int) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT visit_count FROM discounts WHERE contact_id = ?", (contact_id,))
        row = await cur.fetchone()
        return row[0] if row else 0


async def get_all_client_ids() -> list[int]:
    """Вернуть все telegram_id клиентов."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT telegram_id FROM clients")
        rows = await cur.fetchall()
        return [r[0] for r in rows]


async def set_review_discount(contact_id: int, percent: int = 10, days: int = 50):
    """Установить скидку за отзыв (привязана к contact_id, действует days дней)."""
    from datetime import datetime, timedelta
    expires = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO discounts (contact_id, percent, discount_expires)
               VALUES (?, ?, ?)
               ON CONFLICT(contact_id) DO UPDATE SET
                   percent = MAX(percent, ?),
                   discount_expires = CASE
                       WHEN ? > COALESCE(discount_expires, '') THEN ?
                       ELSE discount_expires
                   END""",
            (contact_id, percent, expires, percent, expires, expires),
        )
        await db.commit()


async def get_review_discount(contact_id: int) -> dict:
    """Проверить скидку за отзыв. Вернуть {percent, expires, is_valid}."""
    from datetime import datetime
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT percent, discount_expires FROM discounts WHERE contact_id = ?",
            (contact_id,),
        )
        row = await cur.fetchone()
        if not row:
            return {"percent": 0, "expires": "", "is_valid": False}
        percent, expires = row[0], row[1] or ""
        if expires:
            exp_date = datetime.strptime(expires, "%Y-%m-%d")
            is_valid = exp_date >= datetime.now()
        else:
            is_valid = False
        return {"percent": percent, "expires": expires, "is_valid": is_valid}


async def get_completed_visits_for_review() -> list:
    """Вернуть завершённые сделки (WON), по которым ещё нет отзыва."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE confirmed = 1")
        return [dict(r) for r in await cur.fetchall()]


async def mark_reviewed(booking_id: int):
    """Пометить запись как отценённую (удалить)."""
    await cancel_booking(booking_id)


async def get_booked_times(master_name: str, date: str) -> list[str]:
    """Вернуть список занятых времён для мастера на дату."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT time FROM bookings WHERE master_name = ? AND date = ?",
            (master_name, date),
        )
        return [r[0] for r in await cur.fetchall()]


async def get_booking_services(booking_id: int) -> list[dict]:
    """Услуги, привязанные к записи (может быть пусто для legacy)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT service_id, name, price, duration_minutes FROM booking_services WHERE booking_id = ? ORDER BY id",
            (booking_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def set_booking_services(booking_id: int, items: list[dict]) -> None:
    """Заменить список услуг записи."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM booking_services WHERE booking_id = ?", (booking_id,))
        for it in items:
            await db.execute(
                """INSERT INTO booking_services (booking_id, service_id, name, price, duration_minutes)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    booking_id,
                    int(it.get("service_id") or 0),
                    str(it.get("name") or ""),
                    str(it.get("price") or ""),
                    max(0, int(it.get("duration_minutes") or 0)),
                ),
            )
        await db.commit()


async def delete_booking_services_for_booking(booking_id: int):
    await set_booking_services(booking_id, [])


async def resolve_services_by_ids(service_ids: list[int]) -> list[dict]:
    """Загрузить активные услуги по id (порядок как в списке)."""
    if not service_ids:
        return []
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(service_ids))
        cur = await db.execute(
            f"SELECT id, name, price, duration_minutes FROM services WHERE id IN ({placeholders}) AND is_active = 1",
            list(service_ids),
        )
        by_id = {r["id"]: dict(r) for r in await cur.fetchall()}
    return [by_id[i] for i in service_ids if i in by_id]


async def add_waitlist(master_name: str, date_pref: str, service_name: str,
                       telegram_id: int = 0, phone: str = "",
                       duration_minutes: int = 0) -> int:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO waitlist (master_name, date_pref, service_name, telegram_id, phone, duration_minutes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (master_name, date_pref, service_name, telegram_id, phone, max(0, int(duration_minutes or 0))),
        )
        await db.commit()
        return cur.lastrowid


async def list_open_waitlist(master_name: str = "", date_pref: str = "") -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM waitlist WHERE status = 'open'"
        p: list = []
        if master_name:
            q += " AND (master_name = ? OR master_name = '')"
            p.append(master_name)
        if date_pref:
            q += " AND (date_pref = ? OR date_pref = '')"
            p.append(date_pref)
        q += " ORDER BY created_at"
        cur = await db.execute(q, p)
        return [dict(r) for r in await cur.fetchall()]


async def close_waitlist(waitlist_id: int, status: str = "notified"):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE waitlist SET status = ? WHERE id = ?", (status, waitlist_id))
        await db.commit()


async def notify_waitlist_for_slot(master_name: str, date: str, time: str) -> list[dict]:
    """Подобрать открытых из waitlist под освободившееся окно и пометить notified.
    Возвращает rows для реальной отправки (chat_id = telegram_id)."""
    rows = await list_open_waitlist()
    matched = []
    for r in rows:
        if r.get("master_name") and r["master_name"] != master_name:
            continue
        if r.get("date_pref") and r["date_pref"] != date:
            continue
        if not r.get("telegram_id"):
            continue
        await close_waitlist(r["id"], "notified")
        matched.append(r)
    return matched


async def log_audit(actor: str, action: str, entity: str, entity_id: str, detail: str = ""):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO audit_log (actor, action, entity, entity_id, detail) VALUES (?, ?, ?, ?, ?)",
            (actor, action, entity, entity_id, detail[:500]),
        )
        await db.commit()


async def get_promo(code: str) -> dict | None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM promo_codes WHERE UPPER(code) = UPPER(?) AND active = 1",
            (code.strip(),),
        )
        row = await cur.fetchone()
        if not row:
            return None
        p = dict(row)
        if p.get("expires_at") and p["expires_at"] < datetime.now().strftime("%Y-%m-%d"):
            return None
        if p.get("max_uses") and p.get("used", 0) >= p["max_uses"]:
            return None
        return p


async def use_promo(code: str) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "UPDATE promo_codes SET used = used + 1 WHERE UPPER(code) = UPPER(?) AND active = 1 "
            "AND (max_uses = 0 OR used < max_uses)",
            (code.strip(),),
        )
        await db.commit()
        return cur.rowcount > 0


async def list_tags(client_key: str) -> list[str]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT tag FROM client_tags WHERE client_key = ?", (client_key,))
        return [r[0] for r in await cur.fetchall()]


async def set_tags(client_key: str, tags: list[str]):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM client_tags WHERE client_key = ?", (client_key,))
        for t in tags:
            t = (t or "").strip()
            if t:
                await db.execute(
                    "INSERT OR IGNORE INTO client_tags (client_key, tag) VALUES (?, ?)",
                    (client_key, t),
                )
        await db.commit()


async def add_booking(master_name: str, date: str, time: str, client_name: str = "",
                      telegram_id: int = 0, external_id: int = 0):
    """Сохранить бронирование."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO bookings (master_name, date, time, client_name, telegram_id, external_id) VALUES (?, ?, ?, ?, ?, ?)",
            (master_name, date, time, client_name, telegram_id, external_id),
        )
        await db.commit()
        return cur.lastrowid


# ── Блокировка для атомарного бронирования ──
_booking_locks = {}
_booking_locks_lock = asyncio.Lock()

async def _get_booking_lock(master_name: str, date: str, time: str = "") -> asyncio.Lock:
    """Получить блокировку на мастер+дату (время не участвует: окно может начинаться в любой слот)."""
    key = f"{master_name}|{date}"
    async with _booking_locks_lock:
        if key not in _booking_locks:
            _booking_locks[key] = asyncio.Lock()
        return _booking_locks[key]


def slots_needed(duration_minutes: int | None) -> int:
    """Сколько 15-мин слотов занимает длительность. 0/None → 1 слот."""
    try:
        d = int(duration_minutes or 0)
    except (TypeError, ValueError):
        return 1
    if d <= 0:
        return 1
    return (d + 14) // 15


def occupied_times_for_booking(b: dict) -> set[str]:
    """Все HH:MM, которые покрывает запись (старт + i*15)."""
    start = b.get("time") or ""
    if not start:
        return set()
    return { _add_minutes(start, i * 15) for i in range(slots_needed(b.get("duration_minutes"))) }


def end_time_for_booking(start: str, duration_minutes: int | None) -> str:
    """Конец окна записи для отображения."""
    if not start:
        return ""
    return _add_minutes(start, slots_needed(duration_minutes) * 15)


def format_duration(duration_minutes: int | None) -> str:
    """0/None → '15 мин'; 90 → '1 ч 30 мин'; 120 → '2 ч'."""
    d = slots_needed(duration_minutes) * 15
    if d < 60:
        return f"{d} мин"
    h, m = divmod(d, 60)
    return f"{h} ч" if m == 0 else f"{h} ч {m} мин"


def window_is_free(start: str, duration_minutes: int | None,
                   working_slots: list[str] | set[str],
                   occupied: set[str]) -> bool:
    """Окно [start, start+dur) свободно: все слоты окна есть в рабочих и не заняты."""
    if not start:
        return False
    working = set(working_slots)
    for t in occupied_times_for_booking({"time": start, "duration_minutes": duration_minutes}):
        if t not in working or t in occupied:
            return False
    return True


async def get_buffer_minutes() -> int:
    """Буфер после каждой записи (salon-wide, минуты). 0 = выключен."""
    raw = await get_setting("buffer_minutes", str(getattr(config, "BUFFER_MINUTES", 0) or 0))
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0


def _with_buffer(occupied: set[str], end_time: str, buffer_minutes: int) -> set[str]:
    """Добавить buffer_minutes слотов начиная с end_time (первый свободный слот после окна)."""
    if buffer_minutes <= 0 or not end_time:
        return occupied
    n = slots_needed(buffer_minutes)
    out = set(occupied)
    # end_time — уже первый HH:MM после записи; buffer occupies [end, end+n*15)
    for i in range(n):
        out.add(_add_minutes(end_time, i * 15))
    return out


def _occupied_with_buffer(b: dict, buffer_minutes: int) -> set[str]:
    """Все HH:MM записи + trailing buffer."""
    base = occupied_times_for_booking(b)
    if buffer_minutes <= 0 or not base:
        return base
    end = end_time_for_booking(b.get("time") or "", b.get("duration_minutes"))
    return _with_buffer(base, end, buffer_minutes)


async def try_book_slot(master_name: str, date: str, time: str, client_name: str = "",
                        telegram_id: int = 0, external_id: int = 0, service_name: str = "", price: str = "",
                        phone: str = "", booking_type: str = "client", duration_minutes: int = 0) -> int | None:
    """Атомарная проверка окна + бронирование одной строкой. Возвращает ID или None если окно занято."""
    lock = await _get_booking_lock(master_name, date, time)
    async with lock:
        needed = occupied_times_for_booking({"time": time, "duration_minutes": duration_minutes})
        buffer_minutes = await get_buffer_minutes()
        async with aiosqlite.connect(config.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT id, time, duration_minutes FROM bookings WHERE master_name = ? AND date = ?",
                (master_name, date),
            )
            rows = await cur.fetchall()
            occupied: set[str] = set()
            for r in rows:
                occupied |= _occupied_with_buffer(dict(r), buffer_minutes)
            if needed & occupied:
                return None  # Окно пересекается с записью или её буфером

            cur = await db.execute(
                """INSERT INTO bookings (master_name, date, time, client_name, telegram_id, external_id,
                                         service_name, price, phone, booking_type, duration_minutes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (master_name, date, time, client_name, telegram_id, external_id,
                 service_name, price, phone, booking_type, max(0, int(duration_minutes or 0))),
            )
            await db.commit()
            return cur.lastrowid


async def get_occupied_times(master_name: str, date: str, exclude_id: int | None = None) -> set[str]:
    """Все занятые HH:MM мастера на дату: длительность записей + salon buffer."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT time, duration_minutes FROM bookings WHERE master_name = ? AND date = ?"
        params: list = [master_name, date]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        cur = await db.execute(sql, params)
        rows = await cur.fetchall()
        buffer_minutes = await get_buffer_minutes()
        occupied: set[str] = set()
        for r in rows:
            occupied |= _occupied_with_buffer(dict(r), buffer_minutes)
        return occupied


def slots_between(start_time: str, end_time: str) -> list[str]:
    """Слоты 15 мин в интервале [start, end) — как в block_coworking."""
    sh, sm = map(int, start_time.split(":"))
    eh, em = map(int, end_time.split(":"))
    slots = []
    h, m = sh, sm
    while (h, m) < (eh, em):
        slots.append(f"{h:02d}:{m:02d}")
        m += 15
        if m >= 60:
            h += 1
            m = 0
    if not slots and start_time == end_time:
        slots = [start_time]
    return slots


def _add_minutes(t: str, mins: int) -> str:
    h, m = map(int, t.split(":"))
    total = h * 60 + m + mins
    return f"{(total // 60) % 24:02d}:{(total % 60):02d}"


def group_consecutive_slots(rows: list) -> list:
    """Сгруппировать подряд идущие 15-мин слоты одного клиента → один range.

    key: (telegram_id, master_name, date, service_name).
    Возвращает dict'ы с start_time, end_time (= последний слот + 15 мин), ids=[...].
    """
    if not rows:
        return []
    by_key: dict = {}
    for r in rows:
        key = (
            r.get("telegram_id"),
            r.get("master_name"),
            r.get("date"),
            r.get("service_name") or "",
        )
        by_key.setdefault(key, []).append(r)

    groups: list = []
    for key_rows in by_key.values():
        key_rows.sort(key=lambda r: r.get("time") or "")
        cur: list = [key_rows[0]]
        for r in key_rows[1:]:
            prev_t = cur[-1].get("time") or ""
            if r.get("time") == _add_minutes(prev_t, 15):
                cur.append(r)
            else:
                groups.append(cur)
                cur = [r]
        groups.append(cur)

    out: list = []
    for g in groups:
        first = dict(g[0])
        first["start_time"] = g[0].get("time") or ""
        last_t = g[-1].get("time") or ""
        # Одиночная запись с длительностью — конец по duration_minutes, иначе последний слот + 15
        if len(g) == 1 and (g[0].get("duration_minutes") or 0) > 0:
            first["end_time"] = end_time_for_booking(first["start_time"], g[0].get("duration_minutes"))
        else:
            first["end_time"] = _add_minutes(last_t, 15) if last_t else ""
        first["ids"] = [r["id"] for r in g]
        out.append(first)
    # хронологический порядок для циклов отправки
    out.sort(key=lambda g: (g.get("date") or "", g.get("start_time") or ""))
    return out


def _time_line_from_times(times: list) -> str:
    if not times:
        return "—"
    times = sorted(times)
    if len(times) == 1:
        return times[0]
    return f"{times[0]} – {_add_minutes(times[-1], 15)}"


async def book_range(
    master_name: str,
    date: str,
    start_time: str,
    end_time: str,
    client_name: str = "",
    telegram_id: int = 0,
    service_name: str = "",
    price: str = "",
    phone: str = "",
    booking_type: str = "client",
) -> int:
    """Забронировать диапазон [start, end). Возвращает число слотов (0 = конфликт)."""
    slots = slots_between(start_time, end_time)
    if not slots:
        return 0
    created: list[int] = []
    for slot in slots:
        bid = await try_book_slot(
            master_name=master_name,
            date=date,
            time=slot,
            client_name=client_name,
            telegram_id=telegram_id,
            service_name=service_name,
            price=price,
            phone=phone,
            booking_type=booking_type,
        )
        if bid is None:
            # Откат уже созданных слотов интервала
            async with aiosqlite.connect(config.DB_PATH) as db:
                for cid in created:
                    await db.execute("DELETE FROM bookings WHERE id = ?", (cid,))
                await db.commit()
            return 0
        created.append(bid)
    return len(created)


async def get_booked_times_local(master_name: str, date: str) -> list:
    """Получить занятые времена мастера на дату из локальной БД."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT time FROM bookings WHERE master_name = ? AND date = ?",
            (master_name, date),
        )
        return [row[0] for row in await cur.fetchall()]


async def update_booking_deal_id(booking_id: int, deal_id: int):
    """Обновить deal_id после синхронизации с CRM."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE bookings SET external_id = ? WHERE id = ?",
            (deal_id, booking_id),
        )
        await db.commit()


async def get_upcoming_bookings(hours_ahead: int = 24) -> list:
    """Вернуть бронирования в окне lead_hours ± 10% (до 2ч), которые ещё не напоминали."""
    from datetime import datetime, timedelta
    now = datetime.now()
    try:
        ncfg = await get_notify_config()
        rem = ncfg.get("remind_24h") or {}
        if not rem.get("enabled", 1):
            return []
        lead = float(rem.get("lead_hours", hours_ahead) or hours_ahead)
        quiet_start = int(rem.get("quiet_start", 9))
        quiet_end = int(rem.get("quiet_end", 21))
    except Exception:
        lead, quiet_start, quiet_end = float(hours_ahead), 9, 21
    # Quiet hours: не отправлять вне [quiet_start, quiet_end)
    if quiet_end > quiet_start and not (quiet_start <= now.hour < quiet_end):
        return []
    elif quiet_end <= quiet_start and (quiet_end <= now.hour < quiet_start):
        return []
    tol = max(0.5, lead * 0.1)
    window_start = now + timedelta(hours=lead - tol)
    window_end = now + timedelta(hours=lead + tol)
    start_date = window_start.strftime("%Y-%m-%d")
    start_time = window_start.strftime("%H:%M")
    end_date = window_end.strftime("%Y-%m-%d")
    end_time = window_end.strftime("%H:%M")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if start_date == end_date:
            # Окно в пределах одного дня
            cur = await db.execute(
                """SELECT * FROM bookings
                   WHERE date = ? AND time >= ? AND time <= ?
                   AND reminder_sent = 0 AND telegram_id > 0""",
                (start_date, start_time, end_time),
            )
        else:
            # Окно через полночь (например, 14:00 сегодня → 16:00 завтра)
            cur = await db.execute(
                """SELECT * FROM bookings
                   WHERE reminder_sent = 0 AND telegram_id > 0
                   AND (
                       (date = ? AND time >= ?)
                       OR (date = ? AND time <= ?)
                   )""",
                (start_date, start_time, end_date, end_time),
            )
        return [dict(r) for r in await cur.fetchall()]


async def mark_reminder_sent(booking_id: int):
    await db_mark_reminders_sent([booking_id], "reminder_sent")


async def mark_reminder_2h_sent(booking_id: int):
    await db_mark_reminders_sent([booking_id], "reminder_2h_sent")


async def mark_review_sent(booking_id: int):
    await db_mark_reminders_sent([booking_id], "review_sent")


async def mark_reminder_repeat_sent(booking_id: int):
    await db_mark_reminders_sent([booking_id], "reminder_repeat_sent")


async def db_mark_reminders_sent(booking_ids: list, column: str):
    """Пометить флаг (reminder_sent / reminder_2h_sent / ...) для списка id."""
    if not booking_ids:
        return
    allowed = {"reminder_sent", "reminder_2h_sent", "reminder_repeat_sent", "review_sent"}
    if column not in allowed:
        raise ValueError(f"unsupported column: {column}")
    marks = ",".join("?" * len(booking_ids))
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            f"UPDATE bookings SET {column} = 1 WHERE id IN ({marks})",
            tuple(booking_ids),
        )
        await db.commit()


async def confirm_booking_by_deal(deal_id: int):
    """Подтвердить запись при смене статуса сделки на WON."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "UPDATE bookings SET confirmed = 1 WHERE external_id = ? AND confirmed = 0",
            (deal_id,),
        )
        await db.commit()
        return cur.rowcount > 0


async def get_upcoming_bookings_2h() -> list:
    """Вернуть бронирования в окне lead_hours remind_2h ± 10 мин и ещё не напоминали."""
    from datetime import datetime, timedelta
    now = datetime.now()
    try:
        ncfg = await get_notify_config()
        rem = ncfg.get("remind_2h") or {}
        if not rem.get("enabled", 1):
            return []
        lead = float(rem.get("lead_hours", 2) or 2)
        quiet_start = int(rem.get("quiet_start", 0))
        quiet_end = int(rem.get("quiet_end", 24))
    except Exception:
        lead, quiet_start, quiet_end = 2.0, 0, 24
    if quiet_end > quiet_start and not (quiet_start <= now.hour < quiet_end):
        return []
    elif quiet_end <= quiet_start and (quiet_end <= now.hour < quiet_start):
        return []
    # Окно: от now+(lead-10m) до now+(lead+10m)
    window_start = now + timedelta(hours=lead) - timedelta(minutes=10)
    window_end = now + timedelta(hours=lead) + timedelta(minutes=10)
    start_time = window_start.strftime("%H:%M")
    end_time = window_end.strftime("%H:%M")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if window_start.date() == window_end.date():
            # Окно в пределах одного дня
            target_date = window_start.strftime("%Y-%m-%d")
            cur = await db.execute(
                """SELECT * FROM bookings
                   WHERE date = ? AND time >= ? AND time < ?
                   AND reminder_2h_sent = 0 AND telegram_id > 0""",
                (target_date, start_time, end_time),
            )
        else:
            # Окно через полночь (например, 23:00 → 01:30)
            date1 = window_start.strftime("%Y-%m-%d")
            date2 = window_end.strftime("%Y-%m-%d")
            cur = await db.execute(
                """SELECT * FROM bookings
                   WHERE reminder_2h_sent = 0 AND telegram_id > 0
                   AND (
                       (date = ? AND time >= ?)
                       OR
                       (date = ? AND time < ?)
                   )""",
                (date1, start_time, date2, end_time),
            )
        return [dict(r) for r in await cur.fetchall()]


async def confirm_booking(booking_id: int):
    await confirm_bookings([booking_id])


async def cancel_booking(booking_id: int):
    await cancel_bookings([booking_id])


async def confirm_bookings(booking_ids: list):
    if not booking_ids:
        return
    marks = ",".join("?" * len(booking_ids))
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            f"UPDATE bookings SET confirmed = 1 WHERE id IN ({marks})",
            tuple(booking_ids),
        )
        await db.commit()


async def cancel_bookings(booking_ids: list):
    if not booking_ids:
        return
    marks = ",".join("?" * len(booking_ids))
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            f"DELETE FROM bookings WHERE id IN ({marks})",
            tuple(booking_ids),
        )
        await db.execute(
            f"DELETE FROM booking_services WHERE booking_id IN ({marks})",
            tuple(booking_ids),
        )
        await db.commit()


async def get_range_ids_for_booking(booking_id: int) -> list:
    """Соседние 15-мин слоты того же клиента/мастера/даты/услуги (весь range)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        row = await cur.fetchone()
        if not row:
            return [booking_id]
        b = dict(row)
        cur = await db.execute(
            """SELECT * FROM bookings
               WHERE telegram_id = ? AND master_name = ? AND date = ?
                 AND COALESCE(service_name, '') = COALESCE(?, '')
               ORDER BY time""",
            (
                b.get("telegram_id") or 0,
                b.get("master_name") or "",
                b.get("date") or "",
                b.get("service_name") or "",
            ),
        )
        rows = [dict(r) for r in await cur.fetchall()]
        if not rows:
            return [booking_id]
        groups = group_consecutive_slots(rows)
        for g in groups:
            if booking_id in g["ids"]:
                return g["ids"]
        return [booking_id]


async def save_booking_mapping(telegram_id: int, ext_id: int, master_name: str, service_name: str, date: str, time: str):
    """Сохранить маппинг Telegram ID → запись."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO bookings (master_name, date, time, client_name, telegram_id, external_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (master_name, date, time, service_name, telegram_id, ext_id),
        )
        await db.commit()


async def get_bookings_by_telegram_id(telegram_id: int) -> list:
    """Получить записи клиента по Telegram ID."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT * FROM bookings WHERE telegram_id = ? ORDER BY date DESC, time DESC LIMIT 10""",
            (telegram_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_active_bookings(telegram_id: int) -> list:
    """Будущие записи клиента (дата >= сегодня), по времени ASC."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT * FROM bookings WHERE telegram_id = ? AND date >= ? ORDER BY date, time""",
            (telegram_id, today),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_booking_by_id(booking_id: int) -> dict | None:
    """Получить запись по ID."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def can_modify_booking(booking_id: int) -> bool:
    """True если до записи > 2 часов (можно изменить)."""
    from datetime import datetime
    booking = await get_booking_by_id(booking_id)
    if not booking:
        return False
    try:
        booking_dt = datetime.strptime(f"{booking['date']} {booking['time']}", "%Y-%m-%d %H:%M")
        hours_until = (booking_dt - datetime.now()).total_seconds() / 3600
        return hours_until > 2
    except Exception:
        return False


# ── График мастеров ──────────────────────────────────────

DAYS_OF_WEEK = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

async def get_master_schedule(master_name: str) -> list:
    """Вернуть расписание мастера на неделю."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM master_schedule WHERE master_name = ? ORDER BY day_of_week",
            (master_name,),
        )
        return [dict(r) for r in await cur.fetchall()]


def get_salon_slots(dow: int) -> list[str]:
    """Вернуть слоты салона для дня недели (с шагом 15 мин)."""
    start_h, end_h = config.SALON_HOURS.get(dow, (10, 21))
    slots = []
    for h in range(start_h, end_h):
        for m in (0, 15, 30, 45):
            slots.append(f"{h:02d}:{m:02d}")
    return slots


def _clamp_to_salon(slots: list[str], dow: int) -> list[str]:
    """Обрезать слоты по часам работы салона."""
    start_h, end_h = config.SALON_HOURS.get(dow, (10, 21))
    result = []
    for t in slots:
        h = int(t.split(":")[0])
        if start_h <= h < end_h:
            result.append(t)
    return result


async def get_master_available_hours(master_name: str, date: str, duration_minutes: int = 0) -> list[str]:
    """Вернуть доступные для старта часы мастера (окно услуги целиком свободно и влезает в график)."""
    from datetime import datetime
    dt = datetime.strptime(date, "%Y-%m-%d")
    dow = dt.weekday()  # 0=Пн, 6=Вс

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # 1. Сначала проверяем расписание на конкретную дату
        cur = await db.execute(
            "SELECT * FROM master_date_schedule WHERE master_name = ? AND date = ?",
            (master_name, date),
        )
        date_sched = await cur.fetchone()

        if date_sched:
            if date_sched["is_day_off"]:
                return []
            slots_str = date_sched["time_slots"] or ""
            if slots_str:
                available = [h.strip() for h in slots_str.split(",") if h.strip()]
            else:
                available = []
        else:
            # 2. Если нет кастомного расписания — используем недельное
            cur = await db.execute(
                "SELECT * FROM master_schedule WHERE master_name = ? AND day_of_week = ?",
                (master_name, dow),
            )
            sched = await cur.fetchone()

            if not sched:
                # Нет расписания — рабочий день по умолчанию (часы салона)
                available = get_salon_slots(dow)
            elif sched["is_day_off"]:
                # Явный выходной — слотов нет
                return []
            elif sched["selected_hours"] if "selected_hours" in sched.keys() else "":
                # Если выбраны конкретные часы
                available = [h.strip() for h in sched["selected_hours"].split(",") if h.strip()]
            else:
                # Иначе — диапазон с шагом 15 минут
                start_h = int(sched["start_time"].split(":")[0])
                end_h = int(sched["end_time"].split(":")[0])
                available = []
                for h in range(start_h, end_h):
                    for m in (0, 15, 30, 45):
                        available.append(f"{h:02d}:{m:02d}")

        # Обрезаем по часам салона
        available = _clamp_to_salon(available, dow)

        # Исключаем окна, пересекающиеся с занятыми / выходящие за график
        occupied = await get_occupied_times(master_name, date)
        return [h for h in available if window_is_free(h, duration_minutes, available, occupied)]


async def set_master_schedule(master_name: str, day_of_week: int, start_time: str = "10:00", end_time: str = "20:00", is_day_off: int = 0):
    """Установить расписание мастера на день недели (0=Пн, 6=Вс)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO master_schedule (master_name, day_of_week, start_time, end_time, is_day_off)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(master_name, day_of_week) DO UPDATE SET
               start_time=?, end_time=?, is_day_off=?""",
            (master_name, day_of_week, start_time, end_time, is_day_off,
             start_time, end_time, is_day_off),
        )
        await db.commit()


async def set_master_day_off(master_name: str, day_of_week: int):
    """Установить выходной для мастера."""
    await set_master_schedule(master_name, day_of_week, is_day_off=1)


async def get_date_schedule(master_name: str, date: str) -> dict | None:
    """Получить расписание мастера на конкретную дату."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM master_date_schedule WHERE master_name = ? AND date = ?",
            (master_name, date),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_date_schedule(master_name: str, date: str, time_slots: str, is_day_off: int = 0):
    """Установить расписание мастера на конкретную дату.
    time_slots — строка с временами через запятую: '12:00,15:15,18:30'
    """
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO master_date_schedule (master_name, date, time_slots, is_day_off)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(master_name, date) DO UPDATE SET
               time_slots=?, is_day_off=?""",
            (master_name, date, time_slots, is_day_off, time_slots, is_day_off),
        )
        await db.commit()


async def delete_date_schedule(master_name: str, date: str):
    """Удалить расписание на дату (вернуться к недельному расписанию)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "DELETE FROM master_date_schedule WHERE master_name = ? AND date = ?",
            (master_name, date),
        )
        await db.commit()


async def get_all_date_schedules(master_name: str) -> list:
    """Получить все даты с кастомным расписанием мастера."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM master_date_schedule WHERE master_name = ? ORDER BY date",
            (master_name,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_all_schedules() -> dict:
    """Вернуть расписания всех мастеров."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM master_schedule ORDER BY master_name, day_of_week")
        rows = [dict(r) for r in await cur.fetchall()]
    schedules = {}
    for r in rows:
        name = r["master_name"]
        if name not in schedules:
            schedules[name] = []
        schedules[name].append(r)
    return schedules


# ── Отзывы ──────────────────────────────────────────────

async def add_review(master_name: str, client_name: str, score: int, comment: str = ""):
    """Сохранить отзыв."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO reviews (master_name, client_name, score, comment) VALUES (?, ?, ?, ?)",
            (master_name, client_name, score, comment),
        )
        await db.commit()


async def get_master_reviews(master_name: str) -> list:
    """Вернуть отзывы мастера."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM reviews WHERE master_name = ? ORDER BY created_at DESC",
            (master_name,),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_master_rating(master_name: str) -> dict:
    """Вернуть средний рейтинг мастера."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT AVG(score) as avg_score, COUNT(*) as count FROM reviews WHERE master_name = ?",
            (master_name,),
        )
        row = await cur.fetchone()
        if row and row[1] > 0:
            return {"avg": round(row[0], 1), "count": row[1]}
        return {"avg": 0, "count": 0}



# ── Дополнительные запросы ────────────────────────────────

async def get_reviews(limit: int = 50) -> list:
    """Вернуть последние отзывы."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM reviews ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]


async def get_pending_bookings() -> list:
    """Вернуть неподтверждённые записи."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE confirmed = 0 ORDER BY date, time")
        return [dict(r) for r in await cur.fetchall()]


async def get_all_bookings() -> list:
    """Вернуть все записи."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings ORDER BY date DESC, time DESC")
        return [dict(r) for r in await cur.fetchall()]


async def get_all_clients() -> list:
    """Вернуть всех клиентов (лиды + клиенты)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM clients ORDER BY updated_at DESC")
        return [dict(r) for r in await cur.fetchall()]


async def update_client_name(telegram_id: int, name: str):
    """Обновить имя клиента."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE clients SET name = ?, updated_at = datetime('now') WHERE telegram_id = ?",
            (name, telegram_id),
        )
        await db.commit()


# ══════════════════════════════════════════════════════════
#  Автозакрытие записей + Скидки
# ══════════════════════════════════════════════════════════

async def auto_close_bookings():
    """Закрыть записи, которые начались >2 часов назад. Начислить скидки.
    Записи НЕ удаляются — помечаются completed = 1 (история сохраняется)."""
    from datetime import datetime
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_hour = now.hour

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Находим записи, которые начались >2ч назад, подтверждены и ещё не закрыты
        cur = await db.execute(
            """SELECT * FROM bookings
               WHERE date = ? AND confirmed = 1 AND completed = 0
               AND CAST(SUBSTR(time, 1, 2) AS INTEGER) < ?""",
            (today, current_hour - 2),
        )
        expired = [dict(r) for r in await cur.fetchall()]

        for b in expired:
            telegram_id = b.get("telegram_id", 0)
            if telegram_id > 0:
                # Начисляем скидку 2% за визит
                await increment_visit(telegram_id)

            # Помечаем как завершённую (вместо удаления)
            await db.execute("UPDATE bookings SET completed = 1 WHERE id = ?", (b["id"],))
            log.info(f"AUTO_CLOSE: закрыта запись #{b['id']} {b['master_name']} {b['client_name']}")

        await db.commit()
        return len(expired)


async def increment_visit(telegram_id: int):
    """Начислить визит и скидку (2% за визит, макс 10%, сброс после5)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        # Получаем текущие данные
        cur = await db.execute(
            "SELECT visit_count, percent FROM discounts WHERE contact_id = ?",
            (telegram_id,),
        )
        row = await cur.fetchone()

        if row:
            visits = row[0] + 1
            # После5 визитов — сброс
            if visits > 5:
                visits = 1
            # Скидка: 2% за визит, макс 10%
            discount = min(visits * 2, 10)
            await db.execute(
                "UPDATE discounts SET visit_count = ?, percent = ? WHERE contact_id = ?",
                (visits, discount, telegram_id),
            )
        else:
            await db.execute(
                "INSERT INTO discounts (contact_id, visit_count, percent) VALUES (?, 1, 2)",
                (telegram_id,),
            )
        await db.commit()


async def add_review_discount(telegram_id: int):
    """Добавить скидку за отзыв 5% (действует до следующего посещения)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        # Получаем текущую скидку
        cur = await db.execute(
            "SELECT percent FROM discounts WHERE contact_id = ?",
            (telegram_id,),
        )
        row = await cur.fetchone()
        current = row[0] if row else 0

        # Добавляем 5%, но не больше 10% суммарно
        new_discount = min(current + 5, 10)
        if row:
            await db.execute(
                "UPDATE discounts SET percent = ? WHERE contact_id = ?",
                (new_discount, telegram_id),
            )
        else:
            await db.execute(
                "INSERT INTO discounts (contact_id, visit_count, percent) VALUES (?, 0, 5)",
                (telegram_id,),
            )
        await db.commit()
        return new_discount


async def get_discount_info(telegram_id: int) -> dict:
    """Получить информацию о скидке клиента."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM discounts WHERE contact_id = ?",
            (telegram_id,),
        )
        row = await cur.fetchone()
        if row:
            return dict(row)
        return {"contact_id": telegram_id, "visit_count": 0, "percent": 0}


# ══════════════════════════════════════════════════════════
#  Работа с клиентами: сегменты, потерянные, дни рождения
# ══════════════════════════════════════════════════════════

async def get_lost_clients(days: int = 60) -> list:
    """Клиенты, которые не записывались N дней."""
    from datetime import datetime, timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Клиенты с типом 'client', у которых последняя запись старше cutoff
        cur = await db.execute("""
            SELECT c.*, MAX(b.date) as last_visit
            FROM clients c
            LEFT JOIN bookings b ON c.telegram_id = b.telegram_id
            WHERE c.client_type = 'client' AND c.telegram_id > 0
            GROUP BY c.telegram_id
            HAVING last_visit IS NULL OR last_visit < ?
            ORDER BY last_visit DESC
        """, (cutoff,))
        return [dict(r) for r in await cur.fetchall()]


async def get_new_clients_this_month() -> list:
    """Клиенты, записавшиеся в этом месяце впервые."""
    from datetime import datetime
    month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT DISTINCT c.* FROM clients c
            INNER JOIN bookings b ON c.telegram_id = b.telegram_id
            WHERE c.client_type = 'client' AND b.date >= ?
            AND c.telegram_id NOT IN (
                SELECT DISTINCT telegram_id FROM bookings WHERE date < ?
            )
        """, (month_start, month_start))
        return [dict(r) for r in await cur.fetchall()]


async def get_regular_clients(min_visits: int = 3) -> list:
    """Клиенты с N+ визитами."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT c.*, COUNT(b.id) as visit_count
            FROM clients c
            INNER JOIN bookings b ON c.telegram_id = b.telegram_id
            WHERE c.client_type = 'client' AND c.telegram_id > 0
            GROUP BY c.telegram_id
            HAVING visit_count >= ?
            ORDER BY visit_count DESC
        """, (min_visits,))
        return [dict(r) for r in await cur.fetchall()]


async def get_clients_by_segment(segment: str) -> list:
    """Вернуть клиентов по сегменту: all, lost, new, regular."""
    if segment == "lost":
        return await get_lost_clients(60)
    elif segment == "new":
        return await get_new_clients_this_month()
    elif segment == "regular":
        return await get_regular_clients(3)
    else:  # all
        async with aiosqlite.connect(config.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT * FROM clients WHERE client_type = 'client' AND telegram_id > 0 ORDER BY updated_at DESC"
            )
            return [dict(r) for r in await cur.fetchall()]


async def get_clients_stats(month: str = None) -> dict:
    """Статистика по клиентам для аналитики."""
    from datetime import datetime
    if month:
        month_start = f"{month}-01"
    else:
        month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Всего клиентов
        cur = await db.execute("SELECT COUNT(*) FROM clients WHERE client_type = 'client' AND telegram_id > 0")
        total = (await cur.fetchone())[0]

        # Новых за месяц (первый визит в этом месяце)
        cur = await db.execute("""
            SELECT COUNT(DISTINCT c.telegram_id) FROM clients c
            INNER JOIN bookings b ON c.telegram_id = b.telegram_id
            WHERE c.client_type = 'client' AND b.date >= ?
        """, (month_start,))
        new_month = (await cur.fetchone())[0]

        # Потерянных (60+ дней)
        lost = await get_lost_clients(60)
        lost_count = len(lost)

        # Постоянных (3+ визита)
        regular = await get_regular_clients(3)
        regular_count = len(regular)

        # Среднее кол-во визитов
        cur = await db.execute("""
            SELECT AVG(cnt) FROM (
                SELECT COUNT(*) as cnt FROM bookings
                WHERE telegram_id > 0
                GROUP BY telegram_id
            )
        """)
        row = await cur.fetchone()
        avg_visits = round(row[0], 1) if row and row[0] else 0

        # Топ услуги
        cur = await db.execute("""
            SELECT service_name, COUNT(*) as cnt FROM bookings
            WHERE service_name != '' GROUP BY service_name
            ORDER BY cnt DESC LIMIT 5
        """)
        top_services = [{"name": r[0], "count": r[1]} for r in await cur.fetchall()]

        return {
            "total": total,
            "new_this_month": new_month,
            "lost_60_days": lost_count,
            "regular_3plus": regular_count,
            "avg_visits": avg_visits,
            "top_services": top_services,
        }


async def update_client_birthday(telegram_id: int, birthday: str):
    """Сохранить день рождения клиента (ДД.ММ)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE clients SET birthday = ?, updated_at = datetime('now') WHERE telegram_id = ?",
            (birthday, telegram_id),
        )
        await db.commit()


async def get_birthdays_today() -> list:
    """Клиенты, у которых сегодня день рождения."""
    from datetime import datetime
    today = datetime.now().strftime("%d.%m")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM clients WHERE birthday = ? AND telegram_id > 0 AND client_type = 'client'",
            (today,),
        )
        return [dict(r) for r in await cur.fetchall()]


# ══════════════════════════════════════════════════════════
#  Услуги (services)
# ══════════════════════════════════════════════════════════

async def import_services_from_price_data():
    """Импорт услуг из price_data.py в БД. Вызывается при старте если таблица пуста."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM services")
        count = (await cur.fetchone())[0]
        if count > 0:
            return  # Уже есть данные

    import price_data
    sections = price_data.PRICE_SECTIONS
    async with aiosqlite.connect(config.DB_PATH) as db:
        for cat_idx, section in enumerate(sections):
            title = section.get("title", "")
            note = section.get("note", "")
            for svc_idx, svc in enumerate(section.get("services", [])):
                name = svc[0] if isinstance(svc, (list, tuple)) else svc.get("name", "")
                price = str(svc[1]) if isinstance(svc, (list, tuple)) and len(svc) > 1 else svc.get("price", "")
                await db.execute(
                    """INSERT OR IGNORE INTO services
                       (category_title, category_note, category_index, service_index, name, price, gender, sort_order)
                       VALUES (?, ?, ?, ?, ?, ?, 'all', ?)""",
                    (title, note, cat_idx, svc_idx, name, price, svc_idx),
                )
        await db.commit()
    log.info(f"Services: imported {sum(len(s.get('services', [])) for s in sections)} services from price_data")


async def get_all_services() -> list:
    """Все активные услуги, сгруппированные по категориям."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM services WHERE is_active = 1 ORDER BY category_index, service_index"
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_services_by_category() -> list:
    """Услуги, сгруппированные по категориям (для бота и виджета)."""
    services = await get_all_services()
    categories = {}
    for s in services:
        cat_idx = s["category_index"]
        if cat_idx not in categories:
            categories[cat_idx] = {
                "title": s["category_title"],
                "note": s["category_note"],
                "index": cat_idx,
                "services": [],
            }
        categories[cat_idx]["services"].append({
            "name": s["name"],
            "price": s["price"],
            "id": s["id"],
            "service_index": s["service_index"],
            "duration_minutes": s.get("duration_minutes") or 0,
        })
    return [categories[k] for k in sorted(categories.keys())]


async def get_service_by_id(service_id: int) -> dict | None:
    """Получить услугу по ID."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM services WHERE id = ?", (service_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def add_service(category_title: str, category_note: str, category_index: int,
                      name: str, price: str, gender: str = "all",
                      duration_minutes: int = 0) -> int:
    """Добавить услугу. Возвращает ID."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        # Определяем service_index (следующий в категории)
        cur = await db.execute(
            "SELECT COALESCE(MAX(service_index), -1) + 1 FROM services WHERE category_index = ?",
            (category_index,),
        )
        service_index = (await cur.fetchone())[0]
        cur = await db.execute(
            """INSERT INTO services (category_title, category_note, category_index, service_index, name, price, gender, sort_order, duration_minutes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (category_title, category_note, category_index, service_index, name, price, gender,
             service_index, max(0, int(duration_minutes or 0))),
        )
        await db.commit()
        return cur.lastrowid


async def update_service(service_id: int, **kwargs):
    """Обновить услугу."""
    allowed = {"name", "price", "gender", "category_title", "category_note", "is_active", "sort_order", "duration_minutes"}
    fields = []
    params = []
    for key, value in kwargs.items():
        if key in allowed:
            fields.append(f"{key} = ?")
            params.append(value)
    if not fields:
        return
    params.append(service_id)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(f"UPDATE services SET {', '.join(fields)} WHERE id = ?", params)
        await db.commit()


async def delete_service(service_id: int):
    """Мягкое удаление услуги (is_active = 0)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE services SET is_active = 0 WHERE id = ?", (service_id,))
        await db.commit()


async def get_service_categories() -> list:
    """Список уникальных категорий."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT DISTINCT category_index, category_title, category_note
               FROM services WHERE is_active = 1
               GROUP BY category_index ORDER BY category_index"""
        )
        return [dict(r) for r in await cur.fetchall()]


async def add_category(title: str, note: str = "", gender: str = "all") -> int:
    """Добавить новую категорию. Возвращает category_index."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT COALESCE(MAX(category_index), -1) + 1 FROM services")
        new_index = (await cur.fetchone())[0]
        await db.execute(
            """INSERT INTO services (category_title, category_note, category_index, service_index, name, price, gender)
               VALUES (?, ?, ?, 0, '', '', ?)""",
            (title, note, new_index, gender),
        )
        await db.commit()
        return new_index


async def get_price_for_service(service_name: str) -> int:
    """Получить числовую цену по названию услуги (из БД или fallback в price_data)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT price FROM services WHERE name = ? AND is_active = 1 LIMIT 1",
            (service_name,),
        )
        row = await cur.fetchone()
        if row:
            import re
            match = re.search(r'\d+', str(row[0]))
            if match:
                return int(match.group())
    # Fallback: price_data
    try:
        import price_data
        return price_data.get_price(service_name)
    except Exception:
        return 0


# ══════════════════════════════════════════════════════════
#  Настройки салона (из CRM / Telegram)
# ══════════════════════════════════════════════════════════

FEATURE_FLAGS = [
    "DISCOUNTS_ENABLED", "BIRTHDAY_DISCOUNT", "REVIEW_DISCOUNT",
    "GALLERY_ENABLED", "MASTERS_ENABLED", "RATING_ENABLED",
    "MY_BOOKINGS_ENABLED", "HISTORY_ENABLED", "BIRTHDAY_ENABLED",
    "CONTACT_ENABLED", "WIDGET_ENABLED", "COWORKING_ENABLED",
    "ORG_TYPE",
]

FLAG_LABELS = {
    "DISCOUNTS_ENABLED": "Скидки за визиты",
    "BIRTHDAY_DISCOUNT": "Скидка на день рождения",
    "REVIEW_DISCOUNT": "Скидка за отзыв",
    "GALLERY_ENABLED": "Галерея работ",
    "MASTERS_ENABLED": "Раздел «Мастера»",
    "RATING_ENABLED": "Оценка визитов",
    "MY_BOOKINGS_ENABLED": "Мои записи",
    "HISTORY_ENABLED": "История визитов",
    "COWORKING_ENABLED": "Коворкинг для мастеров",
    "ORG_TYPE": "Тип организации",
    "BIRTHDAY_ENABLED": "День рождения",
    "CONTACT_ENABLED": "Контакты салона",
    "WIDGET_ENABLED": "Виджет онлайн-записи",
}


async def init_settings_table():
    """Создать таблицу настроек (один раз на процесс — не на каждый get)."""
    global _settings_ready
    if _settings_ready:
        return
    async with aiosqlite.connect(config.DB_PATH) as db:
        await _apply_sqlite_pragmas(db)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS salon_settings (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            )
        """)
        await db.commit()
    _settings_ready = True


def _invalidate_settings_cache():
    global _settings_cache, _settings_cache_ts
    _settings_cache = None
    _settings_cache_ts = 0.0


async def get_setting(key: str, default: str = "") -> str:
    """Прочитать настройку (кэш с TTL 5с; miss → один SELECT)."""
    settings = await get_all_settings()
    val = settings.get(key)
    return val if val is not None else default


async def set_setting(key: str, value: str):
    """Записать настройку в БД и инвалидировать кэш."""
    await init_settings_table()
    async with aiosqlite.connect(config.DB_PATH) as db:
        await _apply_sqlite_pragmas(db)
        await db.execute(
            "INSERT OR REPLACE INTO salon_settings (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()
    _invalidate_settings_cache()


async def get_all_settings(force_db: bool = False) -> dict:
    """Все настройки. Кэш действует ≤5 сек — другой процесс (бот) подхватывает правки сам."""
    global _settings_cache, _settings_cache_ts
    await init_settings_table()
    import time as _time
    if (
        not force_db
        and _settings_cache is not None
        and (_time.monotonic() - _settings_cache_ts) < _SETTINGS_TTL_SEC
    ):
        return dict(_settings_cache)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await _apply_sqlite_pragmas(db)
        cur = await db.execute("SELECT key, value FROM salon_settings")
        rows = await cur.fetchall()
        data = {row[0]: row[1] for row in rows}
    _settings_cache = data
    _settings_cache_ts = _time.monotonic()
    return dict(data)


async def get_feature_flags() -> dict:
    """Получить все флаги функций с значениями."""
    settings = await get_all_settings()
    result = {}
    for flag in FEATURE_FLAGS:
        if flag == "ORG_TYPE":
            # ORG_TYPE — строка; читаем свежим SELECT (критичен для CRM↔bot)
            raw = await get_setting("ORG_TYPE", "")
            result[flag] = (raw or getattr(config, "ORG_TYPE", "beauty")).strip() or "beauty"
        elif flag in settings:
            result[flag] = settings[flag].lower() == "true"
        else:
            # Берём из config (значение по умолчанию из .env)
            result[flag] = getattr(config, flag, True)
    return result


async def init_bot_tables():
    """Таблицы меню бота и конфигурации оповещений (self-serve CRM)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_menu (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                org_type TEXT NOT NULL DEFAULT 'beauty',
                label TEXT NOT NULL,
                emoji TEXT DEFAULT '',
                action_type TEXT NOT NULL DEFAULT 'section',
                action_value TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notify_config (
                type TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 1,
                lead_hours REAL DEFAULT 24,
                quiet_start INTEGER DEFAULT 9,
                quiet_end INTEGER DEFAULT 21,
                template TEXT DEFAULT ''
            )
        """)
        await db.commit()


DEFAULT_BOT_MENU = {
    "beauty": [
        ("📅", "Записаться", "section", "menu_book"),
        ("💇‍♀️", "Услуги и цены", "section", "menu_services"),
        ("👩‍🎨", "Наши мастера", "section", "menu_masters"),
        ("📸", "Работы", "section", "menu_works"),
        ("📋", "Мои записи", "section", "menu_my_bookings"),
        ("✏️", "Изменить запись", "section", "menu_edit_booking"),
        ("📋", "История визитов", "section", "menu_history"),
        ("🎁", "Мои скидки", "section", "menu_discount"),
        ("🎂", "Мой день рождения", "section", "menu_birthday"),
        ("📍", "Как нас найти", "section", "menu_location"),
    ],
    "coworking": [
        ("🏢", "Забронировать слот", "section", "menu_book"),
        ("💰", "Тарифы", "section", "menu_services"),
        ("🪑", "Пространства", "section", "menu_masters"),
        ("📸", "Пространства в кадре", "section", "menu_works"),
        ("📋", "Мои брони", "section", "menu_my_bookings"),
        ("✏️", "Изменить бронь", "section", "menu_edit_booking"),
        ("📋", "История броней", "section", "menu_history"),
        ("📍", "Как нас найти", "section", "menu_location"),
    ],
}

SECTION_FLAG_MAP = {
    "menu_masters": "MASTERS_ENABLED",
    "menu_works": "GALLERY_ENABLED",
    "menu_my_bookings": "MY_BOOKINGS_ENABLED",
    "menu_edit_booking": "MY_BOOKINGS_ENABLED",
    "menu_history": "HISTORY_ENABLED",
    "menu_discount": "DISCOUNTS_ENABLED",
    "menu_birthday": "BIRTHDAY_ENABLED",
    "menu_location": "CONTACT_ENABLED",
}


async def get_bot_menu(org_type: str | None = None) -> list[dict]:
    """Меню бота; при пустой таблице — seed из дефолтов."""
    await init_bot_tables()
    if org_type is None:
        flags = await get_feature_flags()
        org_type = flags.get("ORG_TYPE", "beauty")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM bot_menu WHERE org_type = ? ORDER BY sort_order, id",
            (org_type,),
        )
        rows = [dict(r) for r in await cur.fetchall()]
        if not rows:
            defaults = DEFAULT_BOT_MENU.get(org_type) or DEFAULT_BOT_MENU["beauty"]
            for i, (emoji, label, action_type, action_value) in enumerate(defaults):
                await db.execute(
                    "INSERT INTO bot_menu (org_type, label, emoji, action_type, action_value, sort_order, enabled)"
                    " VALUES (?,?,?,?,?,?,1)",
                    (org_type, label, emoji, action_type, action_value, i),
                )
            await db.commit()
            cur = await db.execute(
                "SELECT * FROM bot_menu WHERE org_type = ? ORDER BY sort_order, id",
                (org_type,),
            )
            rows = [dict(r) for r in await cur.fetchall()]
        return rows


async def upsert_bot_menu_item(item_id: int | None, org_type: str, label: str, emoji: str,
                               action_type: str, action_value: str, sort_order: int,
                               enabled: bool) -> int:
    await init_bot_tables()
    async with aiosqlite.connect(config.DB_PATH) as db:
        if item_id:
            await db.execute(
                "UPDATE bot_menu SET label=?, emoji=?, action_type=?, action_value=?, sort_order=?, enabled=? WHERE id=?",
                (label, emoji, action_type, action_value, sort_order, int(enabled), item_id),
            )
            new_id = item_id
        else:
            cur = await db.execute(
                "INSERT INTO bot_menu (org_type, label, emoji, action_type, action_value, sort_order, enabled)"
                " VALUES (?,?,?,?,?,?,?)",
                (org_type, label, emoji, action_type, action_value, sort_order, int(enabled)),
            )
            new_id = cur.lastrowid
        await db.commit()
        return new_id


async def delete_bot_menu_item(item_id: int):
    await init_bot_tables()
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM bot_menu WHERE id = ?", (item_id,))
        await db.commit()


async def reorder_bot_menu(items: list[dict]):
    """items: [{id, sort_order}, ...]"""
    await init_bot_tables()
    async with aiosqlite.connect(config.DB_PATH) as db:
        for it in items:
            await db.execute(
                "UPDATE bot_menu SET sort_order = ? WHERE id = ?",
                (int(it.get("sort_order", 0)), int(it["id"])),
            )
        await db.commit()


NOTIFY_DEFAULTS = {
    "remind_24h": {
        "enabled": 1, "lead_hours": 24, "quiet_start": 9, "quiet_end": 21,
        "template": "📅 *Напоминание о записи*\n\nЗавтра у вас запись:\nМастер: {master_name}\nВремя: {time}\n\nПодтвердите или отмените запись:",
    },
    "remind_2h": {
        "enabled": 1, "lead_hours": 2, "quiet_start": 0, "quiet_end": 24,
        "template": "⏰ *Напоминание*\n\nЧерез 2 часа у вас запись!\nМастер: {master_name}\nВремя: {time}\n\nЖдём вас!",
    },
    "remind_repeat": {"enabled": 0, "lead_hours": 1, "quiet_start": 9, "quiet_end": 21, "template": ""},
    "review": {
        "enabled": 1, "lead_hours": 0, "quiet_start": 9, "quiet_end": 21,
        "template": "⭐ *Как прошла ваша запись?*\n\nМастер: {master_name}\nДата: {date}\nВремя: {time}\n\nПожалуйста, оцените обслуживание от 1 до 5 звёзд:",
    },
    "birthday": {
        "enabled": 1, "lead_hours": 0, "quiet_start": 10, "quiet_end": 21,
        "template": "🎂 С днём рождения! Подарок — скидка на сегодня.",
    },
    "admin_alert": {"enabled": 1, "lead_hours": 0, "quiet_start": 0, "quiet_end": 24, "template": ""},
}

NOTIFY_LABELS = {
    "remind_24h": "Напоминание за сутки",
    "remind_2h": "Напоминание за 2 часа",
    "remind_repeat": "Повторное напоминание",
    "review": "Запрос оценки",
    "birthday": "Поздравление с днём рождения",
    "admin_alert": "Админу о новой записи",
}


async def get_notify_config() -> dict:
    """Все типы оповещений: type -> {enabled, lead_hours, quiet_start, quiet_end, template}."""
    await init_bot_tables()
    result = {}
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM notify_config")
        rows = {r["type"]: dict(r) for r in await cur.fetchall()}
    for ntype, defaults in NOTIFY_DEFAULTS.items():
        if ntype in rows:
            result[ntype] = rows[ntype]
        else:
            result[ntype] = {"type": ntype, **defaults}
            async with aiosqlite.connect(config.DB_PATH) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO notify_config (type, enabled, lead_hours, quiet_start, quiet_end, template)"
                    " VALUES (?,?,?,?,?,?)",
                    (ntype, defaults["enabled"], defaults["lead_hours"],
                     defaults["quiet_start"], defaults["quiet_end"], defaults["template"]),
                )
                await db.commit()
    return result


async def set_notify_config(ntype: str, data: dict):
    await init_bot_tables()
    cfg = NOTIFY_DEFAULTS.get(ntype, NOTIFY_DEFAULTS["admin_alert"])
    enabled = int(bool(data.get("enabled", cfg["enabled"])))
    try:
        lead = float(data.get("lead_hours", cfg["lead_hours"]))
    except (TypeError, ValueError):
        lead = cfg["lead_hours"]
    try:
        qs = int(data.get("quiet_start", cfg["quiet_start"]))
        qe = int(data.get("quiet_end", cfg["quiet_end"]))
    except (TypeError, ValueError):
        qs, qe = cfg["quiet_start"], cfg["quiet_end"]
    template = str(data.get("template", cfg["template"]))
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO notify_config (type, enabled, lead_hours, quiet_start, quiet_end, template)"
            " VALUES (?,?,?,?,?,?)"
            " ON CONFLICT(type) DO UPDATE SET enabled=?, lead_hours=?, quiet_start=?, quiet_end=?, template=?",
            (ntype, enabled, lead, qs, qe, template, enabled, lead, qs, qe, template),
        )
        await db.commit()


def is_notify_enabled(cfg: dict, ntype: str) -> bool:
    if not cfg:
        return True
    item = cfg.get(ntype) or {}
    return bool(item.get("enabled", 1))


def render_notify_template(template: str, context: dict) -> str:
    if not template:
        return ""
    try:
        return template.format(**{k: (v if v is not None else "") for k, v in context.items()})
    except Exception:
        return template


WORKS_CATEGORIES_DEFAULT = [
    ("🔽 Загущение", "zagushchenie"),
    ("🔽 Наращивание", "narashchivanie"),
    ("🔽 Трихопигментация (SMP)", "smp"),
    ("🔽 Ботокс/Кератин", "botoks_keratin"),
]


async def get_works_categories() -> list:
    """Категории работ из БД. Если нет — дефолтные."""
    import json
    raw = await get_setting("works_categories", "")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return WORKS_CATEGORIES_DEFAULT


# ── Коворкинг ──────────────────────────────────────────────

async def get_master_by_tg_id(telegram_id: int) -> dict | None:
    """Найти мастера по Telegram ID."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM masters WHERE telegram_id = ? AND is_active = 1", (telegram_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def block_coworking(master_name: str, date: str, start_time: str, end_time: str) -> int:
    """Заблокировать слоты для коворкинга. Возвращает количество заблокированных."""
    from datetime import datetime, timedelta
    # Генерируем слоты от start_time до end_time с шагом 15 мин
    sh, sm = map(int, start_time.split(":"))
    eh, em = map(int, end_time.split(":"))
    slots = []
    h, m = sh, sm
    while (h, m) < (eh, em):
        slots.append(f"{h:02d}:{m:02d}")
        m += 15
        if m >= 60:
            h += 1
            m = 0

    count = 0
    for slot in slots:
        booking_id = await try_book_slot(
            master_name=master_name, date=date, time=slot,
            client_name="Коворкинг", booking_type="coworking",
        )
        if booking_id:
            count += 1
    return count


async def unblock_coworking(master_name: str, date: str, start_time: str, end_time: str):
    """Снять блокировку коворкинга."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "DELETE FROM bookings WHERE master_name = ? AND date = ? AND time >= ? AND time < ? AND booking_type = 'coworking'",
            (master_name, date, start_time, end_time),
        )
        await db.commit()


async def get_coworking_blocks(master_name: str) -> list:
    """Получить все активные блокировки коворкинга мастера (сегодня и позже)."""
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT date, MIN(time) as start_time, MAX(time) as end_time, COUNT(*) as slots
               FROM bookings
               WHERE master_name = ? AND booking_type = 'coworking' AND date >= ?
               GROUP BY date ORDER BY date""",
            (master_name, today),
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_coworking_blocks_for_date(master_name: str, date: str) -> list:
    """Получить блокировки коворкинга мастера на конкретную дату."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "SELECT time FROM bookings WHERE master_name = ? AND date = ? AND booking_type = 'coworking' ORDER BY time",
            (master_name, date),
        )
        return [row[0] for row in await cur.fetchall()]
