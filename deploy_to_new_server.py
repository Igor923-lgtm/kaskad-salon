"""
deploy_to_new_server.py — Развёртывание всех проектов на новом сервере.

Сервер: 45.159.172.228
"""
import paramiko
import os
import sys
import time

# ── Конфигурация ──
NEW_SERVER = "45.159.172.228"
USER = "root"
PASS = "DndhJ98X1U8LZg24"

# Локальный путь к проекту
LOCAL_PROJECT = r"C:\Users\User\mimo\kaskad-multitenant"

# Сервисы для деплоя (только с реальными .env файлами)
SERVICES = [
    {
        "id": "kaskad",
        "port": 8000,
        "env_file": "salons/kaskad/.env",
        "timezone": "Europe/Moscow",
    },
    {
        "id": "hairos",
        "port": 8005,
        "env_file": "salons/hairos/.env",
        "timezone": "Europe/Minsk",
    },
]


def connect():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(NEW_SERVER, username=USER, password=PASS, timeout=15)
    return ssh


def run(ssh, cmd, timeout=60):
    """Выполнить команду и вернуть (stdout, stderr, exit_code)."""
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    return out, err, exit_code


def upload_dir(ssh, local_dir, remote_dir):
    """Рекурсивно загрузить директорию на сервер."""
    sftp = ssh.open_sftp()
    uploaded = 0

    for root, dirs, files in os.walk(local_dir):
        # Пропускаем ненужные директории
        rel_root = os.path.relpath(root, local_dir)
        skip = any(x in rel_root for x in ['__pycache__', '.git', '.mimocode', '.vscode', 'backups', 'node_modules'])
        if skip:
            continue

        remote_path = os.path.join(remote_dir, rel_root).replace('\\', '/')
        try:
            sftp.mkdir(remote_path)
        except OSError:
            pass

        for f in files:
            if any(f.endswith(ext) for ext in ['.pyc', '.db', '.db.bak']):
                continue
            local_path = os.path.join(root, f)
            remote_file = os.path.join(remote_path, f)
            try:
                sftp.put(local_path, remote_file)
                uploaded += 1
            except Exception as e:
                print(f"  WARNING: {f}: {e}")

    sftp.close()
    return uploaded


