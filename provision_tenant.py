"""provision_tenant.py — Неинтерактивное разворачивание нового тенанта (ЦРМ+бот) на сервере.

Использование:
    python provision_tenant.py --id zima --name "Салон Зима" --type beauty \
        --bot-token 123456:ABC-DEF [--address "Город, улица, 1"] [--phone "+375 ..."]
    python provision_tenant.py --id zima --dry-run          # показать план без подключения
    python provision_tenant.py --cleanup --id zima --yes    # убрать тенанта с сервера

Топология — как у deploy_salon.py, но без интерактива:
каталог /opt/{id}-bot, .env в salons/{id}/, venv, юниты {id}-polling (первым) + {id}-crm,
порт 8000–8100 (первый свободный), одноразовая setup-ссылка вместо пароля в чате.
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time

DEFAULT_HOST = None  # берётся из deploy_settings.py, если --host не указан
DEFAULT_IDENTITY = os.path.expanduser("~/.ssh/id_ed25519_kaskad")
PORT_RANGE = range(8000, 8101)
ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
# Корневые .py, без которых приложение не работает (whitelist: остальные
# вспомогательные скрипты репо тенанту не нужны)
RUNTIME_FILES = ("api.py", "bot.py", "db.py", "config.py", "price_data.py", "logfmt.py")


# ── Чистые функции (используются в тестах) ──────────────────────────────────

def parse_setting_file(text: str, name: str) -> str:
    """Text-parse KEY = "value" из deploy_settings.py / deploy_secrets.py. Никогда не импортировать."""
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            continue
        key, val = s.split("=", 1)
        if key.strip() == name:
            return val.strip().strip('"').strip("'")
    return ""


def pick_port(used: set) -> int:
    for p in PORT_RANGE:
        if p not in used:
            return p
    raise RuntimeError(f"Нет свободного порта в {PORT_RANGE[0]}-{PORT_RANGE[-1]}")


def make_setup_token(salon_id: str, crm_secret: str, exp: int) -> str:
    """Должен совпадать с api._make_setup_token: {exp}.{HMAC(setup:{salon_id}:{exp})[:32]}."""
    msg = f"setup:{salon_id}:{exp}".encode()
    sig = hmac.new(crm_secret.encode(), msg, hashlib.sha256).hexdigest()[:32]
    return f"{exp}.{sig}"


def make_env(args, crm_secret: str, crm_pass: str, crm_token: str) -> str:
    return f"""# === Салон ===
SALON_ID={args.id}

# === Telegram ===
BOT_TOKEN={args.bot_token}
ADMIN_IDS={args.admin_tg_id}

# === База данных ===
DB_PATH=bot_cache.db

# === CRM ===
CRM_PASSWORD={crm_pass}
CRM_SECRET={crm_secret}
CRM_TOKEN_FIXED={crm_token}
CRM_API_URL=

# === Прокси ===
SOCKS5_PROXY=

# === Режим ===
ORG_TYPE={args.type}

# === Салон: информация ===
SALON_NAME={args.name}
SALON_ADDRESS={args.address}
SALON_PHONE={args.phone}
SALON_PHONE_SECONDARY={args.phone}
SALON_METRO=
SALON_MAP_URL=
SALON_WHATSAPP={args.phone}

# === Салон: часы работы ===
SALON_HOURS_START=10
SALON_HOURS_END=22
SALON_HOURS_SAT_START=10
SALON_HOURS_SAT_END=22
SALON_HOURS_SUN_START=10
SALON_HOURS_SUN_END=22

# === Часовой пояс ===
SALON_TIMEZONE={args.tz}

# === Функции салона ===
DISCOUNTS_ENABLED=true
BIRTHDAY_DISCOUNT=true
REVIEW_DISCOUNT=true
GALLERY_ENABLED=true
MASTERS_ENABLED=true
RATING_ENABLED=true
MY_BOOKINGS_ENABLED=true
HISTORY_ENABLED=true
BIRTHDAY_ENABLED=true
CONTACT_ENABLED=true
WIDGET_ENABLED=true
"""


def crm_service(bot_dir: str, salon_id: str, name: str, port: int, tz: str) -> str:
    return f"""[Unit]
Description={name} CRM
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={bot_dir}
Environment=SALON_ID={salon_id}
ExecStart={bot_dir}/venv/bin/python3 -m uvicorn api:app --host 0.0.0.0 --port {port}
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=TZ={tz}

[Install]
WantedBy=multi-user.target
"""


def polling_service(bot_dir: str, salon_id: str, name: str, tz: str) -> str:
    return f"""[Unit]
