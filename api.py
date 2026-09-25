"""CRM REST API — FastAPI + SQLite (YCLIENTS-style)."""
import asyncio
import os
import random
import string
import logging
import hashlib
import hmac
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import quote

import aiosqlite
from fastapi import FastAPI, HTTPException, Query, Request, Depends, Cookie, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageOps
from pydantic import BaseModel

import config

log = logging.getLogger(__name__)


def _resize_image(data: bytes, max_side: int, *, jpeg_quality: int = 85) -> tuple[bytes, str]:
    """Ужать по длинной стороне, сохраняя пропорции. Возвращает (bytes, ext).
    PNG с прозрачностью сохраняем как PNG; иначе JPEG (легче для бота/TG)."""
    img = Image.open(BytesIO(data))
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    if has_alpha:
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        # если PNG всё равно тяжёлый — RGB JPEG без альфы
        if buf.tell() > 400 * 1024:
            img2 = img.convert("RGB")
            buf = BytesIO()
            img2.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
            return buf.getvalue(), "jpg"
        return buf.getvalue(), "png"
    img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    if buf.tell() > 400 * 1024 and jpeg_quality > 70:
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=70, optimize=True)
    return buf.getvalue(), "jpg"

app = FastAPI(title="Salon KASKAD CRM", version="2.0")

# Optional Sentry (F1) — only if SENTRY_DSN set
_sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
if _sentry_dsn:
    try:
        import sentry_sdk
        sentry_sdk.init(dsn=_sentry_dsn, traces_sample_rate=0.0)
        log.info("Sentry initialized")
    except Exception as e:
        log.warning(f"Sentry init failed: {e}")

BASE_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
_works_dir = BASE_DIR / "works_photos"
_works_dir.mkdir(exist_ok=True)
app.mount("/works-photos", StaticFiles(directory=str(_works_dir)), name="works_photos")

# ── Авторизация CRM ──────────────────────────────────────

# Обязательный секрет сессии: без env приложение не стартует (дефолт в коде запрещён)
CRM_SECRET = (os.getenv("CRM_SECRET") or "").strip()
if not CRM_SECRET:
    raise RuntimeError(
        "CRM_SECRET is required: set it in environment / salons/<id>/.env"
    )

def _make_token(password: str) -> str:
    return hashlib.sha256((password + CRM_SECRET).encode()).hexdigest()[:32]

CRM_TOKEN = os.getenv("CRM_TOKEN_FIXED") or _make_token(config.CRM_PASSWORD)

# Имя cookie per-salon: :8000 и :8005 на одном хосте делят cookie jar браузера,
# общее имя "crm_token" приводило к постоянным разлогинам.
COOKIE_NAME = f"crm_token_{config.SALON_ID}"
LEGACY_COOKIE = "crm_token"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 30  # 30 лет


def _cookie_kwargs() -> dict:
    return {"max_age": COOKIE_MAX_AGE, "httponly": True, "path": "/", "samesite": "lax"}


def _auth_cookie_ok(request: Request) -> bool:
    for name in (COOKIE_NAME, LEGACY_COOKIE):
        if request.cookies.get(name) == CRM_TOKEN:
            return True
    return False


# Публичные GET-пути (online booking / widget / статика).
# Мутации (POST/PUT/DELETE) и финансовые/пользовательские API — только после auth.
_PUBLIC_GET_PATHS = {
    "/",
    "/health",
    "/login",
    "/widget",
    "/book",
    "/api/slots",
    "/api/services",
    "/api/masters",
    "/api/salon-hours",
    "/api/settings/salon-name",
    "/api/settings/logo",
}


def _is_public(path: str, method: str = "GET") -> bool:
    # Статика и галерея работ
    if path.startswith("/static/") or path.startswith("/works-photos"):
        return True
    # Мобильное приложение мастеров — своя авторизация внутри handlers
    if path == "/master" or path.startswith("/master/"):
        return True
    if path == "/api/master" or path.startswith("/api/master/"):
        return True
    # Виджет/book создают запись без cookie (rate/валидация — в обработчике)
    if method == "POST" and path == "/api/bookings":
        return True
    # Вход в ЦРМ: POST /login (rate-limit в middleware до этой проверки)
    if path == "/login" and method == "POST":
        return True
    # Self-service manage-booking: handler валидирует HMAC token в query
    if path == "/manage-booking" and method == "GET":
        return True
    if path.startswith("/api/bookings/manage/") and method in ("GET", "POST"):
        return True
    if method != "GET":
        return False
    if path in _PUBLIC_GET_PATHS:
        return True
    # Прайс: список + категории + grouped (только чтение)
    if path.startswith("/api/services"):
        return True
    return False

_login_attempts = {}

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    method = request.method

    # Rate limiting для логина (5 попыток в минуту)
    if path == "/login" and method == "POST":
        ip = request.client.host if request.client else "unknown"
        now = datetime.now().timestamp()
        if ip not in _login_attempts:
            _login_attempts[ip] = []
        _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < 60]
        if len(_login_attempts[ip]) >= 5:
            # HTML-форма логина: редирект с текстом, не JSON
            if path == "/login":
                msg = quote("Слишком много попыток. Подождите минуту и попробуйте снова.")
                return RedirectResponse(url=f"/login?error={msg}", status_code=302)
            return JSONResponse({"detail": "Слишком много попыток. Подождите."}, status_code=429)
        _login_attempts[ip].append(now)

    # Публичные пути — пропускаем
    if _is_public(path, method):
        return await call_next(request)
    # Cookie: per-salon имя, fallback на legacy (только если value == наш CRM_TOKEN)
    if _auth_cookie_ok(request):
        response = await call_next(request)
        # Миграция: legacy → per-salon cookie
        if (request.cookies.get(COOKIE_NAME) != CRM_TOKEN
                and request.cookies.get(LEGACY_COOKIE) == CRM_TOKEN
                and hasattr(response, "set_cookie")):
            response.set_cookie(COOKIE_NAME, CRM_TOKEN, **_cookie_kwargs())
        return response
    # Проверяем токен из query params (master session или CRM token)
    token = request.query_params.get("token")
    if token:
        if token == CRM_TOKEN:
            return await call_next(request)
        try:
            session = await _get_session(token)
            if session:
                return await call_next(request)
        except Exception:
            pass
    # Для API — 401 (без полного query в логе: token не пишем)
    if path.startswith("/api/"):
        log.warning(f"AUTH 401: path={path} method={method}")
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    # Для страниц — редирект на логин
    log.warning(f"AUTH REDIRECT: path={path} method={method}")
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def page_login(request: Request, error: str = ""):
    ctx = await _template_context(request, error=error)
    return templates.TemplateResponse(request, "login.html", ctx)


@app.post("/login")
async def do_login(request: Request):
    form = await request.form()
    password = form.get("password", "")
    if password == config.CRM_PASSWORD:
        response = RedirectResponse(url="/dashboard", status_code=302)
        response.set_cookie(COOKIE_NAME, CRM_TOKEN, **_cookie_kwargs())
        # Подчистить старое общее имя, чтобы не конфликтовало на другом порту
        response.delete_cookie(LEGACY_COOKIE, path="/")
        return response
    ctx = await _template_context(request, error="Неверный пароль")
    return templates.TemplateResponse(request, "login.html", ctx)


@app.get("/logout")
async def do_logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie(COOKIE_NAME, path="/")
    response.delete_cookie(LEGACY_COOKIE, path="/")
    return response





@app.get("/health")
async def health():
    """Health check + флаг миграции duration_minutes (см. db.init)."""
    duration_migration = False
    try:
        async with aiosqlite.connect(config.DB_PATH) as adb:
            cur = await adb.execute("PRAGMA table_info(services)")
            rows = await cur.fetchall()
            duration_migration = any(r[1] == "duration_minutes" for r in rows)
    except Exception:
        duration_migration = False
    return {
        "status": "ok",
        "time": datetime.now().isoformat(),
        "duration_migration": duration_migration,
    }


# ── Модели ────────────────────────────────────────────────

class BookingCreate(BaseModel):
    master_name: str
    date: str
    time: str
    client_name: str = ""
    phone: str = ""
    telegram_id: int = 0
    service_name: str = ""
    price: str = ""
    duration_minutes: int | None = None
    service_ids: list[int] | None = None
    promo_code: str | None = None

class BookingUpdate(BaseModel):
    master_name: str | None = None
    date: str | None = None
    time: str | None = None
    client_name: str | None = None
    phone: str | None = None
    service_name: str | None = None
    price: str | None = None
    duration_minutes: int | None = None

class MasterCreate(BaseModel):
    name: str
    specialization: str = ""
    description: str = ""
    categories: str = ""
    phone: str = ""
    org_type: str = ""  # beauty | coworking | '' (показывать всем)

class ScheduleItem(BaseModel):
    day_of_week: int
    start_time: str = "10:00"
    end_time: str = "20:00"
    is_day_off: int = 0
    selected_hours: str = ""

class HoursUpdate(BaseModel):
    day_of_week: int
    hours: list[str]  # e.g. ["10:00", "14:00", "18:00"]

class AuthRequest(BaseModel):
    phone: str

class AuthVerify(BaseModel):
    phone: str
    code: str

# ── Хранилище сессий (в БД) ──────────────────────────────

_sms_codes = {}

def _gen_code() -> str:
    return "".join(random.choices(string.digits, k=4))

def _gen_token() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=32))

