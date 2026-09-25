"""verify_ubuntu.py — Проверка сервисов на Ubuntu сервере."""
import paramiko

SERVER = "92.246.128.94"
USER = "root"
PASS = "kf24mP2c7KQBViNi"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, username=USER, password=PASS, timeout=15)
print(f"Connected to {SERVER}\n")

# Статус сервисов
print("=== Статус сервисов ===")
for svc in ["kaskad", "hairos"]:
    for suffix in ["crm", "polling"]:
        name = f"{svc}-{suffix}"
        stdin, stdout, stderr = ssh.exec_command(f"systemctl is-active {name}")
        status = stdout.read().decode().strip()
        print(f"  {name:25s} {status}")

# Health check
print("\n=== Health Check ===")
for name, port in [("kaskad", 8000), ("hairos", 8005)]:
    stdin, stdout, stderr = ssh.exec_command(f"curl -s http://localhost:{port}/health --connect-timeout 5")
    out = stdout.read().decode().strip()
    print(f"  {name:10s} :{port} -> {out[:100]}")

# Проверка страниц hairos
print("\n=== Hairos CRM страницы ===")
pages = ["crm", "settings", "finance", "schedule", "masters", "bookings", "widget", "book", "login"]
for page in pages:
    stdin, stdout, stderr = ssh.exec_command(f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:8005/{page} --connect-timeout 5")
    code = stdout.read().decode().strip()
    print(f"  /{page:15s} HTTP {code}")

# API endpoints
print("\n=== API Endpoints ===")
for path in ["api/services", "api/masters", "api/bookings/grouped"]:
    stdin, stdout, stderr = ssh.exec_command(f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:8005/{path} --connect-timeout 5")
    code = stdout.read().decode().strip()
    print(f"  /{path:25s} HTTP {code}")

# Логи ошибок
print("\n=== Последние ошибки (2 мин) ===")
for svc in ["kaskad", "hairos"]:
    stdin, stdout, stderr = ssh.exec_command(f"journalctl -u {svc}-crm --since 2min --no-pager 2>&1 | grep -i -E 'error|traceback|exception' | tail -3")
    err = stdout.read().decode().strip()
    if err:
        print(f"  {svc}: {err[:150]}")
    else:
        print(f"  {svc}: нет ошибок")

# Проверка файлов
print("\n=== Файлы на сервере ===")
for svc in ["kaskad", "hairos"]:
    stdin, stdout, stderr = ssh.exec_command(f"ls -la /opt/{svc}-bot/*.py /opt/{svc}-bot/.env /opt/{svc}-bot/bot_cache.db 2>/dev/null")
    out = stdout.read().decode().strip()
    if out:
        lines = out.split('\n')
        print(f"  {svc}: {len(lines)} файлов")
    else:
        print(f"  {svc}: нет файлов!")

ssh.close()
print("\n=== ПРОВЕРКА ЗАВЕРШЕНА ===")
