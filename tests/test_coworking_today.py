"""Регрессия изменений 2026-09-29: уведомления мастеру, выбор пространства
в ковopкинге, сид расписания, терминология CRM.

Must set env BEFORE importing api/config/bot.
"""
import os
import re
import sqlite3
import tempfile

os.environ.setdefault("CRM_SECRET", "test_secret_for_unit_tests")
os.environ.setdefault("CRM_PASSWORD", "test_crm_pass")
os.environ.setdefault("SALON_ID", "testsalon")
os.environ.setdefault("CRM_TOKEN_FIXED", "fixed_test_crm_token")
os.environ.setdefault(
    "BOT_TOKEN", "123456789:AAFakeTokenForUnitTestsOnly_abcdefghijklmnop"
)
_tmp = tempfile.mkdtemp(prefix="kaskad_coworking_test_")
os.environ.setdefault("DB_PATH", os.path.join(_tmp, "bot_cache.db"))

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from telegram.ext import ConversationHandler

import api as api_module
import bot
import db as db_module


# ── фикстуры ──────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    async def _init():
        await db_module.init()

    asyncio.run(_init())
    with TestClient(api_module.app) as c:
        yield c


def _auth_headers():
    return {"Cookie": f"{api_module.COOKIE_NAME}={api_module.CRM_TOKEN}"}


@pytest.fixture
def org_restore():
    """Переключает ORG_TYPE и всегда возвращает исходное значение."""
    async def _get():
        return await db_module.get_setting("ORG_TYPE", "")

    original = asyncio.run(_get())

    def _set(value):
        asyncio.run(db_module.set_setting("ORG_TYPE", value))

    yield _set
    _set(original or "beauty")


def _run(coro):
    return asyncio.run(coro)


# ── 1. resolve_master_tg (уведомления, a099a9b) ─────────────

def test_resolve_tg_direct(client):
    """Мастер с telegram_id>0 → возвращается напрямую."""
    con = sqlite3.connect(api_module.config.DB_PATH)
    con.execute(
        "INSERT INTO masters (name, phone, telegram_id, org_type) VALUES (?, ?, ?, ?)",
        ("RMT Прямой", "+375001112233", 111222333, "beauty"),
    )
    con.commit()
    con.close()
    assert _run(db_module.resolve_master_tg("RMT Прямой")) == 111222333


def test_resolve_tg_phone_fallback_autolink(client):
    """Fallback по телефону через clients + автопривязка в masters."""
    con = sqlite3.connect(api_module.config.DB_PATH)
    con.execute(
        "INSERT INTO masters (name, phone, telegram_id, org_type) VALUES (?, ?, ?, ?)",
        ("RMT Автолинк", "+375004455667", 0, "beauty"),
    )
    con.execute(
        "INSERT INTO clients (telegram_id, contact_id, phone, name) VALUES (?, ?, ?, ?)",
        (445566778, 0, "+375004455667", "Клиент РМТ"),
    )
    con.commit()
    con.close()

    assert _run(db_module.resolve_master_tg("RMT Автолинк")) == 445566778

    con = sqlite3.connect(api_module.config.DB_PATH)
    linked = con.execute(
        "SELECT telegram_id FROM masters WHERE name = 'RMT Автолинк'"
    ).fetchone()[0]
    con.close()
    assert linked == 445566778, "автопривязка должна записать telegram_id"


def test_resolve_tg_missing_everything(client):
    """Нет мастера → None; мастер без телефона и tg → None."""
    assert _run(db_module.resolve_master_tg("RMT НетТакого")) is None
    con = sqlite3.connect(api_module.config.DB_PATH)
    con.execute(
        "INSERT INTO masters (name, phone, telegram_id, org_type) VALUES (?, ?, ?, ?)",
        ("RMT Пустой", "", 0, "beauty"),
    )
    con.commit()
    con.close()
    assert _run(db_module.resolve_master_tg("RMT Пустой")) is None
    assert _run(db_module.resolve_master_tg("")) is None


# ── 2. сид расписания (80a0639) ──────────────────────────────

def test_seed_schedule_skipped_for_coworking(client):
    """POST /api/masters org=coworking → 0 строк расписания; beauty → 7."""
    r = client.post(
        "/api/masters",
        json={"name": "СидКовТест", "org_type": "coworking", "phone": "+375001000001"},
        headers=_auth_headers(),
    )
    assert r.status_code == 200, r.text

    r2 = client.post(
        "/api/masters",
        json={"name": "СидБьютиТест", "org_type": "beauty", "phone": "+375001000002"},
        headers=_auth_headers(),
    )
    assert r2.status_code == 200, r2.text

    con = sqlite3.connect(api_module.config.DB_PATH)
    cow = con.execute(
        "SELECT count(*) FROM master_schedule WHERE master_name='СидКовТест'"
    ).fetchone()[0]
    beauty = con.execute(
        "SELECT count(*) FROM master_schedule WHERE master_name='СидБьютиТест'"
    ).fetchone()[0]
    con.close()
    assert cow == 0, f"ковopкинг не должен сидить расписание, получено {cow}"
    assert beauty == 7, f"beauty должен получить 7 строк, получено {beauty}"


# ── 3. FSM выбора пространства (80a0639) ─────────────────────