async def _init_sessions_table():
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS master_sessions (
            token TEXT PRIMARY KEY,
            master_id INTEGER,
            master_name TEXT,
            telegram_id INTEGER,
            expires TEXT,
            role TEXT DEFAULT 'master_edit'
        )""")
        await db.commit()

async def _save_session(token: str, master_id: int, master_name: str, telegram_id: int, role: str = "master_edit"):
    expires = (datetime.now() + timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S")  # 10 лет
    await _init_sessions_table()
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO master_sessions (token, master_id, master_name, telegram_id, expires, role) VALUES (?,?,?,?,?,?)",
            (token, master_id, master_name, telegram_id, expires, role),
        )
        await db.commit()

async def _get_session(token: str) -> dict | None:
    await _init_sessions_table()
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM master_sessions WHERE token = ?", (token,))
        row = await cur.fetchone()
        if not row:
            return None
        row = dict(row)
        if datetime.now() > datetime.strptime(row["expires"], "%Y-%m-%d %H:%M:%S"):
            await db.execute("DELETE FROM master_sessions WHERE token = ?", (token,))
            await db.commit()
            return None
        # Обратная совместимость: если role нет — дефолт master_edit
        if "role" not in row:
            row["role"] = "master_edit"
        # Суперадмин — всегда super_admin (по имени или telegram_id)
        if row.get("master_name") == "Суперадмин" or row.get("telegram_id") == config.SUPERADMIN_TG_ID:
            row["role"] = "super_admin"
        return row

async def _get_permissions(master_id: int) -> dict:
    """Загрузить гранулярные permissions пользователя."""
    defaults = {"view_clients": "own", "edit_bookings": "own", "edit_schedule": "own", "finance": 0, "broadcast": 0, "manage_masters": 0}
    if not master_id:
        return defaults
    try:
        async with aiosqlite.connect(config.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM user_permissions WHERE master_id = ?", (master_id,))
            row = await cur.fetchone()
            if row:
                return dict(row)
    except Exception:
        pass
    return defaults

def _require_role(session: dict, allowed: list) -> bool:
    """Проверить что роль пользователя в списке разрешённых."""
    role = session.get("role", "master_edit")
    return role in allowed

async def _get_session_or_crm(token: str | None, request: Request) -> dict | None:
    """Получить сессию по токену ИЛИ по CRM cookie."""
    if token:
        s = await _get_session(token)
        if s:
            return s
    # Fallback: CRM cookie (per-salon or legacy)
    if _auth_cookie_ok(request):
        return {"master_id": 0, "master_name": "CRM Admin", "telegram_id": 0, "role": "super_admin"}
    return None

async def _notify_admin(booking, booking_id: int):
    """Отправить уведомление админу в Telegram о новой записи."""
    try:
        import db as db_module
        ncfg = await db_module.get_notify_config()
        if not db_module.is_notify_enabled(ncfg, "admin_alert"):
            return
        import httpx
        text = (
            f"📅 *Новая запись через CRM!*\n\n"
            f"Клиент: {booking.client_name or '—'}\n"
            f"Телефон: {booking.phone or '—'}\n"
            f"Мастер: {booking.master_name}\n"
            f"Дата: {booking.date}\n"
            f"Время: {booking.time}\n"
        )
        admin_ids = await _get_admin_ids()
        async with httpx.AsyncClient() as client:
            for admin_id in admin_ids:
                await client.post(
                    f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                    json={"chat_id": admin_id, "text": text, "parse_mode": "Markdown"},
                )
    except Exception as e:
        log.warning(f"Не удалось отправить уведомление админу: {e}")


async def _get_admin_ids() -> list[int]:
    """ADMIN_IDS: из salon_settings (если заданы в CRM), иначе из env."""
    try:
        import db as db_module
        raw = await db_module.get_setting("admin_ids", "")
        if raw:
            return [int(x.strip()) for x in raw.replace(";", ",").split(",") if x.strip().isdigit()]
    except Exception:
        pass
    return list(config.ADMIN_IDS)

async def _send_tg(chat_id: int, text: str):
    """Отправить сообщение клиенту через Telegram Bot API."""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
    except Exception as e:
        log.warning(f"Не удалось отправить сообщение в TG {chat_id}: {e}")

async def _notify_master(master_name: str, text: str):
    """Отправить уведомление мастеру в Telegram."""
    try:
        import httpx
        async with aiosqlite.connect(config.DB_PATH) as db:
            cur = await db.execute(
                "SELECT telegram_id FROM masters WHERE name = ? AND telegram_id > 0", (master_name,)
            )
            row = await cur.fetchone()
            if not row:
                return
            tg_id = row[0]

        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                json={"chat_id": tg_id, "text": text, "parse_mode": "Markdown"},
            )
            log.info(f"Уведомление мастеру {master_name} (tg={tg_id}) отправлено")
    except Exception as e:
        log.warning(f"Не удалось отправить уведомление мастеру {master_name}: {e}")


async def _tg_send(chat_id: int, text: str):
    """Прямая отправка в Telegram (chat_id = user id)."""
    if not chat_id:
        return
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": text},
                timeout=10,
            )
    except Exception as e:
        log.warning(f"waitlist TG send failed chat={chat_id}: {e}")

# ── HTML-страницы (с cache-busting) ─────────────────────

def _no_cache(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


async def _template_context(request: Request, **extra) -> dict:
    """Контекст шаблона с salon_name, salon_logo и org_type из БД."""
    import db as db_module
    salon_name = await db_module.get_setting("salon_name", config.SALON_NAME)
    salon_logo = await db_module.get_setting("salon_logo_path", "/static/logo.png")
    flags = await db_module.get_feature_flags()
    org_type = flags.get("ORG_TYPE", "beauty")
    ctx = {"salon_name": salon_name, "salon_logo": salon_logo, "org_type": org_type}
    ctx.update(extra)
    return ctx

@app.get("/widget", response_class=HTMLResponse)
async def page_widget(request: Request):
    if not config.WIDGET_ENABLED:
        raise HTTPException(404, "Виджет отключён")
    ctx = await _template_context(request)
    r = templates.TemplateResponse(request, "widget.html", ctx)
    _no_cache(r)
    return r

@app.get("/finance", response_class=HTMLResponse)
async def page_finance(request: Request):
    ctx = await _template_context(request, page="finance")
    r = templates.TemplateResponse(request, "finance.html", ctx)
    _no_cache(r)
    return r

@app.get("/schedule", response_class=HTMLResponse)
async def page_schedule(request: Request):
    ctx = await _template_context(request, page="schedule")
    r = templates.TemplateResponse(request, "schedule.html", ctx)
    _no_cache(r)
    return r

@app.get("/bookings", response_class=HTMLResponse)
async def page_bookings(request: Request):
    ctx = await _template_context(request, page="bookings")
    r = templates.TemplateResponse(request, "bookings_page.html", ctx)
    _no_cache(r)
    return r

async def _master_session_ok(request: Request) -> bool:
    """Dashboard доступен при валидной master-сессии (cookie/query) или CRM cookie."""
    tok = request.cookies.get("master_session") or request.query_params.get("token")
    if tok and await _get_session(tok):
        return True
    if _auth_cookie_ok(request):
        return True
    return False

@app.get("/master", response_class=HTMLResponse)
async def page_master_login(request: Request):
    ctx = await _template_context(request)
    r = templates.TemplateResponse(request, "master_login.html", ctx)
    _no_cache(r)
    return r

@app.get("/master/dashboard", response_class=HTMLResponse)
async def page_master_dashboard(request: Request):
    if not await _master_session_ok(request):
        return RedirectResponse(url="/master", status_code=302)
    ctx = await _template_context(request, page="dashboard")
    r = templates.TemplateResponse(request, "master_dashboard.html", ctx)
    _no_cache(r)
    return r

@app.get("/masters", response_class=HTMLResponse)
async def page_masters(request: Request):
    ctx = await _template_context(request, page="masters")
    r = templates.TemplateResponse(request, "masters.html", ctx)
    _no_cache(r)
    return r

@app.get("/clients", response_class=HTMLResponse)
async def page_clients(request: Request):
    ctx = await _template_context(request, page="clients")
    r = templates.TemplateResponse(request, "clients_page.html", ctx)
    _no_cache(r)
    return r

@app.get("/")
async def page_root():
    """Корень URL → дашборд (без 404). /dashboard сам уводит на /login без cookie."""
    return RedirectResponse(url="/dashboard", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
async def page_crm_dashboard(request: Request):
    ctx = await _template_context(request, page="dashboard")
    r = templates.TemplateResponse(request, "crm_dashboard.html", ctx)
    _no_cache(r)
    return r

@app.get("/analytics", response_class=HTMLResponse)
async def page_analytics(request: Request):
    ctx = await _template_context(request, page="analytics")
    r = templates.TemplateResponse(request, "client_analytics.html", ctx)
    _no_cache(r)
    return r

@app.get("/users", response_class=HTMLResponse)
async def page_users(request: Request):
    ctx = await _template_context(request, page="users")
    r = templates.TemplateResponse(request, "users_page.html", ctx)
    _no_cache(r)
    return r

@app.get("/services", response_class=HTMLResponse)
async def page_services(request: Request):
    ctx = await _template_context(request, page="services")
    r = templates.TemplateResponse(request, "services_page.html", ctx)
    _no_cache(r)
    return r

@app.get("/bot", response_class=HTMLResponse)
async def page_bot(request: Request):
    ctx = await _template_context(request, page="bot")
    r = templates.TemplateResponse(request, "bot.html", ctx)
    _no_cache(r)
    return r

@app.get("/masters-app", response_class=HTMLResponse)
async def page_masters_app(request: Request):
    ctx = await _template_context(request, page="masters-app")
    r = templates.TemplateResponse(request, "masters_app.html", ctx)
    _no_cache(r)
    return r


def _make_manage_token(booking_id: int) -> str:
    msg = f"manage:{booking_id}".encode()
    return hmac.new(CRM_SECRET.encode(), msg, hashlib.sha256).hexdigest()[:32]


@app.get("/manage-booking", response_class=HTMLResponse)
async def page_manage_booking(request: Request, id: int = Query(...), token: str = Query(...)):
    """Self-service: просмотр/отмена записи по deep-link из бота."""
    expected = _make_manage_token(id)
    if not hmac.compare_digest(expected, token or ""):
        raise HTTPException(403, "Недействительная ссылка")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE id = ?", (id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Запись не найдена")
        booking = dict(row)
    ctx = await _template_context(request, booking=booking, token=token, bid=id)
    r = templates.TemplateResponse(request, "manage_booking.html", ctx)
    _no_cache(r)
    return r


@app.get("/api/bookings/manage/{booking_id}")
async def manage_booking_get(booking_id: int, token: str = Query(...)):
    expected = _make_manage_token(booking_id)
    if not hmac.compare_digest(expected, token or ""):
        raise HTTPException(403, "Недействительная ссылка")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Запись не найдена")
        booking = dict(row)
    import db as db_module
    booking["services"] = await db_module.get_booking_services(booking_id)
    return booking


@app.post("/api/bookings/manage/{booking_id}/cancel")
async def manage_booking_cancel(booking_id: int, token: str = Query(...)):
    expected = _make_manage_token(booking_id)
    if not hmac.compare_digest(expected, token or ""):
        raise HTTPException(403, "Недействительная ссылка")
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Запись не найдена")
        booking = dict(row)
        try:
            booking_dt = datetime.strptime(f"{booking['date']} {booking['time']}", "%Y-%m-%d %H:%M")
            if (booking_dt - datetime.now()).total_seconds() < 7200:
                raise HTTPException(400, "Нельзя отменить менее чем за 2 часа до записи")
        except HTTPException:
            raise
        except Exception:
            pass
        import db as db_module
        await db_module.cancel_booking(booking_id)
        matches = await db_module.notify_waitlist_for_slot(
            booking.get("master_name", ""), booking.get("date", ""), booking.get("time", ""),
        )
        for m in matches:
            asyncio.create_task(_tg_send(
                m["telegram_id"],
                f"🔔 Освободилось окно!\n\nМастер: {booking.get('master_name','—')}\n"
                f"Дата: {booking.get('date','—')}\nВремя: {booking.get('time','—')}\n\n"
                f"Записывайтесь: /start → Записаться",
            ))
    return {"status": "ok"}


@app.post("/api/bookings/manage/{booking_id}/reschedule")
async def manage_booking_reschedule(booking_id: int, token: str = Query(...), request: Request = None):
    expected = _make_manage_token(booking_id)
    if not hmac.compare_digest(expected, token or ""):
        raise HTTPException(403, "Недействительная ссылка")
    body = await request.json()
    new_date = str(body.get("date") or "")
    new_time = str(body.get("time") or "")
    if not new_date or not new_time:
        raise HTTPException(400, "date и time обязательны")
    import db as db_module
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Запись не найдена")
        existing = dict(row)
        try:
            booking_dt = datetime.strptime(f"{existing['date']} {existing['time']}", "%Y-%m-%d %H:%M")
            if (booking_dt - datetime.now()).total_seconds() < 7200:
                raise HTTPException(400, "Нельзя перенести менее чем за 2 часа до записи")
        except HTTPException:
            raise
        except Exception:
            pass
    new_dur = existing.get("duration_minutes") or 0
    working = await _master_working_slots(existing["master_name"], new_date)
    occupied = await db_module.get_occupied_times(existing["master_name"], new_date, exclude_id=booking_id)
    if not db_module.window_is_free(new_time, new_dur, working, occupied):
        raise HTTPException(409, "Выбранное время занято или не помещается")
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE bookings SET date = ?, time = ? WHERE id = ?",
            (new_date, new_time, booking_id),
        )
        await db.commit()
    return {"status": "ok", "date": new_date, "time": new_time}


# ── API: Авторизация мастера ─────────────────────────────

@app.post("/api/master/auth/request")
async def auth_request(req: AuthRequest):
    # Глобальный kill-switch входа мастеров из CRM
    try:
        import db as db_module
        login_on = (await db_module.get_setting("master_login_enabled", "true")).lower() != "false"
    except Exception:
        login_on = True
    if not login_on:
        raise HTTPException(403, "Вход в приложение мастеров отключён администратором")
    phone = req.phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not phone.startswith("+"):
        phone = "+" + phone

    log.info(f"AUTH: phone={phone}")

    # Суперадмин — принудительно
    if phone == config.SUPERADMIN_PHONE:
        code = _gen_code()
        _sms_codes[phone] = {
            "code": code,
            "expires": datetime.now() + timedelta(minutes=5),
            "master_id": 0,
            "master_name": "Суперадмин",
            "telegram_id": config.SUPERADMIN_TG_ID,
            "role": "super_admin",
        }
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                json={"chat_id": config.SUPERADMIN_TG_ID, "text": f"🔐 Код для входа в CRM: *{code}*\nДействителен 5 минут.", "parse_mode": "Markdown"},
            )
        return {"status": "ok", "message": "Код отправлен в Telegram"}

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Сначала ищем мастера с таким телефоном в таблице masters
        cur = await db.execute("SELECT * FROM masters WHERE phone = ? AND is_active = 1", (phone,))
        master = await cur.fetchone()
        
        if master:
            master = dict(master)
            log.info(f"AUTH: found master '{master['name']}' id={master['id']}")
            tg_id = master.get("telegram_id", 0)
            # Если telegram_id не задан — ищем в clients по телефону
            if not tg_id:
                phone_no_plus = phone.lstrip("+")
                cur = await db.execute("SELECT telegram_id FROM clients WHERE phone IN (?, ?) LIMIT 1", (phone, phone_no_plus))
                row = await cur.fetchone()
                if row:
                    tg_id = row["telegram_id"]
                    log.info(f"AUTH: found tg_id={tg_id} from clients table")
        else:
            # Ищем всех клиентов с таким телефоном (и с +, и без — Telegram хранит без +)
            phone_no_plus = phone.lstrip("+")
            cur = await db.execute("SELECT telegram_id FROM clients WHERE phone IN (?, ?)", (phone, phone_no_plus))
            clients = await cur.fetchall()
            if not clients:
                raise HTTPException(404, "Мастер с таким телефоном не найден")
            
            # Проверяем, не админ ли это (среди всех клиентов с этим телефоном)
            admin_tg_id = None
            for row in clients:
                if row["telegram_id"] in config.ADMIN_IDS:
                    admin_tg_id = row["telegram_id"]
                    break
            
            if admin_tg_id:
                log.info(f"AUTH: admin login, tg_id={admin_tg_id}")
                tg_id = admin_tg_id
                master = {"id": 0, "name": "АДМИН", "telegram_id": tg_id}
            else:
                # Берём первого клиента и ищем мастера
                tg_id = clients[0]["telegram_id"]
                cur = await db.execute("SELECT * FROM masters WHERE telegram_id = ? AND is_active = 1", (tg_id,))
                master = await cur.fetchone()
                if not master:
                    raise HTTPException(404, "Мастер с таким телефоном не найден")
                master = dict(master)

        # Автоматически привязываем telegram_id мастера если ещё не привязан
        if master.get("id") and tg_id and not master.get("telegram_id"):
            try:
                await db.execute("UPDATE masters SET telegram_id = ? WHERE id = ?", (tg_id, master["id"]))
                await db.commit()
                log.info(f"AUTH: linked telegram_id={tg_id} to master '{master['name']}'")
            except Exception as e:
                log.warning(f"AUTH: failed to link telegram_id: {e}")

    # Отправляем код в Telegram — сначала проверяем tg_id
    if not tg_id:
        raise HTTPException(400, "Мастер не привязан к Telegram. Обратитесь к администратору.")

    code = _gen_code()
    role = master.get("role", "master_edit")
    # Суперадмин по телефону — всегда super_admin
    if phone == config.SUPERADMIN_PHONE:
        role = "super_admin"
    _sms_codes[phone] = {
        "code": code,
        "expires": datetime.now() + timedelta(minutes=5),
        "master_id": master["id"],
        "master_name": master["name"],
        "telegram_id": tg_id,
        "role": role,
    }

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": tg_id,
                    "text": f"🔐 Код для входа в CRM: *{code}*\nДействителен 5 минут.",
                    "parse_mode": "Markdown",
                },
            )
            if resp.status_code != 200 or not resp.json().get("ok"):
                log.warning(f"AUTH: Telegram send failed: {resp.status_code} {resp.text[:200]}")
                raise HTTPException(400, "Не удалось отправить код в Telegram. Попробуйте позже.")
    except HTTPException:
        raise
    except Exception as e:
        log.warning(f"Не удалось отправить код: {e}")
        raise HTTPException(400, "Не удалось отправить код в Telegram. Попробуйте позже.")

    return {"status": "ok", "message": "Код отправлен в Telegram"}

@app.post("/api/master/auth/verify")
async def auth_verify(req: AuthVerify):
    phone = req.phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not phone.startswith("+"):
        phone = "+" + phone

    stored = _sms_codes.get(phone)
    if not stored:
        raise HTTPException(400, "Код не запрашивался")
    if datetime.now() > stored["expires"]:
        del _sms_codes[phone]
        raise HTTPException(400, "Код истёк")
    if stored["code"] != req.code:
        raise HTTPException(400, "Неверный код")

    token = _gen_token()
    role = stored.get("role", "master_edit")
    try:
        await _save_session(token, stored["master_id"], stored["master_name"], stored["telegram_id"], role)
    except Exception as e:
        log.error(f"AUTH: _save_session failed: {e}")
        raise HTTPException(500, "Ошибка сохранения сессии. Попробуйте войти снова.")
    del _sms_codes[phone]
    resp = JSONResponse({"status": "ok", "token": token, "master_id": stored["master_id"], "master_name": stored["master_name"], "role": role})
    resp.set_cookie(
        "master_session", token,
        max_age=3650 * 24 * 3600,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return resp

# ── API: Записи мастера ──────────────────────────────────

@app.get("/api/master/today")
async def master_today(token: str = Query(...)):
    s = await _get_session(token)
    if not s:
        raise HTTPException(401, "Не авторизован")
    today = datetime.now().strftime("%Y-%m-%d")
    is_admin = _require_role(s, ["super_admin", "director", "admin"]) or s["master_name"] == "АДМИН"
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if is_admin:
            cur = await db.execute(
                "SELECT * FROM bookings WHERE date = ? AND (booking_type IS NULL OR booking_type != 'coworking') ORDER BY time",
                (today,),
            )
        else:
            cur = await db.execute(
                "SELECT * FROM bookings WHERE master_name = ? AND date = ? AND (booking_type IS NULL OR booking_type != 'coworking') ORDER BY time",
                (s["master_name"], today),
            )
        return [dict(r) for r in await cur.fetchall()]

@app.get("/api/master/week")
async def master_week(token: str = Query(...)):
    s = await _get_session(token)
    if not s:
        raise HTTPException(401, "Не авторизован")
    is_admin = _require_role(s, ["super_admin", "director", "admin"]) or s["master_name"] == "АДМИН"
    today = datetime.now()
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        ph = ",".join("?" * len(dates))
        if is_admin:
            cur = await db.execute(
                f"SELECT * FROM bookings WHERE date IN ({ph}) AND (booking_type IS NULL OR booking_type != 'coworking') ORDER BY date, time", dates,
            )
        else:
            cur = await db.execute(
                f"SELECT * FROM bookings WHERE master_name = ? AND date IN ({ph}) AND (booking_type IS NULL OR booking_type != 'coworking') ORDER BY date, time",
                [s["master_name"]] + dates,
            )
        return [dict(r) for r in await cur.fetchall()]

@app.get("/api/master/schedule")
async def master_schedule(token: str = Query(...)):
    """Расписание мастера/админа + записи на неделю (для шахматки)."""
    s = await _get_session(token)
    if not s:
        raise HTTPException(401, "Не авторизован")
    master_name = s["master_name"]
    is_admin = _require_role(s, ["super_admin", "director", "admin"]) or master_name == "АДМИН"
    today = datetime.now()
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if is_admin:
            # Админ видит расписание всех мастеров
            cur = await db.execute("SELECT * FROM master_schedule ORDER BY master_name, day_of_week")
            schedule = [dict(r) for r in await cur.fetchall()]
        else:
            cur = await db.execute(
                "SELECT * FROM master_schedule WHERE master_name = ? ORDER BY day_of_week",
                (master_name,),
            )
            schedule = [dict(r) for r in await cur.fetchall()]

        # Записи на неделю
        ph = ",".join("?" * len(dates))
        if is_admin:
            cur = await db.execute(
                f"SELECT * FROM bookings WHERE date IN ({ph}) ORDER BY date, time", dates,
            )
        else:
            cur = await db.execute(
                f"SELECT * FROM bookings WHERE master_name = ? AND date IN ({ph}) ORDER BY date, time",
                [master_name] + dates,
            )
        bookings = [dict(r) for r in await cur.fetchall()]

        return {"schedule": schedule, "bookings": bookings, "dates": dates}

@app.put("/api/master/schedule")
async def update_master_schedule(token: str = Query(...), items: list[ScheduleItem] = []):
    """Обновить своё расписание (выходные)."""
    s = await _get_session(token)
    if not s:
        raise HTTPException(401, "Не авторизован")
    master_name = s["master_name"]

    async with aiosqlite.connect(config.DB_PATH) as db:
        for item in items:
            await db.execute(
                """INSERT INTO master_schedule (master_name, day_of_week, start_time, end_time, is_day_off)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(master_name, day_of_week) DO UPDATE SET
                   start_time=?, end_time=?, is_day_off=?""",
                (master_name, item.day_of_week, item.start_time, item.end_time, item.is_day_off,
                 item.start_time, item.end_time, item.is_day_off),
            )
        await db.commit()
        return {"status": "ok"}

@app.get("/api/master/clients")
async def master_clients(token: str = Query(...), filter: str = Query("active")):
    """Клиенты мастера/админа: active = есть записи за30 дней, lost = нет записей >30 дней."""
    s = await _get_session(token)
    if not s:
        raise HTTPException(401, "Не авторизован")
    master_name = s["master_name"]
    is_admin = _require_role(s, ["super_admin", "director", "admin"]) or master_name == "АДМИН"

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if is_admin:
            cur = await db.execute(
                """SELECT client_name, telegram_id,
                          MIN(date) as first_visit, MAX(date) as last_visit,
                          COUNT(*) as visit_count
                   FROM bookings
                   WHERE client_name != ''
                   GROUP BY client_name
                   ORDER BY last_visit DESC""",
            )
        else:
            cur = await db.execute(
                """SELECT client_name, telegram_id,
                          MIN(date) as first_visit, MAX(date) as last_visit,
                          COUNT(*) as visit_count
                   FROM bookings
                   WHERE master_name = ? AND client_name != ''
                   GROUP BY client_name
                   ORDER BY last_visit DESC""",
                (master_name,),
            )
        all_clients = [dict(r) for r in await cur.fetchall()]

        today = datetime.now().strftime("%Y-%m-%d")
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        result = []
        for c in all_clients:
            is_active = c["last_visit"] >= cutoff
            # Получаем телефон из таблицы clients если есть
            phone = ""
            if c["telegram_id"]:
                cur2 = await db.execute(
                    "SELECT phone FROM clients WHERE telegram_id = ?", (c["telegram_id"],)
                )
                row = await cur2.fetchone()
                if row and row["phone"]:
                    phone = row["phone"]

            entry = {
                "name": c["client_name"],
                "phone": phone,
                "first_visit": c["first_visit"],
                "last_visit": c["last_visit"],
                "visit_count": c["visit_count"],
                "is_active": is_active,
            }

            if filter == "active" and is_active:
                result.append(entry)
            elif filter == "lost" and not is_active:
                result.append(entry)

        return result

# ── API: Часы работы салона ──────────────────────────────

@app.get("/api/salon-hours")
async def salon_hours():
    """Вернуть часы работы салона по дням недели."""
    return {str(k): list(v) for k, v in config.SALON_HOURS.items()}

# ── API: Мастера ─────────────────────────────────────────

async def _current_org_type() -> str:
    import db as db_module
    flags = await db_module.get_feature_flags()
    return flags.get("ORG_TYPE", "beauty") or "beauty"

def _filter_masters_by_org(masters: list, org_type: str) -> list:
    """Показывать мастера текущего типа; пустой org_type = beauty (не «всегда»)."""
    out = []
    for m in masters:
        t = (m.get("org_type") or "").strip() or "beauty"
        if t == org_type:
            out.append(m)
    return out

def _is_admin_master(m: dict) -> bool:
    role = (m.get("role") or "").strip().lower()
    name = (m.get("name") or "").strip().upper()
    return role in ("super_admin", "director", "admin") or name == "АДМИН"

@app.get("/api/masters")
async def list_masters(exclude_admins: int = Query(0)):
    """exclude_admins=1 — для шахматки: не показывать админов как «мастеров»."""
    org = await _current_org_type()
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM masters WHERE is_active = 1 AND phone != ? ORDER BY name",
            (config.SUPERADMIN_PHONE,),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    rows = _filter_masters_by_org(rows, org)
    if exclude_admins:
        rows = [m for m in rows if not _is_admin_master(m)]
    return rows

async def _seed_master_work_week(db, master_name: str):
    """7 рабочих дней по умолчанию (часы салона), is_day_off=0."""
    import db as db_module
    start = (await db_module.get_setting("salon_hours_start", "10")) or "10"
    end = (await db_module.get_setting("salon_hours_end", "20")) or "20"
    st = f"{int(start):02d}:00"
    en = f"{int(end):02d}:00"
    for dow in range(7):
        await db.execute(
            """INSERT INTO master_schedule (master_name, day_of_week, start_time, end_time, is_day_off)
               VALUES (?,?,?,?,0)
               ON CONFLICT(master_name, day_of_week) DO NOTHING""",
            (master_name, dow, st, en),
        )
    await db.commit()


@app.post("/api/masters")
async def create_master(m: MasterCreate):
    org = m.org_type or await _current_org_type()
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO masters (name, specialization, description, categories, phone, org_type) VALUES (?,?,?,?,?,?)",
            (m.name, m.specialization, m.description, m.categories, m.phone, org),
        )
        await db.commit()
        await _seed_master_work_week(db, m.name)
        return {"id": cur.lastrowid}

@app.put("/api/masters/{master_id}")
async def update_master(master_id: int, m: MasterCreate):
    org = m.org_type or await _current_org_type()
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "UPDATE masters SET name=?, specialization=?, description=?, categories=?, phone=?, org_type=? WHERE id=?",
            (m.name, m.specialization, m.description, m.categories, m.phone, org, master_id),
        )
        await db.commit()
        return {"status": "ok"}

@app.delete("/api/masters/{master_id}")
async def delete_master(master_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE masters SET is_active = 0 WHERE id = ?", (master_id,))
        await db.commit()
        return {"status": "ok"}

@app.get("/api/masters-with-bookings")
async def masters_with_bookings():
    """Мастера с количеством записей (для приложения мастеров)."""
    org = await _current_org_type()
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM masters WHERE is_active = 1 AND phone != ? ORDER BY name",
            (config.SUPERADMIN_PHONE,),
        )
        masters = _filter_masters_by_org([dict(r) for r in await cur.fetchall()], org)

        result = []
        for m in masters:
            cur = await db.execute(
                "SELECT * FROM bookings WHERE master_name = ? ORDER BY date DESC, time DESC LIMIT 20",
                (m["name"],),
            )
            bookings = [dict(r) for r in await cur.fetchall()]
            total = len(bookings)
            active = sum(1 for b in bookings if not b.get("completed") and not b.get("cancelled"))
            completed = sum(1 for b in bookings if b.get("completed"))
            cancelled = sum(1 for b in bookings if b.get("cancelled"))
            result.append({
                "id": m["id"],
                "name": m["name"],
                "specialization": m.get("specialization", ""),
                "total_bookings": total,
                "active_count": active,
                "completed_count": completed,
                "cancelled_count": cancelled,
                "bookings": bookings,
            })
        return result

# ── API: Услуги ──────────────────────────────────────────

class ServiceCreate(BaseModel):
    category_title: str
    category_note: str = ""
    category_index: int | None = None  # если None — берём из category_title
    name: str
    price: str
    gender: str = "all"
    duration_minutes: int = 0

class ServiceUpdate(BaseModel):
    name: str | None = None
    price: str | None = None
    gender: str | None = None
    category_title: str | None = None
    category_note: str | None = None
    is_active: int | None = None
    sort_order: int | None = None
    duration_minutes: int | None = None

class CategoryCreate(BaseModel):
    title: str
    note: str = ""
    gender: str = "all"

@app.get("/api/services")
async def list_services():
    """Все активные услуги из БД."""
    import db as db_module
    services = await db_module.get_all_services()
    return services

@app.get("/api/services/categories")
async def list_categories():
    """Категории услуг из БД."""
    import db as db_module
    return await db_module.get_service_categories()

@app.get("/api/services/grouped")
async def list_services_grouped():
    """Услуги, сгруппированные по категориям (для фронтенда)."""
    import db as db_module
    return await db_module.get_services_by_category()

@app.post("/api/services")
async def create_service(s: ServiceCreate):
    """Добавить услугу."""
    import db as db_module
    # Если category_index не задан — ищем по названию
    if s.category_index is None:
        cats = await db_module.get_service_categories()
        match = next((c for c in cats if c["category_title"] == s.category_title), None)
        if match:
            cat_index = match["category_index"]
            cat_note = match.get("category_note", "")
        else:
            # Новая категория
            cat_index = await db_module.add_category(s.category_title, s.category_note, s.gender)
            cat_note = s.category_note
    else:
        cat_index = s.category_index
        cat_note = s.category_note
    service_id = await db_module.add_service(
        category_title=s.category_title,
        category_note=cat_note,
        category_index=cat_index,
        name=s.name,
        price=s.price,
        gender=s.gender,
        duration_minutes=max(0, int(s.duration_minutes or 0)),
    )
    await db_module.log_audit("crm", "service_create", "service", str(service_id), s.name)
    return {"id": service_id}

@app.put("/api/services/{service_id}")
async def update_service(service_id: int, s: ServiceUpdate):
    """Редактировать услугу."""
    import db as db_module
    existing = await db_module.get_service_by_id(service_id)
    if not existing:
        raise HTTPException(404, "Услуга не найдена")
    updates = {}
    if s.name is not None:
        updates["name"] = s.name
    if s.price is not None:
        updates["price"] = s.price
    if s.gender is not None:
        updates["gender"] = s.gender
    if s.category_title is not None:
        updates["category_title"] = s.category_title
    if s.category_note is not None:
        updates["category_note"] = s.category_note
    if s.is_active is not None:
        updates["is_active"] = s.is_active
    if s.sort_order is not None:
        updates["sort_order"] = s.sort_order
    if s.duration_minutes is not None:
        updates["duration_minutes"] = max(0, int(s.duration_minutes or 0))
    if updates:
        await db_module.update_service(service_id, **updates)
        await db_module.log_audit("crm", "service_update", "service", str(service_id), str(updates))
    return {"status": "ok"}

@app.delete("/api/services/{service_id}")
async def delete_service(service_id: int):
    """Удалить услугу (мягко)."""
    import db as db_module
    existing = await db_module.get_service_by_id(service_id)
    if not existing:
        raise HTTPException(404, "Услуга не найдена")
    await db_module.delete_service(service_id)
    await db_module.log_audit("crm", "service_delete", "service", str(service_id), existing.get("name", ""))
    return {"status": "ok"}

@app.post("/api/services/categories")
async def create_category(c: CategoryCreate):
    """Добавить категорию."""
    import db as db_module
    cat_index = await db_module.add_category(c.title, c.note, c.gender)
    return {"category_index": cat_index}

# ── API: Записи ──────────────────────────────────────────

async def _resolve_booking_duration(service_name: str, explicit: int | None) -> int:
    """Длительность записи: явное значение приоритетнее, иначе из услуги, иначе 0 (=15 мин)."""
    if explicit is not None:
        return max(0, int(explicit or 0))
    if not service_name:
        return 0
    import db as db_module
    async with aiosqlite.connect(config.DB_PATH) as adb:
        adb.row_factory = aiosqlite.Row
        cur = await adb.execute(
            "SELECT duration_minutes FROM services WHERE name = ? AND is_active = 1 ORDER BY id LIMIT 1",
            (service_name,),
        )
        row = await cur.fetchone()
        return max(0, int(row["duration_minutes"] or 0)) if row else 0


async def _master_working_slots(master_name: str, date: str) -> list[str]:
    """Рабочие 15-мин слоты мастера на дату (кастомное расписание → недельное → часы салона)."""
    import db as db_module
    dt = datetime.strptime(date, "%Y-%m-%d")
    dow = dt.weekday()
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM master_date_schedule WHERE master_name = ? AND date = ?",
            (master_name, date),
        )
        date_sched = await cur.fetchone()
        if date_sched:
            if date_sched["is_day_off"]:
                return []
            slots_str = date_sched["time_slots"] or ""
            hours = [h.strip() for h in slots_str.split(",") if h.strip()] if slots_str else []
            return db_module._clamp_to_salon(hours, dow)

        cur = await db.execute(
            "SELECT * FROM master_schedule WHERE master_name = ? AND day_of_week = ?",
            (master_name, dow),
        )
        sched = await cur.fetchone()
        if not sched or sched["is_day_off"]:
            return db_module.get_salon_slots(dow)

        selected = sched["selected_hours"] if "selected_hours" in sched.keys() else ""
        if selected:
            hours = [h.strip() for h in selected.split(",") if h.strip()]
            return db_module._clamp_to_salon(hours, dow)

        start_h = int(sched["start_time"].split(":")[0])
        end_h = int(sched["end_time"].split(":")[0])
        hours = [f"{h:02d}:{m:02d}" for h in range(start_h, end_h) for m in (0, 15, 30, 45)]
        return db_module._clamp_to_salon(hours, dow)


@app.get("/api/bookings")
async def list_bookings(
    date: str = Query(None),
    master_name: str = Query(None),
):
    import db as db_module
    org = await _current_org_type()
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM bookings WHERE 1=1"
        p = []
        if org == "beauty":
            # старые БД могут не иметь booking_type — не роняем 500
            try:
                cur = await db.execute("SELECT 1 FROM pragma_table_info('bookings') WHERE name='booking_type'")
                has_bt = await cur.fetchone() is not None
            except Exception:
                has_bt = True
            if has_bt:
                q += " AND (booking_type IS NULL OR booking_type != 'coworking')"
        if date:
            q += " AND date = ?"
            p.append(date)
        if master_name:
            q += " AND master_name = ?"
            p.append(master_name)
        q += " ORDER BY date, time"
        cur = await db.execute(q, p)
        rows = [dict(r) for r in await cur.fetchall()]
    for row in rows:
        svcs = await db_module.get_booking_services(row["id"])
        if svcs:
            row["services"] = svcs
    return rows

@app.get("/api/bookings/grouped")
async def bookings_grouped(search: str = Query(None)):
    """Записи, сгруппированные по клиентам."""
    org = await _current_org_type()
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        q = "SELECT * FROM bookings WHERE 1=1"
        params = []
        if org == "beauty":
            q += " AND (booking_type IS NULL OR booking_type != 'coworking')"
        if search:
            q += " AND (client_name LIKE ? OR phone LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        q += " ORDER BY date DESC, time DESC"
        cur = await db.execute(q, params)
        all_bookings = [dict(r) for r in await cur.fetchall()]

    groups = {}
    for b in all_bookings:
        key = (b.get("client_name", "") or "", b.get("phone", "") or "")
        if key not in groups:
            groups[key] = {
                "client_name": b.get("client_name", ""),
                "phone": b.get("phone", ""),
                "bookings": [],
                "total_bookings": 0,
                "active_count": 0,
                "completed_count": 0,
                "cancelled_count": 0,
                "last_visit": None,
            }
        g = groups[key]
        g["bookings"].append(b)
        g["total_bookings"] += 1
        if not b.get("cancelled") and not b.get("completed"):
            g["active_count"] += 1
        if b.get("completed"):
            g["completed_count"] += 1
        if b.get("cancelled"):
            g["cancelled_count"] += 1
        if not g["last_visit"] or b["date"] > g["last_visit"]:
            g["last_visit"] = b["date"]

    return sorted(groups.values(), key=lambda x: x["last_visit"] or "", reverse=True)

@app.post("/api/bookings")
async def create_booking(b: BookingCreate):
    import db as db_module

    # Валидация: мастер существует
    async with aiosqlite.connect(config.DB_PATH) as adb:
        adb.row_factory = aiosqlite.Row
        cur = await adb.execute("SELECT id FROM masters WHERE name = ? AND is_active = 1", (b.master_name,))
        if not await cur.fetchone():
            raise HTTPException(400, f"Мастер '{b.master_name}' не найден")

    # Валидация: дата не в прошлом
    today = datetime.now().strftime("%Y-%m-%d")
    if b.date < today:
        raise HTTPException(400, "Нельзя записаться на прошедшую дату")

    # Валидация: слот в часах салона
    try:
        dt = datetime.strptime(b.date, "%Y-%m-%d")
        dow = dt.weekday()
        salon_slots = db_module.get_salon_slots(dow)
        if b.time not in salon_slots:
            raise HTTPException(400, f"Время {b.time} вне графика работы салона")
    except ValueError:
        raise HTTPException(400, "Неверный формат даты")

    # Длительность: explicit → Σ по service_ids → lookup по service_name
    multi_svcs: list[dict] = []
    if b.service_ids:
        multi_svcs = await db_module.resolve_services_by_ids(b.service_ids)
        if not multi_svcs:
            raise HTTPException(400, "Услуги не найдены")
    if multi_svcs:
        dur = sum(max(0, int(s.get("duration_minutes") or 0)) for s in multi_svcs)
        # продолжаемость: каждая ≥0, 0 трактуем как 15 при сумме? план: Σ как есть, 0 → 0 слотов extra
        # но 0 означает 15 мин в сетке — для мульти считаем каждый как slots_needed
        dur = sum(db_module.slots_needed(s.get("duration_minutes")) * 15 for s in multi_svcs)
        service_name = b.service_name or " + ".join(s["name"] for s in multi_svcs)
        price = b.price or " + ".join(str(s.get("price") or "") for s in multi_svcs)
    else:
        dur = await _resolve_booking_duration(b.service_name, b.duration_minutes)
        service_name = b.service_name
        price = b.price
        # duration_minutes explicit + multi: if both, prefer Σ from ids when present

    working = await _master_working_slots(b.master_name, b.date)
    if not db_module.window_is_free(b.time, dur, working, set()):
        raise HTTPException(400, "Услуга не помещается в рабочее время мастера")

    # Атомарное бронирование окна через try_book_slot
    booking_id = await db_module.try_book_slot(
        master_name=b.master_name,
        date=b.date,
        time=b.time,
        client_name=b.client_name,
        telegram_id=b.telegram_id,
        service_name=service_name,
        price=price,
        phone=b.phone,
        duration_minutes=dur,
    )
    if not booking_id:
        raise HTTPException(409, "Слот уже занят")

    if multi_svcs:
        await db_module.set_booking_services(booking_id, [
            {
                "service_id": s["id"],
                "name": s["name"],
                "price": s.get("price") or "",
                "duration_minutes": s.get("duration_minutes") or 0,
            }
            for s in multi_svcs
        ])

    # Промокод
    promo_note = ""
    if (b.promo_code or "").strip():
        promo = await db_module.get_promo(b.promo_code)
        if not promo:
            log.warning(f"promo invalid: {b.promo_code}")
            promo_note = " (промокод не принят)"
        else:
            if await db_module.use_promo(b.promo_code):
                promo_note = f" (промокод {promo['code']} −{promo['percent']}%)"
                await db_module.log_audit(
                    "api", "promo_applied", "booking", str(booking_id),
                    f"code={promo['code']} percent={promo['percent']}",
                )

    # Автоподтверждение если запись <24ч
    try:
        booking_dt = datetime.strptime(f"{b.date} {b.time}", "%Y-%m-%d %H:%M")
        if booking_dt - datetime.now() < timedelta(hours=24):
            async with aiosqlite.connect(config.DB_PATH) as db:
                await db.execute("UPDATE bookings SET confirmed = 1 WHERE id = ?", (booking_id,))
                await db.commit()
            log.info(f"API: auto-confirmed booking #{booking_id} (<24h)")
    except Exception as e:
        log.warning(f"API: auto-confirm failed: {e}")

    # Напоминание за 2 часа отправляет бот (reminder_loop каждые 5 минут).
    # Здесь дубликат не нужен: задача в памяти терялась бы при рестарте API.

    # Уведомления в Telegram
    end_note = ""
    if dur > 15:
        import db as _dbm
        end_note = f" – {_dbm.end_time_for_booking(b.time, dur)} ({_dbm.format_duration(dur)})"
    asyncio.create_task(_notify_admin(b, booking_id))
    asyncio.create_task(_notify_master(b.master_name,
        f"📋 *Новая запись!*\n\n"
        f"Клиент: {b.client_name or '—'}\n"
        f"Телефон: {b.phone or '—'}\n"
        f"Дата: {b.date}\n"
        f"Время: {b.time}{end_note}\n"
        f"Услуга: {service_name or b.service_name or '—'}"
    ))
    return {"id": booking_id, "promo": promo_note}

@app.put("/api/bookings/{booking_id}")
async def update_booking(booking_id: int, b: BookingUpdate):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        existing = await cur.fetchone()
        if not existing:
            raise HTTPException(404, "Запись не найдена")
        existing = dict(existing)
        # Проверка 2 часа
        try:
            booking_dt = datetime.strptime(f"{existing['date']} {existing['time']}", "%Y-%m-%d %H:%M")
            if (booking_dt - datetime.now()).total_seconds() < 7200:
                raise HTTPException(400, "Нельзя изменить менее чем за 2 часа до записи")
        except HTTPException:
            raise
        except Exception:
            pass

        # Проверяем занятость нового окна (если меняются мастер/дата/время/услуга/длительность)
        new_master = b.master_name if b.master_name is not None else existing["master_name"]
        new_date = b.date if b.date is not None else existing["date"]
        new_time = b.time if b.time is not None else existing["time"]
        new_service = b.service_name if b.service_name is not None else existing.get("service_name") or ""
        if b.duration_minutes is not None:
            new_dur = max(0, int(b.duration_minutes or 0))
        elif b.service_name is not None and b.service_name != existing.get("service_name"):
            new_dur = await _resolve_booking_duration(new_service, None)
        else:
            new_dur = existing.get("duration_minutes") or 0

        if (new_master, new_date, new_time, new_service, new_dur) != (
            existing["master_name"], existing["date"], existing["time"],
            existing.get("service_name") or "", existing.get("duration_minutes") or 0,
        ):
            import db as db_module
            working = await _master_working_slots(new_master, new_date)
            occupied = await db_module.get_occupied_times(new_master, new_date, exclude_id=booking_id)
            if not db_module.window_is_free(new_time, new_dur, working, occupied):
                raise HTTPException(409, "Выбранное время занято или не помещается")

        db.row_factory = None
        fields, params = [], []
        if b.master_name is not None:
            fields.append("master_name = ?")
            params.append(b.master_name)
        if b.date is not None:
            fields.append("date = ?")
            params.append(b.date)
        if b.time is not None:
            fields.append("time = ?")
            params.append(b.time)
        if b.client_name is not None:
            fields.append("client_name = ?")
            params.append(b.client_name)
        if b.service_name is not None:
            fields.append("service_name = ?")
            params.append(b.service_name)
        if b.price is not None:
            fields.append("price = ?")
            params.append(b.price)
        if new_dur != (existing.get("duration_minutes") or 0):
            fields.append("duration_minutes = ?")
            params.append(new_dur)
        if fields:
            params.append(booking_id)
            await db.execute(f"UPDATE bookings SET {', '.join(fields)} WHERE id = ?", params)
            await db.commit()
        return {"status": "ok"}

@app.delete("/api/bookings/{booking_id}")
async def delete_booking(booking_id: int):
    import db as db_module
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        await db.execute("DELETE FROM booking_services WHERE booking_id = ?", (booking_id,))
        await db.commit()
        return {"status": "ok"}

@app.post("/api/bookings/{booking_id}/confirm")
async def confirm_booking(booking_id: int):
    import db as db_module
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        booking = await cur.fetchone()
        if not booking:
            raise HTTPException(404, "Запись не найдена")
        booking = dict(booking)
        ids = await db_module.get_range_ids_for_booking(booking_id)
        marks = ",".join("?" * len(ids))
        cur = await db.execute(
            f"SELECT time FROM bookings WHERE id IN ({marks}) ORDER BY time",
            tuple(ids),
        )
        times = [r[0] for r in await cur.fetchall()]
        await db.execute(f"UPDATE bookings SET confirmed = 1 WHERE id IN ({marks})", tuple(ids))
        await db.commit()

    if len(times) <= 1:
        time_line = times[0] if times else booking["time"]
    else:
        time_line = f"{times[0]} – {db_module._add_minutes(times[-1], 15)}"

    asyncio.create_task(_notify_master(booking["master_name"],
        f"✅ *Запись подтверждена*\n\n"
        f"Клиент: {booking.get('client_name', '—')}\n"
        f"Дата: {booking['date']}\n"
        f"Время: {time_line}"
    ))
    return {"status": "ok"}

@app.post("/api/bookings/{booking_id}/cancel")
async def cancel_booking(booking_id: int):
    import db as db_module
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        booking = await cur.fetchone()
        if not booking:
            raise HTTPException(404, "Запись не найдена")
        booking = dict(booking)
        ids = await db_module.get_range_ids_for_booking(booking_id)
        marks = ",".join("?" * len(ids))
        cur = await db.execute(
            f"SELECT time FROM bookings WHERE id IN ({marks}) ORDER BY time",
            tuple(ids),
        )
        times = [r[0] for r in await cur.fetchall()]
        await db.execute(f"DELETE FROM bookings WHERE id IN ({marks})", tuple(ids))
        await db.execute(f"DELETE FROM booking_services WHERE booking_id IN ({marks})", tuple(ids))
        await db.commit()

    if len(times) <= 1:
        time_line = times[0] if times else booking["time"]
    else:
        time_line = f"{times[0]} – {db_module._add_minutes(times[-1], 15)}"

    asyncio.create_task(_notify_master(booking["master_name"],
        f"❌ *Запись отменена*\n\n"
        f"Клиент: {booking.get('client_name', '—')}\n"
        f"Дата: {booking['date']}\n"
        f"Время: {time_line}"
    ))
    # Освободившееся окно → лист ожидания (Telegram)
    try:
        matches = await db_module.notify_waitlist_for_slot(
            booking["master_name"], booking["date"], times[0] if times else booking["time"],
        )
        for m in matches:
            asyncio.create_task(_tg_send(
                m["telegram_id"],
                f"🔔 Освободилось окно!\n\n"
                f"Мастер: {booking['master_name']}\n"
                f"Дата: {booking['date']}\n"
                f"Время: {times[0] if times else booking['time']}\n\n"
                f"Записывайтесь: /start → Записаться",
            ))
    except Exception as e:
        log.warning(f"waitlist notify failed: {e}")
    return {"status": "ok"}

@app.post("/api/bookings/{booking_id}/complete")
async def complete_booking(booking_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        await db.execute("DELETE FROM booking_services WHERE booking_id = ?", (booking_id,))
        await db.commit()
        return {"status": "ok"}

# ── API: Расписание ──────────────────────────────────────

@app.get("/api/schedule/dayoff")
async def schedule_dayoff(date: str = Query(...), request: Request = None):
    """Карта выходных на дату: {master_name: true}. Только для CRM (cookie).
    Должен идти ДО /api/schedule/{master_name} — иначе FastAPI ловит 'dayoff' как имя мастера."""
    if not request or not _auth_cookie_ok(request):
        raise HTTPException(401, "Не авторизован")
    dt = datetime.strptime(date, "%Y-%m-%d")
    dow = dt.weekday()  # 0=Пн … 6=Вс (как в day_of_week CRM)
    out = {}
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT master_name FROM master_date_schedule WHERE date = ? AND is_day_off = 1",
            (date,),
        )
        for r in await cur.fetchall():
            out[r["master_name"]] = True
        cur = await db.execute(
            "SELECT master_name FROM master_schedule WHERE day_of_week = ? AND is_day_off = 1",
            (dow,),
        )
        for r in await cur.fetchall():
            out[r["master_name"]] = True
    return out


@app.get("/api/schedule/{master_name}")
async def get_schedule(master_name: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM master_schedule WHERE master_name = ? ORDER BY day_of_week", (master_name,)
        )
        return [dict(r) for r in await cur.fetchall()]


async def _authorize_schedule_write(request: Request, master_name: str, token: str | None):
    """Писать расписание: CRM-cookie (админ) или master-session только своё имя / admin-роль."""
    if _auth_cookie_ok(request):
        return
    if token:
        s = await _get_session(token)
        if s and (
            _require_role(s, ["super_admin", "director", "admin"])
            or s.get("master_name") == "АДМИН"
            or s.get("master_name") == master_name
        ):
            return
    raise HTTPException(401, "Нужен вход в ЦРМ или сессия мастера")


@app.put("/api/schedule/{master_name}")
async def update_schedule(
    master_name: str,
    items: list[ScheduleItem],
    request: Request,
    token: str = Query(None),
):
    await _authorize_schedule_write(request, master_name, token)
    async with aiosqlite.connect(config.DB_PATH) as db:
        for s in items:
            await db.execute(
                """INSERT INTO master_schedule (master_name, day_of_week, start_time, end_time, is_day_off)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(master_name, day_of_week) DO UPDATE SET
                   start_time=?, end_time=?, is_day_off=?""",
                (master_name, s.day_of_week, s.start_time, s.end_time, s.is_day_off,
                 s.start_time, s.end_time, s.is_day_off),
            )
        await db.commit()
        return {"status": "ok"}


@app.get("/api/slots")
async def get_slots(master_name: str = Query(...), date: str = Query(...), duration_minutes: int = Query(0)):
    import db as db_module
    dt = datetime.strptime(date, "%Y-%m-%d")
    dow = dt.weekday()
    occupied = await db_module.get_occupied_times(master_name, date)

    # 1. Сначала проверяем кастомное расписание на дату
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
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
                hours = [h.strip() for h in slots_str.split(",") if h.strip()]
            else:
                hours = []
            # Обрезаем по часам салона
            hours = db_module._clamp_to_salon(hours, dow)
            return [{"time": h, "available": db_module.window_is_free(h, duration_minutes, hours, occupied)}
                    for h in hours]

        # 2. Недельное расписание
        cur = await db.execute(
            "SELECT * FROM master_schedule WHERE master_name = ? AND day_of_week = ?",
            (master_name, dow),
        )
        sched = await cur.fetchone()

        if sched and sched["is_day_off"]:
            # Явный выходной недели — нет слотов
            return []

        if not sched:
            # Нет расписания — рабочий день по умолчанию (часы салона)
            all_times = db_module.get_salon_slots(dow)
            return [{"time": t, "available": db_module.window_is_free(t, duration_minutes, all_times, occupied)}
                    for t in all_times]

        # Если выбраны конкретные часы — используем их
        selected = sched["selected_hours"] if "selected_hours" in sched.keys() else ""
        if selected:
            hours = [h.strip() for h in selected.split(",") if h.strip()]
            hours = db_module._clamp_to_salon(hours, dow)
            return [{"time": h, "available": db_module.window_is_free(h, duration_minutes, hours, occupied)}
                    for h in hours]

        # Иначе — диапазон start_time..end_time с шагом 15 минут
        start_h = int(sched["start_time"].split(":")[0])
        end_h = int(sched["end_time"].split(":")[0])
        all_times = []
        for h in range(start_h, end_h):
            for m in (0, 15, 30, 45):
                all_times.append(f"{h:02d}:{m:02d}")
        all_times = db_module._clamp_to_salon(all_times, dow)
        return [{"time": t, "available": db_module.window_is_free(t, duration_minutes, all_times, occupied)}
                for t in all_times]

@app.put("/api/master/hours")
async def update_master_hours(token: str = Query(...), body: HoursUpdate = None):
    """Обновить выбранные часы мастера для дня недели."""
    s = await _get_session(token)
    if not s:
        raise HTTPException(401, "Не авторизован")
    master_name = s["master_name"]
    if not body:
        raise HTTPException(400, "Требуется body")

    hours_str = ",".join(sorted(body.hours))

    async with aiosqlite.connect(config.DB_PATH) as db:
        # Проверяем существует ли запись
        cur = await db.execute(
            "SELECT id FROM master_schedule WHERE master_name = ? AND day_of_week = ?",
            (master_name, body.day_of_week),
        )
        exists = await cur.fetchone()

        if exists:
            await db.execute(
                "UPDATE master_schedule SET selected_hours = ?, is_day_off = 0 WHERE master_name = ? AND day_of_week = ?",
                (hours_str, master_name, body.day_of_week),
            )
        else:
            await db.execute(
                "INSERT INTO master_schedule (master_name, day_of_week, start_time, end_time, is_day_off, selected_hours) VALUES (?,?,?,?,?,?)",
                (master_name, body.day_of_week, "10:00", "20:00", 0, hours_str),
            )
        await db.commit()
    return {"status": "ok", "hours": body.hours}


# ── API: Расписание на конкретные даты ─────────────────

class DateScheduleUpdate(BaseModel):
    date: str
    time_slots: list[str]
    is_day_off: bool = False

@app.get("/api/master/date-schedule")
async def get_date_schedule(token: str = Query(...), date: str = Query(...)):
    """Получить расписание мастера на конкретную дату."""
    s = await _get_session(token)
    if not s:
        raise HTTPException(401, "Не авторизован")
    master_name = s["master_name"]
    import db as db_module
    sched = await db_module.get_date_schedule(master_name, date)
    if sched:
        return sched
    # Если нет кастомного расписания — возвращаем недельное
    from datetime import datetime
    dt = datetime.strptime(date, "%Y-%m-%d")
    dow = dt.weekday()
    weekly = await db_module.get_master_schedule(master_name)
    for w in weekly:
        if w["day_of_week"] == dow:
            return {"date": date, "time_slots": w.get("selected_hours", ""), "is_day_off": w.get("is_day_off", 0), "source": "weekly"}
    return {"date": date, "time_slots": "", "is_day_off": 0, "source": "none"}

@app.put("/api/master/date-schedule")
async def update_date_schedule(token: str = Query(...), body: DateScheduleUpdate = None):
    """Установить расписание мастера на конкретную дату."""
    s = await _get_session(token)
    if not s:
        raise HTTPException(401, "Не авторизован")
    master_name = s["master_name"]
    if not body:
        raise HTTPException(400, "Требуется body")
    import db as db_module
    slots_str = ",".join(sorted(body.time_slots))
    await db_module.set_date_schedule(master_name, body.date, slots_str, 1 if body.is_day_off else 0)
    return {"status": "ok", "date": body.date, "time_slots": body.time_slots}

@app.delete("/api/master/date-schedule")
async def delete_date_schedule(token: str = Query(...), date: str = Query(...)):
    """Удалить кастомное расписание на дату (вернуться к недельному)."""
    s = await _get_session(token)
    if not s:
        raise HTTPException(401, "Не авторизован")
    master_name = s["master_name"]
    import db as db_module
    await db_module.delete_date_schedule(master_name, date)
    return {"status": "ok"}

@app.get("/api/master/date-schedules")
async def list_date_schedules(token: str = Query(...)):
    """Получить все даты с кастомным расписанием мастера."""
    s = await _get_session(token)
    if not s:
        raise HTTPException(401, "Не авторизован")
    master_name = s["master_name"]
    import db as db_module
    return await db_module.get_all_date_schedules(master_name)


# ── API: Админ управляет расписанием мастеров ──────────

class AdminDateScheduleUpdate(BaseModel):
    master_name: str
    date: str
    time_slots: list[str] = []
    is_day_off: bool = False

@app.put("/api/admin/date-schedule")
async def admin_date_schedule(
    request: Request,
    token: str = Query(None),
    body: AdminDateScheduleUpdate = None,
):
    """Админ (CRM-cookie) или master-session admin — расписание мастера на дату."""
    if not _auth_cookie_ok(request):
        s = await _get_session(token) if token else None
        if not s:
            raise HTTPException(401, "Не авторизован")
        if not (_require_role(s, ["super_admin", "director", "admin"]) or s["master_name"] == "АДМИН"):
            raise HTTPException(403, "Только админ может использовать этот эндпоинт")
    if not body:
        raise HTTPException(400, "Требуется body")
    import db as db_module
    slots_str = ",".join(sorted(body.time_slots))
    await db_module.set_date_schedule(body.master_name, body.date, slots_str, 1 if body.is_day_off else 0)
    return {"status": "ok", "master_name": body.master_name, "date": body.date}


@app.get("/api/admin/date-schedule")
async def admin_get_date_schedule(
    request: Request,
    master_name: str = Query(...),
    date: str = Query(...),
    token: str = Query(None),
):
    """Админ (CRM-cookie) — расписание мастера на дату."""
    if not _auth_cookie_ok(request):
        s = await _get_session(token) if token else None
        if not s:
            raise HTTPException(401, "Не авторизован")
        if not (_require_role(s, ["super_admin", "director", "admin"]) or s["master_name"] == "АДМИН"):
            raise HTTPException(403, "Только админ")
    import db as db_module
    sched = await db_module.get_date_schedule(master_name, date)
    if sched:
        return sched
    # Возвращаем недельное расписание
    from datetime import datetime
    dt = datetime.strptime(date, "%Y-%m-%d")
    dow = dt.weekday()
    weekly = await db_module.get_master_schedule(master_name)
    for w in weekly:
        if w["day_of_week"] == dow:
            return {"date": date, "time_slots": w.get("selected_hours", ""), "is_day_off": w.get("is_day_off", 0), "source": "weekly"}
    return {"date": date, "time_slots": "", "is_day_off": 0, "source": "none"}


# ── API: Клиенты ─────────────────────────────────────────

@app.get("/api/clients")
async def list_clients(type: str = Query(None)):
    """Вернуть клиентов. type=lead — только лиды, type=client — записавшиеся, без параметра — все."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if type:
            cur = await db.execute("SELECT * FROM clients WHERE client_type = ? ORDER BY updated_at DESC LIMIT 200", (type,))
        else:
            cur = await db.execute("SELECT * FROM clients ORDER BY updated_at DESC LIMIT 200")
        clients = [dict(r) for r in await cur.fetchall()]

        # Добавить ручных клиентов из bookings (telegram_id=0, есть имя)
        existing_names = {(c.get("name", "").lower(), c.get("phone", "")) for c in clients}
        cur = await db.execute(
            "SELECT DISTINCT client_name, phone FROM bookings WHERE (telegram_id = 0 OR telegram_id IS NULL) AND client_name IS NOT NULL AND client_name != ''"
        )
        for row in await cur.fetchall():
            row = dict(row)
            key = (row["client_name"].lower(), row.get("phone", ""))
            if key not in existing_names:
                clients.append({
                    "telegram_id": 0,
                    "name": row["client_name"],
                    "phone": row.get("phone", ""),
                    "client_type": "manual",
                    "visit_count": 0,
                })
                existing_names.add(key)

        return clients


