"""check_logs.py — Проверка логов CRM сервисов."""
import paramiko
import time

SERVER = "92.246.128.94"
USER = "root"
PASS = "kf24mP2c7KQBViNi"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, username=USER, password=PASS, timeout=15)
print(f"Connected to {SERVER}\n")

# Ждём ещё 15 сек
print("Ожидание 15 сек...")
time.sleep(15)

for svc in ["kaskad", "hairos"]:
    print(f"\n=== {svc} CRM логи ===")
    stdin, stdout, stderr = ssh.exec_command(f"journalctl -u {svc}-crm --since 3min --no-pager 2>&1 | tail -30")
    out = stdout.read().decode().strip()
    print(out[:500] if out else "(пусто)")

    print(f"\n=== {svc} Bot логи ===")
    stdin, stdout, stderr = ssh.exec_command(f"journalctl -u {svc}-polling --since 3min --no-pager 2>&1 | tail -15")
    out = stdout.read().decode().strip()
    print(out[:300] if out else "(пусто)")

# Проверяем статус снова
print("\n=== Статус после ожидания ===")
for svc in ["kaskad", "hairos"]:
    stdin, stdout, stderr = ssh.exec_command(f"systemctl is-active {svc}-crm {svc}-polling")
    out = stdout.read().decode().strip()
    print(f"  {svc}: {out}")

# Проверяем health
print("\n=== Health ===")
for name, port in [("kaskad", 8000), ("hairos", 8005)]:
    stdin, stdout, stderr = ssh.exec_command(f"curl -s http://localhost:{port}/health --connect-timeout 5")
    out = stdout.read().decode().strip()
    print(f"  {name}: {out[:100]}")

# Проверяем порты
print("\n=== Порты ===")
stdin, stdout, stderr = ssh.exec_command("ss -tlnp | grep -E '800[0-5]'")
out = stdout.read().decode().strip()
print(out if out else "Нет слушающих портов")

ssh.close()
