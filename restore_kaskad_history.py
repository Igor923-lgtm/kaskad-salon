"""
restore_kaskad_history.py — Деплой исправленного кода + восстановление записей КАСКАД.

Что делает:
1. Бэкапит текущие bot.py и db.py на сервере (.bak_<timestamp>)
2. Загружает исправленные файлы (автоочистка отключена)
3. Перезапускает сервисы kaskad-polling и kaskad-crm
4. Делает страховочную копию живой БД
5. Восстанавливает записи из всех ежедневных бекапов сервера
   (INSERT OR IGNORE — текущие данные не затрагиваются)
6. Показывает статистику до/после

Использование:
    python restore_kaskad_history.py
"""

import paramiko
import os
import sys
import time
from datetime import datetime

# ── Конфигурация сервера ──
SERVER_HOST = "94.141.98.224"
SERVER_USER = "root"
SERVER_PASS = "25ELkJTNxhwCC7vF"

BOT_DIR = "/opt/telegram-bot"
SERVICES = ["kaskad-polling", "kaskad-crm"]

TS = datetime.now().strftime("%Y%m%d_%H%M")

# Серверный скрипт восстановления записей из бекапов.
# ВАЖНО: без символов перевода строки внутри строковых литералов,
# т.к. они искажаются при записи файла через инструменты редактора.
MERGE_SCRIPT_LINES = [
    "import sqlite3, glob, os",
    "",
    'LIVE = os.path.abspath("/opt/telegram-bot/bot_cache.db")',
    "",
    "con = sqlite3.connect(LIVE)",
    "cur = con.cursor()",
    "",
    'before = cur.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]',
    'print(f"BEFORE: {before} bookings")',
    'for row in cur.execute("SELECT date, COUNT(*) FROM bookings GROUP BY date ORDER BY date"):',
    '    print(f"   {row[0]}: {row[1]}")',
    "",
    "# Колонки живой таблицы",
    'live_cols = [r[1] for r in cur.execute("PRAGMA table_info(bookings)")]',
    "",
    'backups = sorted(glob.glob("/opt/telegram-bot/backups/bot_cache_2026*.db"))',
    'print(f"Found {len(backups)} daily backups")',
    "",
    "total_added = 0",
    "for bp in backups:",
    "    try:",
    '        cur.execute("ATTACH DATABASE ? AS src", (bp,))',
    '        src_cols = [r[1] for r in cur.execute("PRAGMA src.table_info(bookings)")]',
    "        common = [c for c in src_cols if c in live_cols]",
    '        if "id" not in common:',
    '            print(f"  SKIP {os.path.basename(bp)}: no id column")',
    '            cur.execute("DETACH DATABASE src")',
    "            continue",
    '        cols_sql = ", ".join(common)',
    "        cur.execute(",
    '            f"INSERT OR IGNORE INTO main.bookings ({cols_sql}) SELECT {cols_sql} FROM src.bookings"',
    "        )",
    "        added = cur.rowcount",
    "        total_added += added",
    '        n_src = cur.execute("SELECT COUNT(*) FROM src.bookings").fetchone()[0]',
    '        print(f"  {os.path.basename(bp)}: {n_src} in backup, added {added}")',
    "        con.commit()",
    '        cur.execute("DETACH DATABASE src")',
    "    except Exception as e:",
    '        print(f"  ERR {os.path.basename(bp)}: {e}")',
    "        try:",
    '            cur.execute("DETACH DATABASE src")',
    "        except Exception:",
    "            pass",
    "",
    'after = cur.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]',
    'print(f"AFTER: {after} bookings (added {total_added})")',
    'print("By date:")',
    'for row in cur.execute("SELECT date, COUNT(*) FROM bookings GROUP BY date ORDER BY date"):',
    '    print(f"   {row[0]}: {row[1]}")',
    "con.close()",
]

MERGE_SCRIPT = chr(10).join(MERGE_SCRIPT_LINES)


def connect_ssh():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_HOST, username=SERVER_USER, password=SERVER_PASS, timeout=15)
    return ssh


def run_cmd(ssh, cmd, timeout=120):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    return stdout.read().decode(), stderr.read().decode(), exit_code


def stage(title):
    print()
    print(f"── {title} ──")