@app.delete("/api/clients/{telegram_id}")
async def delete_client(telegram_id: int):
    """Удалить клиента по telegram_id."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM clients WHERE telegram_id = ?", (telegram_id,))
        await db.commit()
    return {"status": "ok"}


@app.post("/api/clients/delete-manual")
async def delete_manual_client(request: Request):
    """Удалить ручного клиента по имени и телефону из bookings."""
    data = await request.json()
    name = data.get("name", "")
    phone = data.get("phone", "")
    if not name:
        raise HTTPException(400, "Имя обязательно")
    async with aiosqlite.connect(config.DB_PATH) as db:
        if phone:
            await db.execute("DELETE FROM bookings WHERE client_name = ? AND phone = ? AND (telegram_id = 0 OR telegram_id IS NULL)", (name, phone))
        else:
            await db.execute("DELETE FROM bookings WHERE client_name = ? AND (phone IS NULL OR phone = '') AND (telegram_id = 0 OR telegram_id IS NULL)", (name,))
        await db.commit()
    return {"status": "ok"}

@app.get("/api/clients/leads")
async def list_leads():
    """Только лиды (нажали /start, не записались)."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM clients WHERE client_type = 'lead' ORDER BY updated_at DESC LIMIT 200")
        return [dict(r) for r in await cur.fetchall()]

