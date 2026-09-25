import paramiko
import sys

SERVER = '45.159.172.228'
USER = 'root'
PASS = 'DndhJ98X1U8LZg24'

def run_check(ssh, name, cmd):
    try:
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        return name, out, err
    except Exception as e:
        return name, '', str(e)

def main():
    print("=" * 60)
    print("ПРОВЕРКА ПРОЕКТОВ НА НОВОМ СЕРВЕРЕ")
    print(f"Сервер: {SERVER}")
    print("=" * 60)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print("\n[1] Подключение к серверу...")
        ssh.connect(SERVER, username=USER, password=PASS, timeout=15)
        print("    ✓ Подключение установлено")
    except Exception as e:
        print(f"    ✗ Ошибка подключения: {e}")
        sys.exit(1)

    # Проверка Docker контейнеров
    print("\n[2] Docker контейнеры:")
    name, out, err = run_check(ssh, "containers", "docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'")
    if out:
        for line in out.split('\n'):
            print(f"    {line}")
    else:
        print(f"    Ошибка: {err}")

    # Health check для всех сервисов
    print("\n[3] Health check:")
    services = [
        ("kaskad", 8000),
        ("salon-1", 8001),
        ("salon-2", 8002),
        ("salon-3", 8003),
        ("salon-4", 8004),
        ("hairos", 8005),
    ]

    for name, port in services:
        name, out, err = run_check(ssh, name, f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{port}/health --connect-timeout 5")
        status = out if out else "ERROR"
        icon = "✓" if status == "200" else "✗"
        print(f"    {icon} {name:10s} (:{port}) - HTTP {status}")

    # Проверка CRM страниц hairos
    print("\n[4] CRM страницы (hairos :8005):")
    crm_pages = ["crm", "settings", "finance", "schedule", "masters", "bookings", "widget", "book"]
    for page in crm_pages:
        name, out, err = run_check(ssh, page, f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:8005/{page} --connect-timeout 5")
        status = out if out else "ERROR"
        icon = "✓" if status in ("200", "401", "403") else "✗"
        print(f"    {icon} /{page:15s} - HTTP {status}")

    # Проверка API endpoints
    print("\n[5] API endpoints (hairos):")
    api_endpoints = [
        ("api/services", "api/services"),
        ("api/masters", "api/masters"),
        ("api/bookings", "api/bookings/grouped"),
    ]
    for name, path in api_endpoints:
        name, out, err = run_check(ssh, name, f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:8005/{path} --connect-timeout 5")
        status = out if out else "ERROR"
        icon = "✓" if status in ("200", "401") else "✗"
        print(f"    {icon} /{path:25s} - HTTP {status}")

    # Проверка логов на ошибки
    print("\n[6] Ошибки в логах (последние 10 минут):")
    name, out, err = run_check(ssh, "logs", "docker logs hairos-bot --since 10m 2>&1 | grep -i -E 'error|exception|traceback' | tail -5")
    if out:
        for line in out.split('\n')[:5]:
            print(f"    ⚠ {line[:80]}")
    else:
        print("    ✓ Ошибок не обнаружено")

    # Проверка баз данных
    print("\n[7] Базы данных:")
    name, out, err = run_check(ssh, "dbs", "ls -la /opt/*/bot_cache.db 2>/dev/null || echo 'Not found'")
    if out and "Not found" not in out:
        for line in out.split('\n'):
            print(f"    {line}")
    else:
        print("    ⚠ Базы данных не найдены в /opt/*/")

    # Проверка disk space
    print("\n[8] Дисковое пространство:")
    name, out, err = run_check(ssh, "disk", "df -h / | tail -1")
    if out:
        print(f"    {out}")

    ssh.close()

    print("\n" + "=" * 60)
    print("ПРОВЕРКА ЗАВЕРШЕНА")
    print("=" * 60)

if __name__ == "__main__":
    main()