def main():
    print("=" * 60)
    print("  ДЕПЛОЙ НА НОВЫЙ СЕРВЕР")
    print(f"  Сервер: {NEW_SERVER}")
    print("=" * 60)

    # 1. Подключение
    print("\n[1/7] Подключение к серверу...")
    try:
        ssh = connect()
        print("  OK подключено")
    except Exception as e:
        print(f"  FAIL: {e}")
        sys.exit(1)

    # 2. Установка зависимостей
    print("\n[2/7] Установка системных зависимостей...")
    cmds = [
        "apt-get update -qq",
        "apt-get install -y -qq python3 python3-pip python3-venv curl",
    ]
    for cmd in cmds:
        out, err, code = run(ssh, cmd, timeout=120)
        if code != 0:
            print(f"  WARNING: {err[:100]}")

    # Проверяем Python
    out, _, _ = run(ssh, "python3 --version")
    print(f"  Python: {out}")

    # 3. Загрузка файлов проекта
    print("\n[3/7] Загрузка файлов проекта...")
    uploaded = upload_dir(ssh, LOCAL_PROJECT, "/opt/kaskad-multitenant")
    print(f"  Загружено файлов: {uploaded}")

    # 4. Установка Python зависимостей
    print("\n[4/7] Установка Python зависимостей...")
    out, err, code = run(ssh, "cd /opt/kaskad-multitenant && pip3 install -r requirements.txt", timeout=180)
    if code == 0:
        print("  OK зависимости установлены")
    else:
        print(f"  WARNING: {err[:200]}")

    # 5. Настройка сервисов
    print("\n[5/7] Настройка сервисов...")
    for svc in SERVICES:
        svc_id = svc["id"]
        port = svc["port"]
        env_file = svc["env_file"]
        tz = svc["timezone"]

        print(f"\n  --- {svc_id} (порт {port}) ---")

        # Создаём директорию данных
        run(ssh, f"mkdir -p /opt/{svc_id}-bot/data")

        # Копируем .env
        sftp = ssh.open_sftp()
        local_env = os.path.join(LOCAL_PROJECT, env_file)
        if os.path.exists(local_env):
            sftp.put(local_env, f"/opt/{svc_id}-bot/.env")
            print(f"  .env скопирован")
        else:
            print(f"  WARNING: .env не найден: {local_env}")
        sftp.close()

        # Копируем код
        code_files = ["bot.py", "db.py", "config.py", "api.py", "price_data.py", "requirements.txt"]
        for f in code_files:
            local_path = os.path.join(LOCAL_PROJECT, f)
            if os.path.exists(local_path):
                sftp = ssh.open_sftp()
                sftp.put(local_path, f"/opt/{svc_id}-bot/{f}")
                sftp.close()

        # Копируем шаблоны и статику
        for d in ["templates", "static"]:
            local_path = os.path.join(LOCAL_PROJECT, d)
            if os.path.exists(local_path):
                run(ssh, f"rm -rf /opt/{svc_id}-bot/{d}")
                upload_dir(ssh, local_path, f"/opt/{svc_id}-bot/{d}")

        # Копируем price.json
        local_price = os.path.join(LOCAL_PROJECT, "price.json")
        if os.path.exists(local_price):
            sftp = ssh.open_sftp()
            sftp.put(local_price, f"/opt/{svc_id}-bot/price.json")
            sftp.close()

        # Создаём venv и устанавливаем зависимости
        run(ssh, f"cd /opt/{svc_id}-bot && python3 -m venv venv")
        out, err, code = run(ssh, f"cd /opt/{svc_id}-bot && source venv/bin/activate && pip install -r requirements.txt", timeout=180)
        if code == 0:
            print(f"  OK venv создан")
        else:
            print(f"  WARNING: {err[:100]}")

        # Создаём systemd сервис CRM
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
        sftp = ssh.open_sftp()
        f = sftp.open(f"/etc/systemd/system/{svc_id}-crm.service", 'w')
        f.write(crm_service.encode('utf-8'))
        f.close()

        # Создаём systemd сервис Bot
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
        f = sftp.open(f"/etc/systemd/system/{svc_id}-polling.service", 'w')
        f.write(bot_service.encode('utf-8'))
        f.close()

        print(f"  OK systemd сервисы созданы")

    # 6. Запуск сервисов
    print("\n[6/7] Запуск сервисов...")
    run(ssh, "systemctl daemon-reload")

    for svc in SERVICES:
        svc_id = svc["id"]
        run(ssh, f"systemctl enable {svc_id}-crm {svc_id}-polling")
        run(ssh, f"systemctl start {svc_id}-crm {svc_id}-polling")
        print(f"  {svc_id}: запущен")

    # 7. Проверка
    print("\n[7/7] Проверка...")
    time.sleep(5)

    for svc in SERVICES:
        svc_id = svc["id"]
        port = svc["port"]

        # Проверяем статус
        out, _, _ = run(ssh, f"systemctl is-active {svc_id}-crm {svc_id}-polling")
        statuses = out.strip().split('\n')

        # Проверяем health
        out, _, _ = run(ssh, f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{port}/health --connect-timeout 5")
        health = out if out else "N/A"

        crm_ok = "active" in statuses[0] if len(statuses) > 0 else False
        bot_ok = "active" in statuses[1] if len(statuses) > 1 else False

        icon_crm = "OK" if crm_ok else "FAIL"
        icon_bot = "OK" if bot_ok else "FAIL"

        print(f"\n  {svc_id}:")
        print(f"    CRM:   {icon_crm} (HTTP {health})")
        print(f"    Bot:   {icon_bot}")

    ssh.close()

    print("\n" + "=" * 60)
    print("  ДЕПЛОЙ ЗАВЕРШЁН!")
    print("=" * 60)
    print("\n  Сервисы:")
    for svc in SERVICES:
        print(f"    {svc['id']}: http://{NEW_SERVER}:{svc['port']}/login")
    print()


if __name__ == "__main__":
    main()