@app.get("/api/clients/lost")
async def get_lost_clients(days: int = 60):
    """Клиенты, которые не записывались N дней."""
    import db as db_module
    clients = await db_module.get_lost_clients(days)
    return clients


@app.get("/api/clients/stats")
async def get_clients_stats(month: str = None):
    """Статистика по клиентам."""
    import db as db_module
    return await db_module.get_clients_stats(month)


@app.get("/api/clients/conversion")
async def get_conversion():
    """Конверсия лид→клиент."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM clients WHERE client_type='lead'")
        leads = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM clients WHERE client_type='client'")
        clients = (await cur.fetchone())[0]
        total = leads + clients
        rate = (clients / total * 100) if total > 0 else 0
        return {"leads": leads, "clients": clients, "total": total, "conversion_rate": round(rate, 1)}


@app.get("/api/analytics/slots")
async def get_popular_slots():
    """Популярные слоты — тепловая карта."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("""
            SELECT time, CAST(strftime('%w', date) AS INTEGER) as dow, COUNT(*) as cnt
            FROM bookings WHERE cancelled=0
            GROUP BY time, dow ORDER BY cnt DESC
        """)
        rows = await cur.fetchall()
        return [{"time": r[0], "day": r[1], "count": r[2]} for r in rows]


@app.get("/api/analytics/kpi")
async def analytics_kpi(from_date: str = Query(None), to_date: str = Query(None)):
    """KPI за период: загрузка, отмены, retention, выручка, load by master."""
    if not from_date:
        from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")

    import db as db_module
    from collections import Counter

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT id, master_name, date, time, duration_minutes, client_name, phone,
                      confirmed, completed, cancelled, price
               FROM bookings WHERE date >= ? AND date <= ?""",
            (from_date, to_date),
        )
        rows = [dict(r) for r in await cur.fetchall()]

        cur = await db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM transactions WHERE date(created_at) BETWEEN ? AND ?",
            (from_date, to_date),
        )
        revenue = float((await cur.fetchone())[0] or 0)

        total = len(rows)
        cancelled = sum(1 for r in rows if r.get("cancelled"))
        completed = sum(1 for r in rows if r.get("completed"))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        no_show = 0
        for r in rows:
            if r.get("cancelled") or r.get("completed") or not r.get("confirmed"):
                continue
            if f"{r.get('date','')} {r.get('time','')}" < now_str:
                no_show += 1

        active = total - cancelled
        cancel_rate = round(cancelled / total * 100, 1) if total else 0
        no_show_rate = round(no_show / active * 100, 1) if active else 0

        client_keys = [
            (r.get("phone") or r.get("client_name") or "")
            for r in rows if not r.get("cancelled") and (r.get("phone") or r.get("client_name"))
        ]
        cnt = Counter(client_keys)
        repeat = sum(1 for v in cnt.values() if v >= 2)
        retention_rate = round(repeat / len(cnt) * 100, 1) if cnt else 0

        cur = await db.execute(
            "SELECT DISTINCT master_name FROM bookings WHERE date >= ? AND date <= ?",
            (from_date, to_date),
        )
        masters = [r[0] for r in await cur.fetchall() if r[0]]
        booked_slots = sum(
            db_module.slots_needed(r.get("duration_minutes"))
            for r in rows if not r.get("cancelled")
        )
        try:
            d0 = datetime.strptime(from_date, "%Y-%m-%d")
            d1 = datetime.strptime(to_date, "%Y-%m-%d")
            n_days = max(1, (d1 - d0).days + 1)
        except ValueError:
            n_days = 30
        salon_slots_day = sum((e - s) * 4 for s, e in config.SALON_HOURS.values())
        capacity = n_days * max(1, len(masters)) * salon_slots_day
        utilization = round(booked_slots / capacity * 100, 1) if capacity else 0

        load: dict = {}
        for r in rows:
            if r.get("cancelled"):
                continue
            m = r.get("master_name") or "—"
            load[m] = load.get(m, 0) + db_module.slots_needed(r.get("duration_minutes"))
        load_by_master = sorted(
            [{"master": k, "slots": v} for k, v in load.items()],
            key=lambda x: -x["slots"],
        )

        cur = await db.execute(
            """SELECT date(created_at) as d, COALESCE(SUM(amount),0) as s
               FROM transactions WHERE date(created_at) BETWEEN ? AND ?
               GROUP BY d ORDER BY d""",
            (from_date, to_date),
        )
        revenue_by_day = [{"date": r[0], "amount": float(r[1] or 0)} for r in await cur.fetchall()]

        return {
            "from_date": from_date,
            "to_date": to_date,
            "total_bookings": total,
            "cancelled": cancelled,
            "completed": completed,
            "no_show": no_show,
            "cancel_rate": cancel_rate,
            "no_show_rate": no_show_rate,
            "unique_clients": len(cnt),
            "retention_rate": retention_rate,
            "utilization": utilization,
            "revenue": revenue,
            "load_by_master": load_by_master,
            "revenue_by_day": revenue_by_day,
        }


