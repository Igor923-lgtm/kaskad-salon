"""deploy_fix.py — Исправленный деплой на Oracle Linux сервер."""
import paramiko
import os
import sys
import time

NEW_SERVER = "45.159.172.228"
USER = "root"
PASS = "DndhJ98X1U8LZg24"
LOCAL_PROJECT = r"C:\Users\User\mimo\kaskad-multitenant"

SERVICES = [
    {"id": "kaskad", "port": 8000, "env_file": "salons/kaskad/.env", "tz": "Europe/Moscow"},
    {"id": "hairos", "port": 8005, "env_file": "salons/hairos/.env", "tz": "Europe/Minsk"},
]


def connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(NEW_SERVER, username=USER, password=PASS, timeout=15)
    return ssh


def run(ssh, cmd, timeout=120):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    return out, err, exit_code


def upload_file(sftp, local_path, remote_path):
    """Загрузить один файл, создав директории если нужно."""
    remote_dir = os.path.dirname(remote_path).replace('\\', '/')
    # Создаём директории рекурсивно
    parts = remote_dir.split('/')
    current = ''
    for part in parts:
        if not part:
            current = '/'
            continue
        current = current + '/' + part if current else part
        try:
            sftp.mkdir(current)
        except OSError:
            pass
    sftp.put(local_path, remote_path)


