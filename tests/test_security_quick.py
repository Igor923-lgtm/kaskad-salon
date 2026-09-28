"""Быстрые проверки безопасности (этап 1): OTP-лимиты, роли, XSS-валидация.

Must set env BEFORE importing api/config.
"""
import os
import tempfile
from datetime import datetime, timedelta

os.environ["CRM_SECRET"] = "test_secret_for_unit_tests"
os.environ["CRM_PASSWORD"] = "test_crm_pass"
os.environ["SALON_ID"] = "testsalon"
os.environ["CRM_TOKEN_FIXED"] = "fixed_test_crm_token"
_tmp = tempfile.mkdtemp(prefix="kaskad_sec_")
os.environ["DB_PATH"] = os.path.join(_tmp, "bot_cache.db")

import asyncio

import pytest
from fastapi.testclient import TestClient

import api as api_module
import db as db_module


@pytest.fixture(scope="session")
def client():
    async def _init():
        await db_module.init()

    try:
        asyncio.run(_init())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_init())
        loop.close()

    with TestClient(api_module.app) as c:
        yield c


def _auth_headers():
    return {"Cookie": f"{api_module.COOKIE_NAME}={api_module.CRM_TOKEN}"}


def _make_session(token: str, role: str):
    """Создать master-сессию с заданной ролью напрямую в БД."""
    asyncio.run(api_module._save_session(token, 1, "SecTest Master", 0, role))


# ── 1. OTP: лимит запросов и попыток ──────────────────────────

def test_otp_request_rate_limit(client):
    """6-й запрос кода за минуту → 429."""
    phone = "+375001110001"
    codes = []
    for _ in range(6):
        r = client.post("/api/master/auth/request", json={"phone": phone})
        codes.append(r.status_code)
    # первые 5: телефон не найден (400) или отправлен (200); 6-й — 429
    assert codes[5] == 429, f"6th request must be rate-limited, got {codes}"
    assert all(c in (200, 400) for c in codes[:5]), codes


def test_otp_unknown_phone_no_enumeration(client):
    """Неизвестный телефон → 400 с текстом как для прочих ошибок (не 404)."""
    r = client.post("/api/master/auth/request", json={"phone": "+375002220002"})
    assert r.status_code == 400
    assert "не найден" not in r.text
    assert "Проверьте номер" in r.text


def test_otp_verify_lockout_after_5_attempts(client):
    """После 5 неверных код сгорает — 6-я попытка (даже верная) отклоняется."""
    phone = "+375003330003"
    api_module._sms_codes[phone] = {
        "code": "1234",
        "expires": datetime.now() + timedelta(minutes=5),
        "master_id": 1,
        "master_name": "SecTest",
        "telegram_id": 0,
        "role": "master_edit",
    }
    for i in range(5):
        r = client.post("/api/master/auth/verify", json={"phone": phone, "code": "9999"})
        assert r.status_code == 400, f"attempt {i+1}"
    # 6-я попытка — код должен сгореть даже с верным значением
    r = client.post("/api/master/auth/verify", json={"phone": phone, "code": "1234"})
    assert r.status_code == 400
    # код удалён — повторная попытка тоже отклонена
    assert phone not in api_module._sms_codes
    r = client.post("/api/master/auth/verify", json={"phone": phone, "code": "1234"})
    assert r.status_code == 400


# ── 2. Роли: эскалация через master-токен закрыта ─────────────

def test_master_token_cannot_list_sessions(client):
    """CRITICAL: master_edit-токен не читает сырые токены сессий."""
    _make_session("sec_tok_master_edit", "master_edit")
    r = client.get("/api/masters/sessions?token=sec_tok_master_edit")
    assert r.status_code == 403


def test_crm_cookie_can_list_sessions(client):
    """masters_app.html (CRM-кука) продолжает работать."""
    r = client.get("/api/masters/sessions", headers=_auth_headers())
    assert r.status_code == 200
    assert "sessions" in r.json()


def test_master_token_cannot_broadcast(client):
    """Рассылка без права broadcast → 403."""
    _make_session("sec_tok_nobroadcast", "master_edit")
    r = client.post(
        "/api/broadcast?token=sec_tok_nobroadcast",
        json={"segment": "all", "text": "hack"},
    )
    assert r.status_code == 403


