"""Self-serve setup flow: одноразовая ссылка /setup задаёт пароль ЦРМ.

Must set env BEFORE importing api/config.
"""
import asyncio
import os
import tempfile
import time

os.environ.setdefault("CRM_SECRET", "test_secret_for_unit_tests")
os.environ.setdefault("CRM_PASSWORD", "test_crm_pass")
os.environ.setdefault("SALON_ID", "testsalon")
os.environ.setdefault("CRM_TOKEN_FIXED", "fixed_test_crm_token")
_tmp = tempfile.mkdtemp(prefix="kaskad_setup_test_")
os.environ.setdefault("DB_PATH", os.path.join(_tmp, "bot_cache.db"))

import pytest
from fastapi.testclient import TestClient

import api as api_module
import db as db_module


@pytest.fixture(scope="session")
def client():
    async def _init():
        await db_module.init()

    asyncio.run(_init())
    with TestClient(api_module.app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean_state():
    api_module._login_attempts.clear()
    yield
    api_module._login_attempts.clear()
    async def _reset():
        await db_module.set_setting("CRM_PASSWORD_HASH", "")
        await db_module.set_setting("SETUP_CONSUMED", "")
    asyncio.run(_reset())


def _token(ttl: int = 3600) -> str:
    return api_module._make_setup_token(int(time.time()) + ttl)


def test_garbage_token_renders_error_no_form(client):
    r = client.get("/setup", params={"token": "garbage"})
    assert r.status_code == 200
    assert "недействительна" in r.text.lower()
    assert 'name="password"' not in r.text


def test_valid_token_shows_form(client):
    r = client.get("/setup", params={"token": _token()})
    assert r.status_code == 200
    assert 'name="password"' in r.text
    assert 'name="confirm"' in r.text


def test_post_reaches_handler_not_middleware(client):
    """403 от handler доказывает, что /setup в публичных путях (не 302-redirect)."""
    r = client.post("/setup", data={"token": "bad", "password": "newpass123",
                                    "confirm": "newpass123"})
    assert r.status_code == 403


def test_short_password_rejected_token_survives(client):
    token = _token()
    r = client.post("/setup", data={"token": token, "password": "123", "confirm": "123"})
    assert r.status_code == 200
    assert "не короче" in r.text
    # токен не сгорел — форма доступна ещё раз
    r = client.get("/setup", params={"token": token})
    assert 'name="password"' in r.text


def test_mismatched_passwords(client):
    r = client.post("/setup", data={"token": _token(), "password": "abcdef123",
                                    "confirm": "abcdef999"})
    assert r.status_code == 200
    assert "не совпадают" in r.text


def test_expired_token_403(client):
    expired = api_module._make_setup_token(int(time.time()) - 10)
    r = client.post("/setup", data={"token": expired, "password": "abcdef123",
                                    "confirm": "abcdef123"})
    assert r.status_code == 403


def test_full_flow_set_password_login_and_burn_token(client):
    token = _token()

    r = client.post("/setup", data={"token": token, "password": "brandnew77",
                                    "confirm": "brandnew77"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login"

    # общий пароль из .env больше не пускает
    r = client.post("/login", data={"password": "test_crm_pass"}, follow_redirects=False)
    assert r.status_code == 200
    assert "Неверный" in r.text

    # новый пароль пускает
    r = client.post("/login", data={"password": "brandnew77"}, follow_redirects=False)
    assert r.status_code == 302
    assert "/dashboard" in r.headers["location"]

    # токен одноразовый: повторный POST → 403, GET — без формы
    r = client.post("/setup", data={"token": token, "password": "another777",
                                    "confirm": "another777"}, follow_redirects=False)
    assert r.status_code == 403
    r = client.get("/setup", params={"token": token})
    assert 'name="password"' not in r.text