def main():
    print("=" * 60)
    print("  ИСПРАВЛЕННЫЙ ДЕПЛОЙ")
    print("=" * 60)

    ssh = connect()
    print("OK подключено\n")

    # 1. Установка Python и pip
    print("[1] Установка зависимостей...")
    # Проверяем что установлено
    out, _, _ = run(ssh, "python3 --version; pip3 --version 2>/dev/null || echo 'pip not found'")
    print(f"  Текущее: {out}")

    # Устанавливаем pip если нужно
    run(ssh, "yum install -y python3-pip python3-devel 2>/dev/null || dnf install -y python3-pip python3-devel 2>/dev/null", timeout=180)
    print("  OK")

    # 2. Загрузка кода проекта (только нужные файлы)
    print("\n[2] Загрузка кода...")

    # Основные файлы
    core_files = [
        "bot.py", "db.py", "config.py", "api.py", "price_data.py",
        "requirements.txt", "price.json"
    ]

    sftp = ssh.open_sftp()

    for svc in SERVICES:
        svc_id = svc["id"]
        remote_base = f"/opt/{svc_id}-bot"

        # Создаём директории
        run(ssh, f"mkdir -p {remote_base}/data {remote_base}/templates {remote_base}/static {remote_base}/works_photos")

        # Загружаем основные файлы
        for f in core_files:
            local = os.path.join(LOCAL_PROJECT, f)
            if os.path.exists(local):
                upload_file(sftp, local, f"{remote_base}/{f}")
                print(f"  {svc_id}/{f}")
            else:
                print(f"  SKIP {f}")

        # Загружаем .env
        local_env = os.path.join(LOCAL_PROJECT, svc["env_file"])
        if os.path.exists(local_env):
            upload_file(sftp, local_env, f"{remote_base}/.env")
            print(f"  {svc_id}/.env")

        # Загружаем шаблоны
        templates_dir = os.path.join(LOCAL_PROJECT, "templates")
        if os.path.isdir(templates_dir):
            for f in os.listdir(templates_dir):
                local = os.path.join(templates_dir, f)
                if os.path.isfile(local) and f.endswith('.html'):
                    upload_file(sftp, local, f"{remote_base}/templates/{f}")

        # Загружаем статику
        static_dir = os.path.join(LOCAL_PROJECT, "static")
        if os.path.isdir(static_dir):
            for f in os.listdir(static_dir):
                local = os.path.join(static_dir, f)
                if os.path.isfile(local):
                    upload_file(sftp, local, f"{remote_base}/static/{f}")

        # Загружаем логотип
        local_logo = os.path.join(LOCAL_PROJECT, "logo.png")
        if os.path.exists(local_logo):
            upload_file(sftp, local_logo, f"{remote_base}/logo.png")

        print(f"  {svc_id}: файлы загружены")

    sftp.close()

    # 3. Установка Python зависимостей
    print("\n[3] Установка Python пакетов...")
    for svc in SERVICES:
        svc_id = svc["id"]
        out, err, code = run(ssh, f"cd /opt/{svc_id}-bot && python3 -m venv venv && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt", timeout=300)
        if code == 0:
            print(f"  {svc_id}: OK")
        else:
            print(f"  {svc_id}: WARN - {err[:100]}")

    # 4. Создание systemd сервисов
    print("\n[4] Создание systemd сервисов...")
    for svc in SERVICES:
        svc_id = svc["id"]
        port = svc["port"]
        tz = svc["tz"]

        crm_service = f"""[Unit]
Description={svc_id} CRM
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/{svc_id}-bot
Environment=SALON_ID={svc_id}
ExecStart=/opt/{svc_id}-bot/venv/bin/python3 -m uvicorn api:app --host 0.0.0.0 --port {port}
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=TZ={tz}

[Install]
WantedBy=multi-user.target
"""

        bot_service = f"""[Unit]
Description={svc_id} Bot Polling
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/{svc_id}-bot
Environment=SALON_ID={svc_id}
ExecStart=/opt/{svc_id}-bot/venv/bin/python3 bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
Environment=TZ={tz}

[Install]
WantedBy=multi-user.target
"""

        sftp = ssh.open_sftp()
        f = sftp.open(f"/etc/systemd/system/{svc_id}-crm.service", 'w')
        f.write(crm_service.encode('utf-8'))
        f.close()
        f = sftp.open(f"/etc/systemd/system/{svc_id}-polling.service", 'w')
        f.write(bot_service.encode('utf-8'))
        f.close()
        sftp.close()

        print(f"  {svc_id}: сервисы созданы")

    # 5. Запуск
    print("\n[5] Запуск сервисов...")
    run(ssh, "systemctl daemon-reload")
    for svc in SERVICES:
        svc_id = svc["id"]
        run(ssh, f"systemctl enable {svc_id}-crm {svc_id}-polling")
        run(ssh, f"systemctl start {svc_id}-crm {svc_id}-polling")
        print(f"  {svc_id}: запущен")

    # 6. Проверка
    print("\n[6] Проверка (ждём 10 сек)...")
    time.sleep(10)

    for svc in SERVICES:
        svc_id = svc["id"]
        port = svc["port"]

        out, _, _ = run(ssh, f"systemctl is-active {svc_id}-crm {svc_id}-polling")
        statuses = out.strip().split('\n')

        out, _, _ = run(ssh, f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{port}/health --connect-timeout 5")
        health = out if out else "N/A"

        # Логи ошибок
        out, _, _ = run(ssh, f"journalctl -u {svc_id}-crm --since 1min --no-pager 2>&1 | tail -3")

        crm_ok = "active" in (statuses[0] if len(statuses) > 0 else "")
        bot_ok = "active" in (statuses[1] if len(statuses) > 1 else "")

        print(f"\n  {svc_id}:")
        print(f"    CRM: {'OK' if crm_ok else 'FAIL'} (HTTP {health})")
        print(f"    Bot: {'OK' if bot_ok else 'FAIL'}")
        if not crm_ok or not bot_ok:
            # Показываем последние ошибки
            out_err, _, _ = run(ssh, f"journalctl -u {svc_id}-crm --since 2min --no-pager 2>&1 | grep -i -E 'error|traceback|import' | tail -3")
            if out_err:
                print(f"    Ошибки: {out_err[:200]}")

    ssh.close()
    print("\n" + "=" * 60)
    print("  ГОТОВО")
    print("=" * 60)


if __name__ == "__main__":
    main()
