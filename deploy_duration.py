"""deploy_duration.py — инкрементальный деплой фичи duration_minutes.

Загружает db.py, api.py, bot.py + 5 шаблонов в /opt/{kaskad,hairos}-bot,
делает бэкап, рестарт: polling (миграция) → crm, проверяет health/status.
Пароли берутся из deploy_settings.py / env, не печатаются.
"""
from __future__ import annotations

import os
import sys
import time

import paramiko

SERVER = "92.246.128.94"
USER = "root"
# пароль не хардкодим повторно — читаем из deploy_settings.py
LOCAL = os.path.dirname(os.path.abspath(__file__))

CORE_FILES = ["db.py", "api.py", "bot.py"]
TEMPLATE_FILES = [
    "services_page.html",
    "master_dashboard.html",
    "schedule.html",
    "book.html",
    "widget.html",
]
SERVICES = ["kaskad", "hairos"]


def _load_pass() -> str:
    path = os.path.join(LOCAL, "deploy_settings.py")
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("PASS"):
                # PASS = "...."
                return line.split("=", 1)[1].strip().strip("\"'")
    raise RuntimeError("PASS not found in deploy_settings.py")


def connect() -> paramiko.SSHClient:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER, username=USER, password=_load_pass(), timeout=20)
    return ssh


def run(ssh: paramiko.SSHClient, cmd: str, timeout: int = 120) -> tuple[str, str, int]:
    _, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    code = stdout.channel.recv_exit_status()
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    return out, err, code


def main() -> int:
    print("=" * 60)
    print("  DEPLOY duration_minutes →", SERVER)
    print("=" * 60)

    ssh = connect()
    print("OK: connected\n")

    stamp = time.strftime("%H%M")
    sftp = ssh.open_sftp()

    # 1. Бэкап целевых файлов
    print("[1] Backup...")
    for svc in SERVICES:
        for name in CORE_FILES:
            src = f"/opt/{svc}-bot/{name}"
            dst = f"{src}.bak-duration-{stamp}"
            run(ssh, f"cp -f {src} {dst} 2>/dev/null || true")
        for name in TEMPLATE_FILES:
            src = f"/opt/{svc}-bot/templates/{name}"
            dst = f"{src}.bak-duration-{stamp}"
            run(ssh, f"cp -f {src} {dst} 2>/dev/null || true")
        print(f"  {svc}: backups *.bak-duration-{stamp}")

    # 2. Upload
    print("\n[2] Upload files...")
    for svc in SERVICES:
        for name in CORE_FILES:
            local = os.path.join(LOCAL, name)
            sftp.put(local, f"/opt/{svc}-bot/{name}")
            print(f"  {svc}/{name}")
        for name in TEMPLATE_FILES:
            local = os.path.join(LOCAL, "templates", name)
            sftp.put(local, f"/opt/{svc}-bot/templates/{name}")
            print(f"  {svc}/templates/{name}")
    sftp.close()

    # 3. Restart polling first (db.init / ALTER), then crm
    print("\n[3] Restart polling (migration)...")
    run(ssh, "systemctl restart kaskad-polling hairos-polling")
    time.sleep(8)

    print("[4] Restart crm...")
    run(ssh, "systemctl restart kaskad-crm hairos-crm")
    time.sleep(6)

    # 5. Status
    print("\n[5] Status...")
    out, _, _ = run(ssh, "systemctl is-active kaskad-crm kaskad-polling hairos-crm hairos-polling")
    print(out)

    # 6. Health
    print("\n[6] Health...")
    for svc, port in [("kaskad", 8000), ("hairos", 8005)]:
        out, _, _ = run(
            ssh,
            f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{port}/health --connect-timeout 5",
        )
        print(f"  {svc} /health: {out}")

    # 7. journalctl errors
    print("\n[7] Recent errors (if any)...")
    out, _, _ = run(
        ssh,
        "journalctl -u kaskad-crm -u hairos-crm -u kaskad-polling -u hairos-polling "
        "--since 3min --no-pager 2>/dev/null | grep -iE 'error|traceback' | tail -20 || true",
    )
    print(out if out else "  (clean)")

    # 8. PRAGMA duration_minutes — via each service venv python
    print("\n[8] Migration check (duration_minutes)...")
    pragma_script = (
        "import sqlite3,sys;"
        "db=sys.argv[1];"
        "c=sqlite3.connect(db);"
        "s={r[1] for r in c.execute('PRAGMA table_info(services)')};"
        "b={r[1] for r in c.execute('PRAGMA table_info(bookings)')};"
        "print('services', 'duration_minutes' in s, 'bookings', 'duration_minutes' in b)"
    )
    for svc in SERVICES:
        # найти DB_PATH из .env
        out, _, _ = run(ssh, f"grep -E '^(DB_PATH|DATABASE)' /opt/{svc}-bot/.env 2>/dev/null || true")
        db_path = ""
        for line in out.splitlines():
            if "=" in line:
                db_path = line.split("=", 1)[1].strip().strip('"')
                break
        if not db_path:
            db_path = f"/opt/{svc}-bot/bot_cache.db"
        if not db_path.startswith("/"):
            db_path = f"/opt/{svc}-bot/{db_path}"
        out, err, code = run(
            ssh,
            f"/opt/{svc}-bot/venv/bin/python3 -c \"{pragma_script}\" {db_path}",
        )
        print(f"  {svc} ({db_path}): {out or err} (exit {code})")

    # 9. Smoke: /api/services duration field
    print("\n[9] Smoke /api/services...")
    for svc, port in [("kaskad", 8000), ("hairos", 8005)]:
        out, _, _ = run(
            ssh,
            f"curl -s http://localhost:{port}/api/services --connect-timeout 5 | "
            f"python3 -c \"import sys,json; d=json.load(sys.stdin); "
            f"print('n=',len(d),'has_duration=', all('duration_minutes' in x for x in d[:3]) if d else 'empty')\"",
        )
        print(f"  {svc}: {out}")

    ssh.close()
    print("\n" + "=" * 60)
    print("  DEPLOY DONE")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