@app.get("/api/analytics/kpi/export")
async def analytics_kpi_export(from_date: str = Query(None), to_date: str = Query(None)):
    """CSV KPI — Excel-friendly (BOM, ';', русские подписи)."""
    import csv
    from io import StringIO
    data = await analytics_kpi(from_date=from_date, to_date=to_date)

    labels = {
        "from_date": "Период с",
        "to_date": "Период по",
        "total_bookings": "Всего записей",
        "cancelled": "Отмены",
        "completed": "Завершено",
        "no_show": "Не пришли",
        "cancel_rate": "% отмен",
        "no_show_rate": "% не пришли",
        "unique_clients": "Уникальных клиентов",
        "retention_rate": "% возвращаются (2+)",
        "utilization": "% загрузки",
        "revenue": "Выручка",
    }

    def _csv_response(header, rows, filename: str) -> Response:
        buf = StringIO()
        w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
        w.writerow(header)
        w.writerows(rows)
        # UTF-8 BOM — иначе Excel ломает кириллицу
        content = "﻿" + buf.getvalue()
        return Response(
            content,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    summary_rows = [[labels.get(k, k), data.get(k)] for k in labels]
    summary_rows.append(["", ""])
    summary_rows.append(["Мастер", "Слоты"])
    for row in data.get("load_by_master", []):
        summary_rows.append([row.get("master", ""), row.get("slots", "")])

    fname = f"kpi_{data.get('from_date', 'x')}_{data.get('to_date', 'x')}.csv"
    return _csv_response(["Показатель", "Значение"], summary_rows, fname)


@app.get("/api/analytics/forecast")
async def get_forecast():
    """Прогноз загрузки на 2 недели."""
    from datetime import datetime, timedelta
    async with aiosqlite.connect(config.DB_PATH) as db:
        today = datetime.now()
        result = []
        for i in range(14):
            d = today + timedelta(days=i)
            date_str = d.strftime("%Y-%m-%d")
            dow = d.weekday()
            # Среднее кол-во записей за этот день недели за последние 4 недели
            four_weeks_ago = (d - timedelta(days=28)).strftime("%Y-%m-%d")
            cur = await db.execute(
                "SELECT COUNT(*) FROM bookings WHERE date=? AND cancelled=0", (date_str,)
            )
            current = (await cur.fetchone())[0]
            cur = await db.execute(
                "SELECT AVG(cnt) FROM (SELECT date, COUNT(*) as cnt FROM bookings WHERE CAST(strftime('%w', date) AS INTEGER)=? AND date>=? AND cancelled=0 GROUP BY date)",
                (dow, four_weeks_ago)
            )
            avg_row = await cur.fetchone()
            avg = avg_row[0] if avg_row and avg_row[0] else 0
            load = min(100, int(current / max(avg, 1) * 100)) if avg > 0 else 0
            rus_days = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс']
            result.append({"date": date_str, "day_name": rus_days[d.weekday()], "bookings": current, "avg": round(avg, 1), "load_percent": load})
        return result


@app.get("/api/clients/birthday/today")
async def get_birthdays_today():
    """Клиенты с днём рождения сегодня."""
    import db as db_module
    return await db_module.get_birthdays_today()


@app.get("/api/clients/booked")
async def list_booked_clients():
    """Только записавшиеся клиенты."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM clients WHERE client_type = 'client' ORDER BY updated_at DESC LIMIT 200")
        return [dict(r) for r in await cur.fetchall()]

@app.get("/api/clients/{telegram_id}")
async def get_client(telegram_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM clients WHERE telegram_id = ?", (telegram_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404)
        return dict(row)

@app.get("/api/clients/search/{query}")
async def search_clients(query: str):
    """Поиск клиентов по имени или телефону."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM clients WHERE name LIKE ? OR phone LIKE ? ORDER BY updated_at DESC LIMIT 50",
            (f"%{query}%", f"%{query}%"),
        )
        return [dict(r) for r in await cur.fetchall()]