def test_fsm_space_state_registered():
    """BOOK_SELECT_SPACE зарегистрирован: book_sp_ + back_main."""
    app = bot.build_application()
    conv = next(h for h in app.handlers[0] if isinstance(h, ConversationHandler))
    states = conv.states
    assert bot.BOOK_SELECT_SPACE in states, "состояние BOOK_SELECT_SPACE не зарегистрировано"
    patterns = [h.pattern.pattern for h in states[bot.BOOK_SELECT_SPACE]
                if getattr(h, "pattern", None)]
    assert "^book_sp_" in patterns, "нет хендлера выбора пространства"
    assert "^back_main$" in patterns, "нет кнопки «Назад» в состоянии выбора пространства"


def test_book_multi_done_coworking_asks_space(org_restore):
    """В ковopкинге после тарифа — экран выбора пространства, не календарь."""
    org_restore("coworking")
    con = sqlite3.connect(api_module.config.DB_PATH)
    con.execute(
        "INSERT INTO masters (name, phone, org_type, is_active) VALUES (?, ?, ?, 1)",
        ("ФСМ Стол Тест", "+375002000001", "coworking"),
    )
    con.execute(
        "INSERT INTO masters (name, phone, org_type, is_active) VALUES (?, ?, ?, 1)",
        ("ФСМ Стол Тест2", "+375002000002", "coworking"),
    )
    con.commit()
    con.close()

    update = MagicMock()
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    ctx = MagicMock()
    ctx.user_data = {
        "booking": {
            "section_idx": 0,
            "multi_services": [
                {"id": 1, "name": "День", "price": "5", "duration_minutes": 60}
            ],
        }
    }

    result = _run(bot.book_multi_done(update, ctx))
    assert result == bot.BOOK_SELECT_SPACE, (
        f"в ковopкинге ожидается BOOK_SELECT_SPACE, получено {result}"
    )
    _, kwargs = query.edit_message_text.call_args
    kb = kwargs["reply_markup"]
    callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
    assert any(c.startswith("book_sp_") and c != "book_sp_back" for c in callbacks), (
        f"в клавиатуре нет book_sp_ кнопок: {callbacks}"
    )
    assert "book_sp_back" in callbacks, "нет кнопки «Назад»"


def test_book_select_space_sets_master_name(org_restore):
    """book_sp_<id> записывает реальное имя пространства и ведёт в календарь."""
    org_restore("coworking")
    con = sqlite3.connect(api_module.config.DB_PATH)
    row = con.execute(
        "SELECT id FROM masters WHERE name='ФСМ Стол Тест'"
    ).fetchone()
    con.close()
    assert row, "тестовое пространство должно существовать"
    space_id = row[0]

    update = MagicMock()
    query = MagicMock()
    query.data = f"book_sp_{space_id}"
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    ctx = MagicMock()
    ctx.user_data = {"booking": {"duration_minutes": 60}}

    result = _run(bot.book_select_space(update, ctx))
    assert result == bot.BOOK_SELECT_DATE
    assert ctx.user_data["booking"]["master_name"] == "ФСМ Стол Тест"


# ── 4. manage-ссылка удалена (dae14e0) ───────────────────────

def test_manage_link_gone_from_bot():
    """bot.py не должен содержать генерацию manage-ссылки."""
    import pathlib
    src = (pathlib.Path(__file__).parent.parent / "bot.py").read_text(encoding="utf-8")
    assert "manage_link" not in src, "manage_link вернулся в bot.py"
    assert "manage-booking?id=" not in src, "manage-ссылка вернулась в bot.py"


# ── 5. терминология ковopкинга (d58b451) ────────────────────

_VISIBLE_PAGES = ["/", "/masters", "/bookings", "/clients", "/finance",
                  "/users", "/analytics", "/widget", "/schedule",
                  "/services", "/settings", "/bot"]


def _visible_html(html: str) -> str:
    """Убирает <script>/<style>/комментарии — то, что реально видит пользователь."""
    html = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S | re.I)
    return html


def test_coworking_pages_have_no_master_terms(client, org_restore):
    """Режим coworking: на видимых страницах нет «мастер»."""
    org_restore("coworking")
    pattern = re.compile(r"мастер", re.I)
    violations = []
    for page in _VISIBLE_PAGES:
        r = client.get(page, headers=_auth_headers())
        assert r.status_code == 200, f"{page}: HTTP {r.status_code}"
        visible = _visible_html(r.text)
        for m in pattern.finditer(visible):
            seg = visible[max(0, m.start() - 70):m.start() + 70].replace("\n", " ")
            violations.append(f"{page}: …{seg}…")
    assert not violations, "видимые «мастер» в ковopкинге:\n" + "\n".join(violations)


def test_beauty_texts_unchanged(client, org_restore):
    """Режим beauty: прежние тексты на месте (обратная регресс)."""
    org_restore("beauty")
    r = client.get("/masters", headers=_auth_headers())
    assert r.status_code == 200
    assert "<h1>Мастера</h1>" in r.text
    assert "+ Добавить мастера" in r.text

    r2 = client.get("/settings", headers=_auth_headers())
    assert r2.status_code == 200
    assert "Раздел «Мастера»" in r2.text


def test_coworking_settings_labels(client, org_restore):
    """Настройки в ковopкинге: лейблы флагов и ORG_HINTS без «мастера»."""
    org_restore("coworking")
    r = client.get("/settings", headers=_auth_headers())
    assert r.status_code == 200
    visible = _visible_html(r.text)
    assert "Раздел «Пространства»" in visible, "LABEL MASTERS_ENABLED не подменён"
    assert "выбор пространства" in r.text, "ORG_HINTS не обновлён после фикса бота"
    assert "без выбора мастера" not in r.text, "устаревшая подсказка вернулась"
