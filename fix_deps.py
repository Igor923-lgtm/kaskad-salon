"""fix_deps.py — Установка недостающих зависимостей."""
import paramiko
import time

SERVER = "92.246.128.94"
USER = "root"
PASS = "kf24mP2c7KQBViNi"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, username=USER, password=PASS, timeout=15)
print(f"Connected to {SERVER}\n")

# Устанавливаем python-multipart
for svc in ["kaskad", "hairos"]:
    print(f"Установка зависимостей для {svc}...")
    stdin, stdout, stderr = ssh.exec_command(f"cd /opt/{svc}-bot && source venv/bin/activate && pip install python-multipart 2>&1", timeout=60)
    out = stdout.read().decode().strip()
    print(f"  {out[:200]}")

# Перезапускаем сервисы
print("\nПерезапуск сервисов...")
ssh.exec_command("systemctl restart kaskad-crm hairos-crm")
time.sleep(5)

# Проверяем
print("\n=== Статус ===")
for svc in ["kaskad", "hairos"]:
    stdin, stdout, stderr = ssh.exec_command(f"systemctl is-active {svc}-crm")
    status = stdout.read().decode().strip()
    print(f"  {svc}-crm: {status}")

# Health check
print("\n=== Health ===")
for name, port in [("kaskad", 8000), ("hairos", 8005)]:
    stdin, stdout, stderr = ssh.exec_command(f"curl -s http://localhost:{port}/health --connect-timeout 5")
    out = stdout.read().decode().strip()
    print(f"  {name}: {out[:100]}")

# Порты
print("\n=== Порты ===")
stdin, stdout, stderr = ssh.exec_command("ss -tlnp | grep -E '800[0-5]'")
print(stdout.read().decode().strip())

ssh.close()