@app.get("/api/clients/{telegram_id}/history")
async def client_history(telegram_id: int):
    """История визитов клиента."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT * FROM bookings WHERE telegram_id = ?
               ORDER BY date DESC, time DESC LIMIT 50""",
            (telegram_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

@app.get("/api/clients/{telegram_id}/notes")
async def client_notes_list(telegram_id: int):
    """Заметки о клиенте."""
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM client_notes WHERE client_telegram_id = ? ORDER BY created_at DESC",
            (telegram_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

@app.post("/api/clients/{telegram_id}/notes")
async def add_client_note(telegram_id: int, request: Request):
    """Добавить заметку о клиенте."""
    body = await request.json()
    text = body.get("text", "").strip()
    author = body.get("author", "Админ")
    if not text:
        raise HTTPException(400, "Текст заметки обязателен")
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT INTO client_notes (client_telegram_id, author, text) VALUES (?,?,?)",
            (telegram_id, author, text),
        )
        await db.commit()
    return {"status": "ok"}


@app.put("/api/clients/{telegram_id}/birthday")
async def set_birthday(telegram_id: int, request: Request):
    """Установить день рождения клиента."""
    body = await request.json()
    birthday = body.get("birthday", "").strip()
    import db as db_module
    await db_module.update_client_birthday(telegram_id, birthday)
    return {"status": "ok"}


# ── API: Рассылка ────────────────────────────────────────

class BroadcastRequest(BaseModel):
    segment: str = "all"  # all, lost, active
    text: str
    client_ids: list = []  # если пусто — по сегменту

@app.post("/api/broadcast")
async def broadcast_message(req: BroadcastRequest):
    """Отправить сообщение клиентам через Telegram."""
    if not req.text.strip():
        raise HTTPException(400, "Текст сообщения обязателен")

    import db as db_module
    import httpx

    if req.client_ids:
        # Отправка конкретным клиентам по telegram_id
        async with aiosqlite.connect(config.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            ph = ",".join("?" * len(req.client_ids))
            cur = await db.execute(f"SELECT * FROM clients WHERE telegram_id IN ({ph})", req.client_ids)
            clients = [dict(r) for r in await cur.fetchall()]
    elif req.segment == "lost":
        clients = await db_module.get_lost_clients(60)
    elif req.segment == "active":
        clients = await db_module.get_clients_by_segment("regular")
    else:
        clients = await db_module.get_clients_by_segment("all")

    sent, failed = 0, 0
    async with httpx.AsyncClient() as http:
        for c in clients:
            tg_id = c.get("telegram_id")
            if not tg_id:
                continue
            try:
                resp = await http.post(
                    f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage",
                    json={"chat_id": tg_id, "text": req.text},
                    timeout=10,
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    sent += 1
                else:
                    failed += 1
                    log.warning(f"BROADCAST: failed tg_id={tg_id} status={resp.status_code} resp={resp.text[:200]}")
            except Exception as e:
                failed += 1
                log.warning(f"BROADCAST: exception tg_id={tg_id}: {e}")

    return {"sent": sent, "failed": failed, "total": len(clients)}


# ── API: Управление пользователями ───────────────────────

class UserCreate(BaseModel):
    name: str
    phone: str
    role: str = "master_edit"
    permissions: dict = {}

class UserUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    role: str | None = None
    permissions: dict | None = None

@app.get("/api/users")
async def list_users(request: Request, token: str | None = None):
    """Список пользователей (super_admin/director)."""
    s = await _get_session_or_crm(token, request)
    if not s:
        raise HTTPException(401, "Не авторизован")
    if not _require_role(s, ["super_admin", "director"]):
        raise HTTPException(403, "Нет доступа")

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM masters WHERE is_active = 1 ORDER BY name")
        masters = [dict(r) for r in await cur.fetchall()]

    result = []
    for m in masters:
        perms = await _get_permissions(m["id"])
        result.append({**m, "permissions": perms})
    return result

@app.post("/api/users")
async def create_user(req: UserCreate, request: Request, token: str | None = None):
    """Создать пользователя (super_admin)."""
    s = await _get_session_or_crm(token, request)
    if not s:
        raise HTTPException(401, "Не авторизован")
    if not _require_role(s, ["super_admin"]):
        raise HTTPException(403, "Только супер-админ может создавать пользователей")

    phone = req.phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not phone.startswith("+"):
        phone = "+" + phone

    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO masters (name, phone, role, is_active) VALUES (?,?,?,1)",
            (req.name, phone, req.role),
        )
        master_id = cur.lastrowid
        await db.commit()

        # Сохраняем permissions
        p = req.permissions
        await db.execute(
            "INSERT OR REPLACE INTO user_permissions (master_id, view_clients, edit_bookings, edit_schedule, finance, broadcast, manage_masters) VALUES (?,?,?,?,?,?,?)",
            (master_id, p.get("view_clients", "own"), p.get("edit_bookings", "own"), p.get("edit_schedule", "own"), p.get("finance", 0), p.get("broadcast", 0), p.get("manage_masters", 0)),
        )
        await db.commit()

    return {"status": "ok", "id": master_id}

@app.put("/api/users/{user_id}")
async def update_user(user_id: int, req: UserUpdate, request: Request, token: str | None = None):
    """Обновить пользователя (super_admin/director)."""
    s = await _get_session_or_crm(token, request)
    if not s:
        raise HTTPException(401, "Не авторизован")
    if not _require_role(s, ["super_admin", "director"]):
        raise HTTPException(403, "Нет доступа")

    async with aiosqlite.connect(config.DB_PATH) as db:
        updates = []
        params = []
        if req.name is not None:
            updates.append("name = ?")
            params.append(req.name)
        if req.phone is not None:
            phone = req.phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
            if not phone.startswith("+"):
                phone = "+" + phone
            updates.append("phone = ?")
            params.append(phone)
        if req.role is not None:
            if not _require_role(s, ["super_admin"]):
                raise HTTPException(403, "Только супер-админ может менять роль")
            updates.append("role = ?")
            params.append(req.role)

        if updates:
            params.append(user_id)
            await db.execute(f"UPDATE masters SET {', '.join(updates)} WHERE id = ?", params)
            await db.commit()

        if req.permissions is not None:
            p = req.permissions
            await db.execute(
                "INSERT OR REPLACE INTO user_permissions (master_id, view_clients, edit_bookings, edit_schedule, finance, broadcast, manage_masters) VALUES (?,?,?,?,?,?,?)",
                (user_id, p.get("view_clients", "own"), p.get("edit_bookings", "own"), p.get("edit_schedule", "own"), p.get("finance", 0), p.get("broadcast", 0), p.get("manage_masters", 0)),
            )
            await db.commit()

    return {"status": "ok"}

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, request: Request, token: str | None = None):
    """Деактивировать пользователя (super_admin)."""
    s = await _get_session_or_crm(token, request)
    if not s:
        raise HTTPException(401, "Не авторизован")
    if not _require_role(s, ["super_admin"]):
        raise HTTPException(403, "Только супер-админ может удалять пользователей")

    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE masters SET is_active = 0 WHERE id = ?", (user_id,))
        await db.commit()
    return {"status": "ok"}


# ── API: Статистика ──────────────────────────────────────

@app.get("/api/stats")
async def get_stats():
    async with aiosqlite.connect(config.DB_PATH) as db:
        today = datetime.now().strftime("%Y-%m-%d")
        r = {}
        for q, k in [
            ("SELECT COUNT(*) FROM bookings WHERE date = ?", "today_bookings"),
            ("SELECT COUNT(*) FROM bookings", "total_bookings"),
            ("SELECT COUNT(*) FROM clients", "total_clients"),
            ("SELECT COUNT(*) FROM masters WHERE is_active = 1", "total_masters"),
            ("SELECT COUNT(*) FROM bookings WHERE confirmed = 0", "pending_bookings"),
        ]:
            cur = await db.execute(q, (today,) if "date" in q else ())
            r[k] = (await cur.fetchone())[0]
        return r

# ── API: Финансы ─────────────────────────────────────────

@app.get("/api/finance/summary")
async def finance_summary(from_date: str = Query(None), to_date: str = Query(None)):
    """Сводка по финансам за период."""
    if not from_date:
        from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")

    import db as db_module

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Считаем из confirmed + completed bookings (кроме cancelled)
        cur = await db.execute(
            """SELECT master_name, service_name, date, price, confirmed, completed
               FROM bookings WHERE date >= ? AND date <= ? AND cancelled = 0
               AND (confirmed = 1 OR completed = 1)""",
            (from_date, to_date),
        )
        rows = await cur.fetchall()

        total_revenue = 0
        master_revenue = {}
        service_revenue = {}
        booking_count = 0
        completed_count = 0

        for row in rows:
            completed_count += 1
            # Цена: из bookings, fallback — из services
            booking_price = (row["price"] or "").strip()
            if booking_price:
                import re
                match = re.search(r'\d+', booking_price)
                price = int(match.group()) if match else 0
            else:
                price = await db_module.get_price_for_service(row["service_name"] or "")
            total_revenue += price
            master = row["master_name"] or "Неизвестно"
            master_revenue[master] = master_revenue.get(master, 0) + price
            svc = row["service_name"] or "Неизвестно"
            service_revenue[svc] = service_revenue.get(svc, 0) + price

        by_master = [{"master_name": k, "total": v, "count": 0} for k, v in sorted(master_revenue.items(), key=lambda x: -x[1])]
        by_service = [{"service_name": k, "total": v, "count": 0} for k, v in sorted(service_revenue.items(), key=lambda x: -x[1])][:10]

        avg_ticket = round(total_revenue / completed_count, 2) if completed_count > 0 else 0

        return {
            "from_date": from_date,
            "to_date": to_date,
            "total_revenue": total_revenue,
            "transaction_count": completed_count,
            "bookings_count": booking_count,
            "avg_ticket": avg_ticket,
            "by_master": by_master,
            "by_service": by_service,
            "by_payment": [],
        }

@app.post("/api/transactions")
async def create_transaction(request: Request):
    """Записать транзакцию."""
    body = await request.json()
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute(
            """INSERT INTO transactions (booking_id, master_name, service_name, amount, payment_type)
               VALUES (?,?,?,?,?)""",
            (body.get("booking_id", 0), body.get("master_name", ""),
             body.get("service_name", ""), body.get("amount", 0), body.get("payment_type", "cash")),
        )
        await db.commit()
        return {"id": cur.lastrowid}

@app.get("/api/transactions")
async def list_transactions(from_date: str = Query(None), to_date: str = Query(None), limit: int = Query(50)):
    """Список транзакций."""
    if not from_date:
        from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM transactions WHERE created_at >= ? AND created_at <= ? ORDER BY created_at DESC LIMIT ?",
            (from_date, to_date + " 23:59:59", limit),
        )
        return [dict(r) for r in await cur.fetchall()]