Description={name} Bot Polling
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory={bot_dir}
Environment=SALON_ID={salon_id}
ExecStart={bot_dir}/venv/bin/python3 bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=TZ={tz}

[Install]
WantedBy=multi-user.target
"""


def plan_lines(args) -> list:
    """Команды-план для --dry-run (без SSH)."""
    bot_dir = f"/opt/{args.id}-bot"
    return [
        f"[preflight] проверить: /opt/{args.id}-bot отсутствует, юниты {args.id}-crm/-polling не существуют",
        f"[port] первый свободный 8000-8100 (ss -ltn ∪ /opt/tenants.json)",
        f"[dirs] mkdir -p {bot_dir} {{templates,static,salons/{args.id},works_photos}}",
        f"[upload] локальный репо → {bot_dir}: {', '.join(RUNTIME_FILES)}, "
        "requirements.txt, templates/*.html, static/**",
        "[env] сгенерировать CRM_SECRET / CRM_PASSWORD / CRM_TOKEN_FIXED → "
        f"{bot_dir}/salons/{args.id}/.env (ORG_TYPE={args.type})",
        f"[venv] python3 -m venv {bot_dir}/venv && pip install -r requirements.txt",
        f"[db] SALON_ID={args.id} {bot_dir}/venv/bin/python -c 'import db, asyncio; asyncio.run(db.init())'",
        f"[systemd] записать {args.id}-polling.service (первым) + {args.id}-crm.service, daemon-reload, enable+start",
        "[health] curl -fsS localhost:PORT/health → retry до 200",
        "[registry] обновить /opt/tenants.json",
        "[setup] одноразовая ссылка /setup?token={{exp}}.{HMAC} (TTL --ttl-days) → в stdout",
    ]


# ── SSH ─────────────────────────────────────────────────────────────────────

def load_deploy_settings_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "deploy_settings.py")


def connect_ssh(host: str, user: str, identity: str, timeout: int = 20):
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    if host is None:
        with open(load_deploy_settings_path(), encoding="utf-8") as f:
            host = parse_setting_file(f.read(), "SERVER")
    if not host:
        raise RuntimeError("Не задан --host и не найден SERVER в deploy_settings.py")
    if identity and os.path.exists(identity):
        ssh.connect(host, username=user, key_filename=identity, timeout=timeout, allow_agent=True)
    else:
        with open(load_deploy_settings_path(), encoding="utf-8") as f:
            pw = parse_setting_file(f.read(), "PASS")
        if not pw:
            raise RuntimeError(f"Нет ключа {identity} и нет PASS в deploy_settings.py")
        ssh.connect(host, username=user, password=pw, timeout=timeout)
    return ssh, host


def run(ssh, cmd: str, check: bool = True) -> str:
    _, stdout, stderr = ssh.exec_command(cmd, timeout=600)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    if check and code != 0:
        raise RuntimeError(f"Команда {code}: {cmd}\n{err or out}")
    return out


def write_file(ssh, path: str, content: str):
    sftp = ssh.open_sftp()
    try:
        f = sftp.open(path, "w")
        f.write(content.encode("utf-8"))
        f.close()
    finally:
        sftp.close()


def read_file(ssh, path: str) -> str:
    return run(ssh, f"cat {path}", check=False)


def upload_code(ssh, bot_dir: str):
    """Загрузить код из локального репо (новый тенант получает текущий api.py, включая /setup)."""
    root = os.path.dirname(os.path.abspath(__file__))
    sftp = ssh.open_sftp()
    try:
        for name in RUNTIME_FILES:
            sftp.put(os.path.join(root, name), f"{bot_dir}/{name}")
        sftp.put(os.path.join(root, "requirements.txt"), f"{bot_dir}/requirements.txt")
        for sub, ext in (("templates", ".html"), ("static", None)):
            src_dir = os.path.join(root, sub)
            if not os.path.isdir(src_dir):
                continue
            for dirpath, _dirs, filenames in os.walk(src_dir):
                rel = os.path.relpath(dirpath, src_dir)
                remote_dir = f"{bot_dir}/{sub}" if rel == "." else f"{bot_dir}/{sub}/{rel}"
                run(ssh, f"mkdir -p {remote_dir}")
                for fn in sorted(filenames):
                    if ext and not fn.endswith(ext):
                        continue
                    sftp.put(os.path.join(dirpath, fn), f"{remote_dir}/{fn}")
    finally:
        sftp.close()


# ── Основной сценарий ───────────────────────────────────────────────────────

def provision(args) -> int:
    bot_dir = f"/opt/{args.id}-bot"
    if args.dry_run:
        print(f"=== DRY-RUN: {args.id} ({args.name}, {args.type}) ===")
        for line in plan_lines(args):
            print(" ", line)
        exp = int(time.time()) + args.ttl_days * 86400
        print(f"\n  setup-ссылка будет вида: http://<host>:<port>/setup?token={exp}.<hmac32>")
        print("  (SSH-подключение не выполняется)")
        return 0

    print(f"[1/9] SSH {args.host or '(из deploy_settings)'} ...")
    ssh, host = connect_ssh(args.host, args.user, args.identity)

    print("[2/9] Preflight: каталог и юниты не должны существовать...")
    if run(ssh, f"test -e {bot_dir} && echo EXISTS || echo FREE", check=False).strip() == "EXISTS":
        raise RuntimeError(f"{bot_dir} уже существует — используй --cleanup")
    for unit in (f"{args.id}-crm.service", f"{args.id}-polling.service"):
        if run(ssh, f"test -e /etc/systemd/system/{unit} && echo EXISTS || echo FREE",
               check=False).strip() == "EXISTS":
            raise RuntimeError(f"Юнит {unit} уже существует — используй --cleanup")

    print("[3/9] Выбор порта...")
    ss_out = run(ssh, "ss -ltn")
    used = set()
    for line in ss_out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "LISTEN":
            addr = parts[3]
            if ":" in addr:
                try:
                    used.add(int(addr.rsplit(":", 1)[1]))
                except ValueError:
                    pass
    raw_registry = read_file(ssh, "/opt/tenants.json")
    registry = {}
    if raw_registry.strip():
        try:
            registry = json.loads(raw_registry)
        except json.JSONDecodeError:
            registry = {}
    for meta in registry.values():
        if isinstance(meta, dict) and isinstance(meta.get("port"), int):
            used.add(meta["port"])
    port = args.port if isinstance(args.port, int) else pick_port(used)
    if port in used:
        raise RuntimeError(f"Порт {port} занят")
    print(f"    порт: {port}")

    print("[4/9] Каталоги и загрузка кода из локального репо...")
    for d in (bot_dir, f"{bot_dir}/templates", f"{bot_dir}/static",
              f"{bot_dir}/salons/{args.id}", f"{bot_dir}/works_photos"):
        run(ssh, f"mkdir -p {d}")
    upload_code(ssh, bot_dir)

    print("[5/9] .env со сгенерированными секретами...")
    crm_secret = secrets.token_hex(32)
    crm_pw = secrets.token_urlsafe(18)
    env_content = make_env(
        args,
        crm_secret=crm_secret,
        crm_pass=crm_pw,
        crm_token=secrets.token_hex(16),
    )
    write_file(ssh, f"{bot_dir}/salons/{args.id}/.env", env_content)

    print("[6/9] venv + зависимости (может занять минуты)...")
    run(ssh, f"cd {bot_dir} && python3 -m venv venv && "
             f"./venv/bin/pip install -q -r requirements.txt")

    print("[7/9] Инициализация БД (схема + прайс + меню)...")
    run(ssh, f"cd {bot_dir} && SALON_ID={args.id} ./venv/bin/python -c "
             f'"import asyncio, db; asyncio.run(db.init())"')

    print("[8/9] systemd: polling первым, затем crm...")
    write_file(ssh, f"/etc/systemd/system/{args.id}-polling.service",
               polling_service(bot_dir, args.id, args.name, args.tz))
    write_file(ssh, f"/etc/systemd/system/{args.id}-crm.service",
               crm_service(bot_dir, args.id, args.name, port, args.tz))
    run(ssh, "systemctl daemon-reload")
    run(ssh, f"systemctl enable {args.id}-polling {args.id}-crm")
    run(ssh, f"systemctl restart {args.id}-polling {args.id}-crm")

    print("[9/9] Health-check и реестр...")
    healthy = False
    for _ in range(15):
        code = run(ssh, f"curl -s -o /dev/null -w %{{http_code}} "
                        f"http://localhost:{port}/health --connect-timeout 2", check=False).strip()
        if code == "200":
            healthy = True
            break
        time.sleep(2)
    if not healthy:
        raise RuntimeError(f"/health не ответил 200 на порту {port} "
                           f"(journalctl -u {args.id}-crm -n 50)")

    registry = {}
    raw = read_file(ssh, "/opt/tenants.json")
    if raw.strip():
        try:
            registry = json.loads(raw)
        except json.JSONDecodeError:
            registry = {}
    created = time.strftime("%Y-%m-%dT%H:%M:%S")
    registry[args.id] = {"port": port, "name": args.name, "type": args.type, "created": created}
    write_file(ssh, "/opt/tenants.json", json.dumps(registry, ensure_ascii=False, indent=2))

    polling_ok = "active" in run(ssh, f"systemctl is-active {args.id}-polling", check=False)
    exp = int(time.time()) + args.ttl_days * 86400
    setup_link = f"http://{host}:{port}/setup?token={make_setup_token(args.id, crm_secret, exp)}"

    print("\n" + "=" * 60)
    print(f"  ГОТОВО: {args.name} ({args.id})")
    print(f"  ЦРМ:      http://{host}:{port}/login")
    print(f"  Setup:    {setup_link}")
    print(f"  Срок:     {args.ttl_days} дн. (до {time.strftime('%Y-%m-%d %H:%M', time.localtime(exp))})")
    print(f"  Бот:      {'active' if polling_ok else 'ОШИБКА — journalctl -u ' + args.id + '-polling'}")
    print("=" * 60)
    ssh.close()
    return 0


def cleanup(args) -> int:
    if not args.yes:
        print("Cleanup удаляет юниты и убирает каталог тенанта. Подтвердите флагом --yes.")
        return 2
    print(f"[1/4] SSH {args.host or '(из deploy_settings)'} ...")
    ssh, host = connect_ssh(args.host, args.user, args.identity)
    bot_dir = f"/opt/{args.id}-bot"

    print("[2/4] Останавливаю юниты...")
    run(ssh, f"systemctl disable --now {args.id}-crm {args.id}-polling", check=False)
    run(ssh, f"rm -f /etc/systemd/system/{args.id}-crm.service "
             f"/etc/systemd/system/{args.id}-polling.service")
    run(ssh, "systemctl daemon-reload")

    print("[3/4] Убираю каталог...")
    if run(ssh, f"test -e {bot_dir} && echo EXISTS || echo FREE", check=False).strip() == "EXISTS":
        if args.purge:
            run(ssh, f"rm -rf {bot_dir}")
            print(f"    {bot_dir} удалён")
        else:
            trash = f"/opt/.removed/{args.id}-{time.strftime('%Y%m%d%H%M%S')}"
            run(ssh, f"mkdir -p /opt/.removed && mv {bot_dir} {trash}")
            print(f"    {bot_dir} → {trash} (recover: mv обратно)")

    print("[4/4] Реестр tenants.json...")
    raw = read_file(ssh, "/opt/tenants.json")
    if raw.strip():
        try:
            registry = json.loads(raw)
            registry.pop(args.id, None)
            write_file(ssh, "/opt/tenants.json",
                       json.dumps(registry, ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            print("    tenants.json повреждён — пропускаю")
    print("ГОТОВО")
    ssh.close()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Provision CRM tenant")
    p.add_argument("--id", help="латиницей: zima, salon_5 ...")
    p.add_argument("--name", help="Название салона")
    p.add_argument("--type", choices=("beauty", "coworking"), default="beauty")
    p.add_argument("--bot-token", default="", help="Токен от @BotFather")
    p.add_argument("--address", default="")
    p.add_argument("--phone", default="")
    p.add_argument("--admin-tg-id", default="")
    p.add_argument("--tz", default="Europe/Moscow")
    p.add_argument("--port", default="auto", help="auto (по умолчанию) или число 8000-8100")
    p.add_argument("--host", default=None)
    p.add_argument("--user", default="root")
    p.add_argument("--identity", default=DEFAULT_IDENTITY)
    p.add_argument("--ttl-days", type=int, default=7)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--cleanup", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--purge", action="store_true", help="cleanup: удалить каталог, а не переместить")
    args = p.parse_args(argv)

    if args.cleanup:
        if not args.id:
            p.error("--cleanup требует --id")
        return cleanup(args)

    missing = [a for a, v in (("--id", args.id), ("--name", args.name),
                              ("--bot-token", args.bot_token)) if not v]
    if missing:
        p.error("не заданы: " + ", ".join(missing))
    if not ID_RE.match(args.id):
        p.error("--id: латиница, начинается с буквы, 2-31 символ [a-z0-9_]")
    if "\n" in args.name or "\n" in args.address:
        p.error("name/address не должны содержать переносы строк")
    if args.port != "auto":
        try:
            args.port = int(args.port)
        except ValueError:
            p.error("--port: 'auto' или число")
        if args.port not in PORT_RANGE:
            p.error(f"--port должен быть в {PORT_RANGE[0]}-{PORT_RANGE[-1]}")

    return provision(args)


if __name__ == "__main__":
    sys.exit(main())