def main():
    print("=" * 60)
    print("  ВОССТАНОВЛЕНИЕ ЗАПИСЕЙ КАСКАД + ОТКЛЮЧЕНИЕ АВТООЧИСТКИ")
    print("=" * 60)

    # ── Проверка локальных файлов ──
    for f in ["bot.py", "db.py"]:
        if not os.path.exists(f):
            print(f"[ОШИБКА] Локальный файл {f} не найден!")
            sys.exit(1)
    print("[OK] Локальные bot.py и db.py на месте")

    ssh = connect_ssh()
    print(f"[OK] Подключение к {SERVER_HOST}")

    # ── Шаг 1: бэкап кода на сервере ──
    stage("Шаг 1/5: Бэкап текущего кода на сервере")
    out, err, code = run_cmd(
        ssh,
        f"cp {BOT_DIR}/bot.py {BOT_DIR}/bot.py.bak_{TS} && "
        f"cp {BOT_DIR}/db.py {BOT_DIR}/db.py.bak_{TS} && echo BACKUP_OK",
    )
    if "BACKUP_OK" not in out:
        print(f"[ОШИБКА] Бэкап не удался: {err}")
        ssh.close()
        sys.exit(1)
    print(f"[OK] Сохранены .bak_{TS}")

    # ── Шаг 2: загрузка исправленного кода ──
    stage("Шаг 2/5: Загрузка исправленного кода")
    sftp = ssh.open_sftp()
    sftp.put("bot.py", f"{BOT_DIR}/bot.py")
    sftp.put("db.py", f"{BOT_DIR}/db.py")
    sftp.close()
    print("[OK] bot.py и db.py загружены")

    # Проверка синтаксиса на сервере
    out, err, code = run_cmd(
        ssh, f"cd {BOT_DIR} && python3 -m py_compile bot.py db.py && echo COMPILE_OK"
    )
    if "COMPILE_OK" not in out:
        print(f"[ОШИБКА] Синтаксис на сервере: {err}")
        print("Откатываю бэкап...")
        run_cmd(
            ssh,
            f"cp {BOT_DIR}/bot.py.bak_{TS} {BOT_DIR}/bot.py && "
            f"cp {BOT_DIR}/db.py.bak_{TS} {BOT_DIR}/db.py",
        )
        ssh.close()
        sys.exit(1)
    print("[OK] Синтаксис проверен на сервере")

    # ── Шаг 3: перезапуск сервисов ──
    stage("Шаг 3/5: Перезапуск сервисов")
    run_cmd(ssh, "systemctl restart " + " ".join(SERVICES))
    time.sleep(4)
    out, _, _ = run_cmd(ssh, "systemctl is-active " + " ".join(SERVICES))
    statuses = out.strip().splitlines()
    for svc, st in zip(SERVICES, statuses):
        icon = "OK" if st.strip() == "active" else "ПРОБЛЕМА"
        print(f"  {svc}: {st.strip()} [{icon}]")
    if any(s.strip() != "active" for s in statuses):
        print("[ВНИМАНИЕ] Не все сервисы активны! Проверьте: journalctl -u kaskad-polling -n 30")

    # ── Шаг 4: страховочная копия живой БД ──
    stage("Шаг 4/5: Страховочная копия живой БД")
    out, err, code = run_cmd(
        ssh,
        f"cp {BOT_DIR}/bot_cache.db "
        f"{BOT_DIR}/backups/bot_cache_before_restore_{TS}.db && echo DB_BACKUP_OK",
    )
    if "DB_BACKUP_OK" not in out:
        print(f"[ОШИБКА] Копия БД не удалась: {err}")
        ssh.close()
        sys.exit(1)
    print(f"[OK] backups/bot_cache_before_restore_{TS}.db")

    # ── Шаг 5: восстановление записей из бекапов ──
    stage("Шаг 5/5: Восстановление записей из ежедневных бекапов")
    sftp = ssh.open_sftp()
    remote_script = f"{BOT_DIR}/_restore_merge_{TS}.py"
    with sftp.open(remote_script, "w") as f:
        f.write(MERGE_SCRIPT)
    sftp.close()

    out, err, code = run_cmd(ssh, f"python3 {remote_script}", timeout=180)
    print(out)
    if err.strip():
        print("STDERR:", err)

    # Удаляем временный скрипт
    run_cmd(ssh, f"rm -f {remote_script}")

    # Итоговая проверка сервисов
    time.sleep(2)
    out, _, _ = run_cmd(ssh, "systemctl is-active " + " ".join(SERVICES))
    print()
    print("Финальный статус сервисов:", ", ".join(out.strip().splitlines()))

    ssh.close()

    print()
    print("=" * 60)
    print("  ГОТОВО!")
    print("=" * 60)
    print("  1. Автоочистка отключена (код задеплоен)")
    print("  2. Записи восстановлены из бекапов (см. статистику выше)")
    print("  3. Страховочные копии:")
    print(f"     - код: {BOT_DIR}/*.bak_{TS}")
    print(f"     - БД:  {BOT_DIR}/backups/bot_cache_before_restore_{TS}.db")
    print()


if __name__ == "__main__":
    main()