@app.get("/api/finance/export")
async def finance_export(from_date: str = Query(None), to_date: str = Query(None)):
    """Экспорт транзакций в CSV (Excel: BOM + ';')."""
    if not from_date:
        from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not to_date:
        to_date = datetime.now().strftime("%Y-%m-%d")

    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM transactions WHERE created_at >= ? AND created_at <= ? ORDER BY created_at",
            (from_date, to_date + " 23:59:59"),
        )
        rows = [dict(r) for r in await cur.fetchall()]

    import csv, io
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["ID", "Мастер", "Услуга", "Сумма", "Тип оплаты", "Дата"])
    pay = {"cash": "Наличные", "card": "Карта"}
    for r in rows:
        writer.writerow([
            r["id"],
            r.get("master_name") or "",
            r.get("service_name") or "",
            r.get("amount") or "",
            pay.get(r.get("payment_type") or "", r.get("payment_type") or ""),
            r.get("created_at") or "",
        ])
    content = "﻿" + output.getvalue()
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="finance_{from_date}_{to_date}.csv"'},
    )

# ── API: Настройки салона ──────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request):
    import db as db_module
    flags = await db_module.get_feature_flags()
    labels = db_module.FLAG_LABELS
    salon_name = await db_module.get_setting("salon_name", config.SALON_NAME)
    salon_logo = await db_module.get_setting("salon_logo_path", "/static/logo.png")
    contact = {
        "address": await db_module.get_setting("salon_address", config.SALON_ADDRESS),
        "phone": await db_module.get_setting("salon_phone", config.SALON_PHONE),
        "metro": await db_module.get_setting("salon_metro", config.SALON_METRO),
        "map_url": await db_module.get_setting("salon_map_url", config.SALON_MAP_URL),
        "whatsapp": await db_module.get_setting("salon_whatsapp", config.SALON_WHATSAPP),
    }
    hours = {
        "start": await db_module.get_setting("salon_hours_start", config.SALON_HOURS_START),
        "end": await db_module.get_setting("salon_hours_end", config.SALON_HOURS_END),
        "sat_start": await db_module.get_setting("salon_hours_sat_start", config.SALON_HOURS_SAT_START),
        "sat_end": await db_module.get_setting("salon_hours_sat_end", config.SALON_HOURS_SAT_END),
        "sun_start": await db_module.get_setting("salon_hours_sun_start", config.SALON_HOURS_SUN_START),
        "sun_end": await db_module.get_setting("salon_hours_sun_end", config.SALON_HOURS_SUN_END),
    }
    ctx = await _template_context(request, page="settings", flags=flags, labels=labels,
                                  salon_name=salon_name, salon_logo=salon_logo,
                                  contact=contact, hours=hours,
                                  buffer_minutes=await db_module.get_buffer_minutes())
    return templates.TemplateResponse(request, "settings.html", ctx)

@app.get("/api/settings")
async def get_settings():
    import db as db_module
    return await db_module.get_feature_flags()

@app.put("/api/settings")
async def update_settings(request: Request):
    import db as db_module
    body = await request.json()
    for key, value in body.items():
        if key in db_module.FEATURE_FLAGS:
            if key == "ORG_TYPE":
                await db_module.set_setting(key, str(value))
                import config
                setattr(config, key, str(value))
                # сразу засеять меню бота для нового режима (CRM и бот читают одну БД)
                try:
                    await db_module.get_bot_menu(org_type=str(value))
                except Exception as e:
                    log.warning(f"bot_menu seed after ORG_TYPE change: {e}")
            else:
                await db_module.set_setting(key, str(value).lower())
                # Обновляем config в runtime
                import config
                setattr(config, key, str(value).lower() == "true")
    return {"status": "ok", "flags": await db_module.get_feature_flags()}


@app.put("/api/settings/salon-name")
async def update_salon_name(request: Request):
    """Обновить название салона."""
    import db as db_module
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(400, "Название не может быть пустым")
    await db_module.set_setting("salon_name", name)
    import config as cfg
    cfg.SALON_NAME = name
    return {"status": "ok", "salon_name": name}


@app.post("/api/settings/logo")
async def upload_logo(file: UploadFile = File(...)):
    """Загрузить логотип салона (ужать до 512px, сохраняя пропорции)."""
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(400, "Допустимые форматы: JPG, PNG, WebP")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Максимальный размер: 5 МБ")
    try:
        data, ext = _resize_image(data, 512, jpeg_quality=90)
    except Exception as e:
        log.warning(f"logo resize failed: {e}")
        raise HTTPException(400, "Не удалось обработать изображение")
    logo_path = BASE_DIR / "static" / f"salon_logo.{ext}"
    # убрать старый salon_logo.* с другим расширением
    for old in BASE_DIR.glob("static/salon_logo.*"):
        if old != logo_path:
            try:
                old.unlink()
            except OSError:
                pass
    with open(logo_path, "wb") as f:
        f.write(data)
    import db as db_module
    url = f"/static/salon_logo.{ext}"
    await db_module.set_setting("salon_logo_path", url)
    return {"status": "ok", "url": url}


@app.put("/api/settings/contact")
async def update_contact(request: Request):
    """Обновить контактные данные салона."""
    import db as db_module
    import config as cfg
    body = await request.json()

    mapping = {
        "address": ("salon_address", "SALON_ADDRESS"),
        "phone": ("salon_phone", "SALON_PHONE"),
        "metro": ("salon_metro", "SALON_METRO"),
        "map_url": ("salon_map_url", "SALON_MAP_URL"),
        "whatsapp": ("salon_whatsapp", "SALON_WHATSAPP"),
    }

    for key, (db_key, cfg_key) in mapping.items():
        if key in body:
            value = body[key].strip()
            await db_module.set_setting(db_key, value)
            setattr(cfg, cfg_key, value)

    return {"status": "ok"}


@app.put("/api/settings/hours")
async def update_hours(request: Request):
    """Обновить часы работы салона."""
    import db as db_module
    import config as cfg
    body = await request.json()

    mapping = {
        "start": ("salon_hours_start", "SALON_HOURS_START"),
        "end": ("salon_hours_end", "SALON_HOURS_END"),
        "sat_start": ("salon_hours_sat_start", "SALON_HOURS_SAT_START"),
        "sat_end": ("salon_hours_sat_end", "SALON_HOURS_SAT_END"),
        "sun_start": ("salon_hours_sun_start", "SALON_HOURS_SUN_START"),
        "sun_end": ("salon_hours_sun_end", "SALON_HOURS_SUN_END"),
    }

    for key, (db_key, cfg_key) in mapping.items():
        if key in body:
            value = str(body[key]).strip()
            await db_module.set_setting(db_key, value)
            setattr(cfg, cfg_key, value)

    return {"status": "ok"}


@app.get("/api/settings/buffer")
async def get_buffer_setting():
    import db as db_module
    return {"buffer_minutes": await db_module.get_buffer_minutes()}


@app.get("/api/promo")
async def promo_list():
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM promo_codes ORDER BY code")
        return [dict(r) for r in await cur.fetchall()]


@app.post("/api/promo")
async def promo_create(request: Request):
    body = await request.json()
    code = (body.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "code required")
    percent = max(0, min(100, int(body.get("percent") or 0)))
    max_uses = max(0, int(body.get("max_uses") or 0))
    expires_at = str(body.get("expires_at") or "")
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """INSERT INTO promo_codes (code, percent, max_uses, expires_at, active)
               VALUES (?, ?, ?, ?, 1)
               ON CONFLICT(code) DO UPDATE SET percent=excluded.percent, max_uses=excluded.max_uses,
                 expires_at=excluded.expires_at, active=1, used=0""",
            (code.upper(), percent, max_uses, expires_at),
        )
        await db.commit()
    import db as db_module
    await db_module.log_audit("crm", "promo_create", "promo", code.upper(), str(percent))
    return {"status": "ok", "code": code.upper()}


@app.delete("/api/promo/{code}")
async def promo_delete(code: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("UPDATE promo_codes SET active = 0 WHERE UPPER(code) = UPPER(?)", (code,))
        await db.commit()
    import db as db_module
    await db_module.log_audit("crm", "promo_delete", "promo", code.upper(), "")
    return {"status": "ok"}


@app.get("/api/clients/tags/{client_key}")
async def client_tags_get(client_key: str):
    import db as db_module
    return {"tags": await db_module.list_tags(client_key)}


@app.put("/api/clients/tags/{client_key}")
async def client_tags_set(client_key: str, request: Request):
    body = await request.json()
    tags = body.get("tags") or []
    if not isinstance(tags, list):
        raise HTTPException(400, "tags must be list")
    import db as db_module
    await db_module.set_tags(client_key, [str(t) for t in tags])
    await db_module.log_audit("crm", "client_tags", "client", client_key, ",".join(str(t) for t in tags))
    return {"status": "ok", "tags": await db_module.list_tags(client_key)}


@app.post("/api/clients/import")
async def clients_import(request: Request):
    """CSV import: name,phone[,tag] per line, header optional."""
    body = await request.json()
    raw = body.get("csv") or ""
    import csv
    import io
    import db as db_module
    reader = csv.reader(io.StringIO(raw))
    created = 0
    for row in reader:
        if not row:
            continue
        name = (row[0] or "").strip()
        if not name or name.lower() == "name":
            continue
        phone = (row[1] or "").strip() if len(row) > 1 else ""
        tag = (row[2] or "").strip() if len(row) > 2 else ""
        # Telegram PK: use stable negative hash key for CSV-only clients
        import hashlib as _hl
        key = -int(_hl.md5(f"{name}|{phone}".encode()).hexdigest()[:7], 16)
        async with aiosqlite.connect(config.DB_PATH) as adb:
            await adb.execute(
                """INSERT INTO clients (telegram_id, contact_id, name, phone, client_type)
                   VALUES (?, 0, ?, ?, 'client')
                   ON CONFLICT(telegram_id) DO UPDATE SET name=excluded.name, phone=excluded.phone""",
                (key, name, phone),
            )
            await adb.commit()
        if tag:
            await db_module.set_tags(name, [tag])
        created += 1
    await db_module.log_audit("crm", "clients_import", "clients", str(created), f"rows={created}")
    return {"status": "ok", "imported": created}


@app.get("/api/audit")
async def audit_list(limit: int = Query(100)):
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (max(1, min(500, limit)),)
        )
        return [dict(r) for r in await cur.fetchall()]


