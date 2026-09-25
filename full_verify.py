"""full_verify.py — Полная проверка всех сервисов."""
import paramiko

SERVER = "92.246.128.94"
USER = "root"
PASS = "kf24mP2c7KQBViNi"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, username=USER, password=PASS, timeout=15)
print(f"Connected to {SERVER}\n")

def check(ssh, name, cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    return out

# === kaskad ===
print("=" * 50)
print("  KASKAD (порт 8000)")
print("=" * 50)
print("\nСтатус:")
for suffix in ["crm", "polling"]:
    status = check(ssh, "", f"systemctl is-active kaskad-{suffix}")
    print(f"  kaskad-{suffix}: {status}")

print("\nСтраницы:")
pages = ["health", "login", "crm", "settings", "finance", "schedule", "masters", "bookings", "widget", "book"]
for p in pages:
    code = check(ssh, "", f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:8000/{p} --connect-timeout 5")
    icon = "OK" if code in ("200", "307", "401", "403") else "FAIL"
    print(f"  /{p:15s} HTTP {code} {icon}")

print("\nAPI:")
for path in ["api/services", "api/masters", "api/bookings/grouped"]:
    code = check(ssh, "", f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:8000/{path} --connect-timeout 5")
    icon = "OK" if code in ("200", "401") else "FAIL"
    print(f"  /{path:25s} HTTP {code} {icon}")

# === hairos ===
print("\n" + "=" * 50)
print("  HAIROS (порт 8005)")
print("=" * 50)
print("\nСтатус:")
for suffix in ["crm", "polling"]:
    status = check(ssh, "", f"systemctl is-active hairos-{suffix}")
    print(f"  hairos-{suffix}: {status}")

print("\nСтраницы:")
for p in pages:
    code = check(ssh, "", f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:8005/{p} --connect-timeout 5")
    icon = "OK" if code in ("200", "307", "401", "403") else "FAIL"
    print(f"  /{p:15s} HTTP {code} {icon}")

# Доп. страницы hairos
extra = ["client-analytics", "users", "services-page", "master/login"]
for p in extra:
    code = check(ssh, "", f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:8005/{p} --connect-timeout 5")
    icon = "OK" if code in ("200", "307", "401", "403") else "FAIL"
    print(f"  /{p:15s} HTTP {code} {icon}")

print("\nAPI:")
for path in ["api/services", "api/masters", "api/bookings/grouped"]:
    code = check(ssh, "", f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:8005/{path} --connect-timeout 5")
    icon = "OK" if code in ("200", "401") else "FAIL"
    print(f"  /{path:25s} HTTP {code} {icon}")

# Bot health
print("\n" + "=" * 50)
print("  TELEGRAM БОТЫ")
print("=" * 50)
for svc in ["kaskad", "hairos"]:
    status = check(ssh, "", f"systemctl is-active {svc}-polling")
    errors = check(ssh, "", f"journalctl -u {svc}-polling -n 20 --no-pager 2>&1 | grep -i -E 'error|exception' | tail -3")
    print(f"\n  {svc}-polling: {status}")
    if errors:
        print(f"    Ошибки: {errors[:200]}")
    else:
        print(f"    Ошибок нет")

# Порты
print("\n" + "=" * 50)
print("  ПОРТЫ")
print("=" * 50)
out = check(ssh, "", "ss -tlnp | grep -E '800[0-5]'")
print(out)

ssh.close()
print("\n" + "=" * 50)
print("  ПРОВЕРКА ЗАВЕРШЕНА")
print("=" * 50)
print(f"\n  kaskad: http://{SERVER}:8000/login")
print(f"  hairos: http://{SERVER}:8005/login")