def test_master_token_cannot_change_settings(client):
    """Настройки салона — только админ (CRM-кука/director)."""
    _make_session("sec_tok_settings", "master_edit")
    r = client.put(
        "/api/settings?token=sec_tok_settings",
        json={"ORG_TYPE": "beauty"},
    )
    assert r.status_code == 403


def test_crm_cookie_can_change_settings(client):
    """Регресс: настройки из settings.html (кука) работают."""
    r = client.put("/api/settings", json={"ORG_TYPE": "beauty"}, headers=_auth_headers())
    assert r.status_code == 200


def test_master_token_cannot_revoke_sessions(client):
    _make_session("sec_tok_revoke", "master_edit")
    r = client.post("/api/masters/sessions/revoke-all?token=sec_tok_revoke")
    assert r.status_code == 403


# ── 3. XSS: валидация публичной брони ─────────────────────────

def test_booking_validator_strips_html():
    b = api_module.BookingCreate(
        master_name="M",
        date="2099-01-01",
        time="10:00",
        client_name="<img src=x onerror=alert(1)>",
        service_name="<b>Стрижка</b>",
        phone="<script>+375291112233",
    )
    assert "<" not in b.client_name and ">" not in b.client_name
    assert "<" not in b.service_name
    assert "<" not in b.phone
    # длина ограничена
    long = api_module.BookingCreate(
        master_name="M", date="2099-01-01", time="10:00",
        client_name="А" * 500,
    )
    assert len(long.client_name) <= 160


def test_booking_validator_keeps_normal_names():
    """Обычные имена/цены не ломаются валидацией (анти-слом)."""
    b = api_module.BookingCreate(
        master_name="M", date="2099-01-01", time="10:00",
        client_name="Анна-Мария (Петрова)", price="120 р. + скидка",
        phone="+375 (29) 120-61-01",
    )
    assert b.client_name == "Анна-Мария (Петрова)"
    assert b.price == "120 р. + скидка"
    assert b.phone == "+375 (29) 120-61-01"


# ── Telegram-ID мастера: поле реально сохранялось только в UI ──

def test_master_create_persists_telegram_id(client):
    """«ID в Telegram» из формы ЦРМ должен сохраняться, а не отбрасываться Pydantic."""
    r = client.post("/api/masters", json={
        "name": "ТГ Тест", "phone": "+375002220001", "telegram_id": 987654,
    }, headers=_auth_headers())
    assert r.status_code == 200, r.text
    mid = r.json()["id"]

    rows = client.get("/api/masters", headers=_auth_headers()).json()
    row = next(m for m in rows if m["id"] == mid)
    assert row.get("telegram_id") == 987654, f"telegram_id lost: {row.get('telegram_id')}"


def test_master_update_persists_telegram_id(client):
    """PUT /api/masters/{id} сохраняет переданный telegram_id."""
    r = client.post("/api/masters", json={"name": "ТГ апдейт"}, headers=_auth_headers())
    mid = r.json()["id"]

    r = client.put(f"/api/masters/{mid}", json={
        "name": "ТГ апдейт", "telegram_id": 555777,
    }, headers=_auth_headers())
    assert r.status_code == 200, r.text

    rows = client.get("/api/masters", headers=_auth_headers()).json()
    row = next(m for m in rows if m["id"] == mid)
    assert row.get("telegram_id") == 555777


def test_master_update_without_telegram_id_keeps_it(client):
    """PUT без telegram_id (его шлёт PWA) не должен обнулять колонку."""
    r = client.post("/api/masters", json={
        "name": "ТГ сохранить", "telegram_id": 424242,
    }, headers=_auth_headers())
    mid = r.json()["id"]

    # PWA шлёт только name/specialization/phone — telegram_id отсутствует
    r = client.put(f"/api/masters/{mid}", json={
        "name": "ТГ сохранить", "specialization": "новая", "phone": "+375003330001",
    }, headers=_auth_headers())
    assert r.status_code == 200, r.text

    rows = client.get("/api/masters", headers=_auth_headers()).json()
    row = next(m for m in rows if m["id"] == mid)
    assert row.get("telegram_id") == 424242, "telegram_id was wiped by partial PUT"
    assert row.get("specialization") == "новая"