@app.put("/api/settings/buffer")
async def update_buffer_setting(request: Request):
    """Салон-вайдный буфер после каждой записи (минуты, кратно 15, 0 = выкл)."""
    import db as db_module
    import config as cfg
    body = await request.json()
    try:
        raw = int(body.get("buffer_minutes", 0) or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "buffer_minutes must be an integer")
    if raw < 0 or raw > 240:
        raise HTTPException(400, "buffer_minutes must be 0..240")
    # округляем вверх до шага 15
    if raw > 0:
        raw = ((raw + 14) // 15) * 15
    await db_module.set_setting("buffer_minutes", str(raw))
    cfg.BUFFER_MINUTES = raw
    return {"status": "ok", "buffer_minutes": raw}


@app.get("/api/settings/works-photos")
async def list_works_photos():
    """Список фото работ."""
    photos_dir = BASE_DIR / "works_photos"
    if not photos_dir.exists():
        return []
    photos = []
    for f in sorted(photos_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
            photos.append({
                "name": f.name,
                "url": f"/works-photos/{f.name}",
                "size": f.stat().st_size,
            })
    for sub in sorted(photos_dir.iterdir()):
        if sub.is_dir():
            for f in sorted(sub.iterdir()):
                if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
                    photos.append({
                        "name": f"{sub.name}/{f.name}",
                        "url": f"/works-photos/{sub.name}/{f.name}",
                        "size": f.stat().st_size,
                    })
    return photos


@app.post("/api/settings/works-photo")
async def upload_works_photo(file: UploadFile = File(...), category: str = Form("")):
    """Загрузить фото работ (ужать до 1600px, ≤15 в категории)."""
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(400, "Допустимые форматы: JPG, PNG, WebP")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "Максимальный размер: 10 МБ")
    try:
        # галерея: ≤1280px — хватает для TG и не тормозит бота
        data, ext = _resize_image(data, 1280, jpeg_quality=80)
    except Exception as e:
        log.warning(f"works photo resize failed: {e}")
        raise HTTPException(400, "Не удалось обработать изображение")
    # Безопасное имя категории
    safe_cat = ""
    if category:
        safe_cat = "".join(c if c.isalnum() or c in "-_" else "_" for c in category).strip("_")
    photos_dir = BASE_DIR / "works_photos" / safe_cat if safe_cat else BASE_DIR / "works_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    # Лимит 15 фото в категории (и в корне — считаем корень как пустую категорию)
    existing = [f for f in photos_dir.iterdir()
                if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    if len(existing) >= 15:
        raise HTTPException(400, "Максимум 15 фото в категории")
    # только имя файла, без путей из браузера
    raw_name = Path(file.filename or "photo.jpg").name
    stem = Path(raw_name).stem or "photo"
    # убрать недопустимые символы в имени
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in stem).strip() or "photo"
    filename = f"{safe}.{ext}"
    # не затереть чужой файл с тем же stem, но другим ext — добавить суффикс при коллизии
    filepath = photos_dir / filename
    if filepath.exists():
        filename = f"{safe}_{random.randint(1000, 9999)}.{ext}"
        filepath = photos_dir / filename
    with open(filepath, "wb") as f:
        f.write(data)
    rel = f"{safe_cat}/{filename}" if safe_cat else filename
    return {"status": "ok", "url": f"/works-photos/{rel}"}


@app.delete("/api/settings/works-photo/{path:path}")
async def delete_works_photo(path: str):
    """Удалить фото работ (с защитой от path traversal)."""
    base = (BASE_DIR / "works_photos").resolve()
    filepath = (BASE_DIR / "works_photos" / path).resolve()
    if not str(filepath).startswith(str(base)) or not filepath.exists() or not filepath.is_file():
        raise HTTPException(404, "Файл не найден")
    filepath.unlink()
    return {"status": "ok"}


@app.get("/api/settings/works-categories")
async def get_works_categories_api():
    import db as db_module
    cats = await db_module.get_works_categories()
    return [{"label": c[0], "folder": c[1]} for c in cats]


@app.put("/api/settings/works-categories")
async def set_works_categories_api(request: Request):
    import db as db_module
    body = await request.json()
    items = body.get("categories") or []
    cleaned = []
    for it in items:
        label = str(it.get("label", "")).strip()
        folder = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(it.get("folder", "")).strip()).strip("_")
        if label and folder:
            cleaned.append([label, folder])
    if not cleaned:
        raise HTTPException(400, "Нужно хотя бы одна категория")
    import json as _json
    await db_module.set_setting("works_categories", _json.dumps(cleaned, ensure_ascii=False))
    return {"status": "ok", "categories": cleaned}


# ── API: Управление ботом (self-serve) ────────────────────

class _MenuIn(BaseModel):
    id: int | None = None
    label: str
    emoji: str = ""
    action_type: str = "section"
    action_value: str = ""
    sort_order: int = 0
    enabled: bool = True


@app.get("/api/bot/menu")
async def api_bot_menu():
    import db as db_module
    flags = await db_module.get_feature_flags()
    org = flags.get("ORG_TYPE", "beauty")
    items = await db_module.get_bot_menu(org)
    return {"org_type": org, "items": items}


@app.post("/api/bot/menu")
async def api_bot_menu_create(item: _MenuIn):
    import db as db_module
    if not item.label.strip():
        raise HTTPException(400, "Название кнопки не может быть пустым")
    if item.action_type == "url" and not item.action_value.startswith(("http://", "https://")):
        raise HTTPException(400, "Для URL укажите ссылку http(s)://")
    if item.action_type == "section" and not item.action_value:
        raise HTTPException(400, "Выберите раздел")
    flags = await db_module.get_feature_flags()
    org = flags.get("ORG_TYPE", "beauty")
    new_id = await db_module.upsert_bot_menu_item(
        None, org, item.label.strip(), item.emoji.strip(),
        item.action_type, item.action_value.strip(), item.sort_order, item.enabled,
    )
    return {"status": "ok", "id": new_id}


@app.put("/api/bot/menu/{item_id}")
async def api_bot_menu_update(item_id: int, item: _MenuIn):
    import db as db_module
    if not item.label.strip():
        raise HTTPException(400, "Название кнопки не может быть пустым")
    if item.action_type == "url" and not item.action_value.startswith(("http://", "https://")):
        raise HTTPException(400, "Для URL укажите ссылку http(s)://")
    flags = await db_module.get_feature_flags()
    org = flags.get("ORG_TYPE", "beauty")
    await db_module.upsert_bot_menu_item(
        item_id, org, item.label.strip(), item.emoji.strip(),
        item.action_type, item.action_value.strip(), item.sort_order, item.enabled,
    )
    return {"status": "ok"}


@app.delete("/api/bot/menu/{item_id}")
async def api_bot_menu_delete(item_id: int):
    import db as db_module
    await db_module.delete_bot_menu_item(item_id)
    return {"status": "ok"}


@app.post("/api/bot/menu/reorder")
async def api_bot_menu_reorder(request: Request):
    import db as db_module
    body = await request.json()
    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        raise HTTPException(400, "items пуст")
    await db_module.reorder_bot_menu(items)
    return {"status": "ok"}


@app.post("/api/bot/start-photo")
async def api_bot_start_photo(file: UploadFile = File(...)):
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(400, "Допустимые форматы: JPG, PNG, WebP")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(400, "Максимальный размер: 5 МБ")
    try:
        data, ext = _resize_image(data, 512, jpeg_quality=90)
    except Exception as e:
        log.warning(f"start photo resize failed: {e}")
        raise HTTPException(400, "Не удалось обработать изображение")
    path = BASE_DIR / "static" / f"bot_start_photo.{ext}"
    for old in BASE_DIR.glob("static/bot_start_photo.*"):
        if old != path:
            try:
                old.unlink()
            except OSError:
                pass
    with open(path, "wb") as f:
        f.write(data)
    url = f"/static/bot_start_photo.{ext}"
    import db as db_module
    await db_module.set_setting("bot_start_photo", str(path))
    await db_module.set_setting("bot_start_photo_url", url)
    return {"status": "ok", "url": url}


@app.delete("/api/bot/start-photo")
async def api_bot_start_photo_delete():
    import db as db_module
    for old in BASE_DIR.glob("static/bot_start_photo.*"):
        try:
            old.unlink()
        except OSError:
            pass
    await db_module.set_setting("bot_start_photo", "")
    await db_module.set_setting("bot_start_photo_url", "")
    return {"status": "ok"}


@app.get("/api/bot/welcome")
async def api_bot_welcome_get():
    import db as db_module
    text = await db_module.get_content("welcome")
    return {"text": text}


@app.put("/api/bot/welcome")
async def api_bot_welcome_put(request: Request):
    import db as db_module
    body = await request.json()
    text = str(body.get("text", ""))
    if len(text) > 4000:
        raise HTTPException(400, "Текст слишком длинный (макс. 4000)")
    await db_module.set_content("welcome", text)
    return {"status": "ok"}


@app.get("/api/bot/status")
async def api_bot_status():
    import db as db_module
    heartbeat = await db_module.get_setting("bot_heartbeat_at", "")
    photo_url = await db_module.get_setting("bot_start_photo_url", "")
    online = False
    if heartbeat:
        try:
            from datetime import datetime as _dt
            last = _dt.strptime(heartbeat, "%Y-%m-%d %H:%M:%S")
            online = (_dt.now() - last).total_seconds() < 600
        except Exception:
            online = False
    admin_ids_raw = await db_module.get_setting("admin_ids", "")
    return {
        "online": online,
        "heartbeat_at": heartbeat,
        "start_photo_url": photo_url,
        "bot_token_set": bool(config.BOT_TOKEN and config.BOT_TOKEN != "YOUR_BOT_TOKEN_HERE"),
        "admin_ids": admin_ids_raw,
    }


@app.get("/api/bot/notifications")
async def api_bot_notifications_get():
    import db as db_module
    cfg = await db_module.get_notify_config()
    labels = db_module.NOTIFY_LABELS
    return {
        "items": [
            {
                "type": t,
                "label": labels.get(t, t),
                "enabled": bool(v.get("enabled", 1)),
                "lead_hours": float(v.get("lead_hours", 0)),
                "quiet_start": int(v.get("quiet_start", 0)),
                "quiet_end": int(v.get("quiet_end", 24)),
                "template": v.get("template", ""),
            }
            for t, v in cfg.items()
        ]
    }


@app.put("/api/bot/notifications")
async def api_bot_notifications_put(request: Request):
    import db as db_module
    body = await request.json()
    items = body.get("items") or []
    if not isinstance(items, list):
        raise HTTPException(400, "items должен быть массивом")
    for it in items:
        ntype = str(it.get("type", "")).strip()
        if ntype:
            await db_module.set_notify_config(ntype, it)
    return {"status": "ok"}


@app.put("/api/bot/admin-ids")
async def api_bot_admin_ids(request: Request):
    import db as db_module
    body = await request.json()
    raw = str(body.get("admin_ids", "")).strip()
    cleaned = ",".join(
        x.strip() for x in raw.replace(";", ",").split(",")
        if x.strip().lstrip("-").isdigit()
    )
    await db_module.set_setting("admin_ids", cleaned)
    return {"status": "ok", "admin_ids": cleaned}


# ── API: Приложение мастеров (self-serve) ─────────────────

@app.get("/api/masters/app-status")
async def api_masters_app_status():
    import db as db_module
    login_on = (await db_module.get_setting("master_login_enabled", "true")).lower() != "false"
    return {"login_enabled": login_on}


@app.put("/api/masters/{master_id}/login")
async def api_master_login_toggle(master_id: int, request: Request):
    import db as db_module
    body = await request.json()
    enabled = bool(body.get("enabled", True))
    if master_id == 0:
        # 0 = global switch stored as setting
        await db_module.set_setting("master_login_enabled", "true" if enabled else "false")
        return {"status": "ok", "scope": "global", "enabled": enabled}
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("UPDATE masters SET is_active = ? WHERE id = ?", (int(enabled), master_id))
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Мастер не найден")
    return {"status": "ok", "scope": "master", "master_id": master_id, "enabled": enabled}


@app.get("/api/masters/sessions")
async def api_masters_sessions():
    await _init_sessions_table()
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT token, master_id, master_name, telegram_id, role, expires FROM master_sessions ORDER BY expires DESC"
        )
        rows = [dict(r) for r in await cur.fetchall()]
    return {"sessions": rows}


@app.delete("/api/masters/sessions/{token}")
async def api_masters_session_revoke(token: str):
    await _init_sessions_table()
    async with aiosqlite.connect(config.DB_PATH) as db:
        cur = await db.execute("DELETE FROM master_sessions WHERE token = ?", (token,))
        await db.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Сессия не найдена")
    return {"status": "ok"}


@app.post("/api/masters/sessions/revoke-all")
async def api_masters_sessions_revoke_all():
    await _init_sessions_table()
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute("DELETE FROM master_sessions")
        await db.commit()
    return {"status": "ok"}


@app.get("/api/masters/permissions/{master_id}")
async def api_master_permissions(master_id: int):
    return await _get_permissions(master_id)


@app.put("/api/masters/permissions/{master_id}")
async def api_master_permissions_put(master_id: int, request: Request):
    body = await request.json()
    allowed_keys = {"view_clients", "edit_bookings", "edit_schedule", "finance", "broadcast", "manage_masters"}
    values = []
    for key in ("view_clients", "edit_bookings", "edit_schedule"):
        values.append(str(body.get(key, "own")))
    for key in ("finance", "broadcast", "manage_masters"):
        values.append(1 if body.get(key) else 0)
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO user_permissions (master_id, view_clients, edit_bookings, edit_schedule, finance, broadcast, manage_masters)"
            " VALUES (?,?,?,?,?,?,?)",
            (master_id, *values),
        )
        await db.commit()
    return {"status": "ok"}


# ── Запуск ───────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, workers=1)
