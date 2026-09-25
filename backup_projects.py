"""
backup_projects.py — Полный бекап проектов КАСКАД и ХАЙРОС с сервера.

Что делает:
1. Подключается к серверу по SSH
2. Создаёт tar.gz архивы обоих проектов (код + базы данных, без venv/__pycache__)
3. Скачивает архивы локально в папку backups/
4. Проверяет целостность архивов и наличие баз данных внутри

Использование:
    python backup_projects.py
"""

import paramiko
import os
import sys
import tarfile
from datetime import datetime

# ── Конфигурация сервера (запрашивается при запуске) ──
SERVER_HOST = None
SERVER_USER = None
SERVER_PASS = None

# ── Проекты для бекапа ──
PROJECTS = {
    "kaskad": "/opt/kaskad-bot",   # КАСКАД
    "hairos": "/opt/hairos-bot",   # ХАЙРОС
}

BACKUP_DIR_LOCAL = "backups"
TS = datetime.now().strftime("%Y-%m-%d_%H%M")


def connect_ssh():
    """Подключиться к серверу."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_HOST, username=SERVER_USER, password=SERVER_PASS, timeout=15)
    return ssh


def run_cmd(ssh, cmd):
    """Выполнить команду на сервере."""
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=300)
    exit_code = stdout.channel.recv_exit_status()
    return stdout.read().decode(), stderr.read().decode(), exit_code


def main():
    global SERVER_HOST, SERVER_USER, SERVER_PASS

    os.makedirs(BACKUP_DIR_LOCAL, exist_ok=True)

    print("=" * 55)
    print("  БЕКАП ПРОЕКТОВ: КАСКАД + ХАЙРОС")
    print("=" * 55)
    print()

    # ── Конфигурация сервера ──
    SERVER_HOST = input("IP сервера: ").strip()
    SERVER_USER = input("Логин [root]: ").strip() or "root"
    SERVER_PASS = input("Пароль: ").strip()

    try:
        ssh = connect_ssh()
    except Exception as e:
        print(f"[ОШИБКА] Не удалось подключиться к серверу: {e}")
        sys.exit(1)

    print(f"[OK] Подключение к {SERVER_HOST} установлено")

    # Папка бекапов на сервере
    run_cmd(ssh, "mkdir -p /root/backups")

    remote_archives = {}

    # ── Шаг 1: Архивация проектов на сервере ──
    print()
    print("── Шаг 1/3: Архивация на сервере ──")
    for name, path in PROJECTS.items():
        archive = f"/root/backups/{name}_{TS}.tar.gz"

        # Проверяем, что директория существует
        out, err, code = run_cmd(ssh, f"test -d {path} && echo EXISTS")
        if "EXISTS" not in out:
            print(f"[ОШИБКА] Директория {path} не найдена на сервере!")
            continue

        print(f"  Архивирую {path} ...")
        out, err, code = run_cmd(
            ssh,
            f"cd {path} && tar "
            f"--exclude='venv' --exclude='__pycache__' --exclude='.git' "
            f"-czf {archive} . && echo TAR_OK"
        )
        if code != 0 or "TAR_OK" not in out:
            print(f"  [ОШИБКА] tar: {err.strip()}")
            continue

        # Размер архива
        out, _, _ = run_cmd(ssh, f"stat -c %s {archive}")
        size_mb = int(out.strip() or 0) / 1024 / 1024

        # Есть ли база данных в архиве
        out, _, _ = run_cmd(ssh, f"tar -tzf {archive} | grep -c 'bot_cache.db' || true")
        db_count = out.strip()

        remote_archives[name] = archive
        print(f"  [OK] {archive}")
        print(f"       Размер: {size_mb:.1f} МБ | БД bot_cache.db в архиве: {db_count}")

    if not remote_archives:
        print()
        print("[ОШИБКА] Ни один проект не заархивирован. Прерывание.")
        ssh.close()
        sys.exit(1)

    # ── Шаг 2: Скачивание локально ──
    print()
    print("── Шаг 2/3: Скачивание в backups/ ──")
    sftp = ssh.open_sftp()
    downloaded = []
    for name, archive in remote_archives.items():
        local_path = os.path.join(BACKUP_DIR_LOCAL, os.path.basename(archive))
        print(f"  Скачиваю {os.path.basename(archive)} ...")
        try:
            sftp.get(archive, local_path)
            local_size = os.path.getsize(local_path) / 1024 / 1024
            downloaded.append((name, local_path))
            print(f"  [OK] {local_path} ({local_size:.1f} МБ)")
        except Exception as e:
            print(f"  [ОШИБКА] Скачивание {name}: {e}")
    sftp.close()

    # ── Шаг 3: Верификация локальных архивов ──
    print()
    print("── Шаг 3/3: Проверка целостности ──")
    all_ok = True
    for name, local_path in downloaded:
        try:
            with tarfile.open(local_path, "r:gz") as tf:
                members = tf.getnames()
                dbs = [m for m in members if m.endswith("bot_cache.db")]
                key_files = [m for m in members if m.endswith(("bot.py", "api.py"))]
                status = "OK"
                if not dbs:
                    status = "НЕТ БАЗЫ ДАННЫХ!"
                    all_ok = False
                print(f"  {os.path.basename(local_path)}: {status}")
                print(f"       Всего файлов: {len(members)} | БД: {len(dbs)} | bot.py/api.py: {len(key_files)}")
                for db in dbs:
                    info = tf.getmember(db)
                    print(f"       - {db} ({info.size / 1024 / 1024:.2f} МБ)")
        except Exception as e:
            print(f"  {os.path.basename(local_path)}: ПОВРЕЖДЁН — {e}")
            all_ok = False

    ssh.close()

    # ── Итог ──
    print()
    print("=" * 55)
    if all_ok and len(downloaded) == len(remote_archives):
        print("  ✅ БЕКАП ЗАВЕРШЁН УСПЕШНО!")
    else:
        print("  ⚠️ БЕКАП ЗАВЕРШЁН С ОШИБКАМИ — проверьте вывод выше")
    print("=" * 55)
    for name, local_path in downloaded:
        print(f"  {name.upper():8s}: {local_path} ({os.path.getsize(local_path)/1024/1024:.1f} МБ)")
    print()


if __name__ == "__main__":
    main()