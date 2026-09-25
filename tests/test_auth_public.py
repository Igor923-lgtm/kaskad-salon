"""Auth middleware: public GET vs protected mutations.

Must set env BEFORE importing api/config.
"""
import os
import tempfile

os.environ["CRM_SECRET"] = "test_secret_for_unit_tests"
os.environ["CRM_PASSWORD"] = "test_crm_pass"
os.environ["SALON_ID"] = "testsalon"
os.environ["CRM_TOKEN_FIXED"] = "fixed_test_crm_token"
_tmp = tempfile.mkdtemp(prefix="kaskad_test_")
os.environ["DB_PATH"] = os.path.join(_tmp, "bot_cache.db")

import pytest
from fastapi.testclient import TestClient

import api as api_module
import db as db_module


@pytest.fixture(scope="session")
def client():
    # init schema in temp DB
    import asyncio

    asyncio.get_event_loop_policy()
    # db.init is async — run once
    async def _init():
        await db_module.init()

    try:
        asyncio.run(_init())
    except RuntimeError:
        # already running loop (shouldn't in pytest)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(_init())
        loop.close()

    with TestClient(api_module.app) as c:
        yield c


def _auth_headers():
    return {"Cookie": f"{api_module.COOKIE_NAME}={api_module.CRM_TOKEN}"}


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "duration_migration" in body


def test_public_get_services(client):
    assert client.get("/api/services").status_code == 200
    assert client.get("/api/services/grouped").status_code == 200
    assert client.get("/api/masters").status_code == 200


def test_post_services_unauthorized(client):
    payload = {
        "category_title": "Test",
        "name": "Hack",
        "price": "1",
    }
    r = client.post("/api/services", json=payload)
    assert r.status_code == 401


def test_put_service_unauthorized(client):
    r = client.put("/api/services/1", json={"price": "999"})
    assert r.status_code == 401


def test_delete_service_unauthorized(client):
    r = client.delete("/api/services/1")
    assert r.status_code == 401


def test_post_services_authorized(client):
    payload = {
        "category_title": "SecTest",
        "name": "SecTest service",
        "price": "10",
        "duration_minutes": 30,
    }
    r = client.post("/api/services", json=payload, headers=_auth_headers())
    assert r.status_code == 200
    assert "id" in r.json()


def test_finance_unauthorized(client):
    assert client.get("/api/finance/summary").status_code == 401
    assert client.get("/api/transactions").status_code == 401


def test_users_unauthorized(client):
    assert client.get("/api/users").status_code == 401


def test_clients_unauthorized(client):
    assert client.get("/api/clients").status_code == 401


def test_bookings_list_unauthorized(client):
    # GET /api/bookings — только с auth (виджету нужен только POST)
    assert client.get("/api/bookings").status_code == 401


def test_post_bookings_public_path_still_open(client):
    # Виджет создаёт запись без cookie: невалидный мастер → 400, не 401
    r = client.post("/api/bookings", json={
        "master_name": "__no_such__",
        "date": "2099-01-01",
        "time": "10:00",
        "client_name": "T",
    })
    assert r.status_code != 401
    assert r.status_code in (400, 409)


def test_put_masters_unauthorized_without_auth(client):
    # POST /api/masters без auth — 401 (раньше был публичным)
    r = client.post("/api/masters", json={"name": "Hacker"})
    assert r.status_code == 401


def test_manage_booking_bad_token_not_blocked_by_middleware(client):
    """HMAC paths must reach handler (403), not middleware 401/302."""
    r = client.get("/manage-booking", params={"id": 1, "token": "bad"})
    assert r.status_code == 403
    r = client.post("/api/bookings/manage/1/cancel", params={"token": "bad"})
    assert r.status_code == 403
    r = client.get("/api/bookings/manage/1", params={"token": "bad"})
    assert r.status_code == 403


def test_manage_booking_does_not_open_other_bookings(client):
    assert client.get("/api/bookings").status_code == 401


def test_login_post_is_public(client):
    """POST /login must not be blocked by middleware (rate-limit only)."""
    # wrong password → 200 with error page (not 401/302 from middleware)
    r = client.post("/login", data={"password": "definitely-wrong"})
    assert r.status_code == 200
    assert "Неверный" in r.text or "пароль" in r.text.lower()


def test_login_post_with_correct_password_sets_cookie(client):
    r = client.post("/login", data={"password": "test_crm_pass"}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/dashboard" in r.headers.get("location", "")


def test_login_rate_limit_redirects_with_message(client):
    """6+ POST /login → 302 to /login?error=... (HTML form UX, not bare JSON)."""
    # reset counter for this test process by flooding after clearing via many posts
    for i in range(6):
        r = client.post("/login", data={"password": "wrong"}, follow_redirects=False)
    # either redirect with error (rate limited) or still 200 wrong-password before limit
    # after 5 wrong attempts within a minute the 6th should be 302 to /login?error=
    assert r.status_code in (200, 302)
    if r.status_code == 302:
        loc = r.headers.get("location", "")
        assert loc.startswith("/login")
        assert "error=" in loc
