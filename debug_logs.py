"""debug_logs.py — Диагностика CRM сервисов."""
import paramiko

SERVER = "92.246.128.94"
USER = "root"
PASS = "kf24mP2c7KQBViNi"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, username=USER, password=PASS, timeout=15)
print(f"Connected to {SERVER}\n")

# Проверяем что python может запустить uvicorn
print("=== Тест запуска uvicorn ===")
stdin, stdout, stderr = ssh.exec_command("cd /opt/kaskad-bot && source venv/bin/activate && python3 -c 'import uvicorn; print(uvicorn.__version__)'", timeout=30)
print("  stdout:", stdout.read().decode().strip())
print("  stderr:", stderr.read().decode().strip())

# Пробуем запустить вручную
print("\n=== Ручной запуск kaskad CRM (5 сек) ===")
stdin, stdout, stderr = ssh.exec_command("cd /opt/kaskad-bot && SALON_ID=kaskad timeout 5 /opt/kaskad-bot/venv/bin/python3 -m uvicorn api:app --host 0.0.0.0 --port 8000 2>&1", timeout=15)
print("  stdout:", stdout.read().decode().strip()[:300])
print("  stderr:", stderr.read().decode().strip()[:300])

# Проверяем journalctl с правильным форматом
print("\n=== journalctl kaskad-crm ===")
stdin, stdout, stderr = ssh.exec_command("journalctl -u kaskad-crm -n 30 --no-pager", timeout=15)
print(stdout.read().decode().strip()[:500])

print("\n=== journalctl hairos-crm ===")
stdin, stdout, stderr = ssh.exec_command("journalctl -u hairos-crm -n 30 --no-pager", timeout=15)
print(stdout.read().decode().strip()[:500])

# Проверяем статус-код
print("\n=== Systemd status ===")
for svc in ["kaskad", "hairos"]:
    stdin, stdout, stderr = ssh.exec_command(f"systemctl status {svc}-crm --no-pager", timeout=10)
    print(f"\n--- {svc}-crm ---")
    print(stdout.read().decode().strip()[:400])

ssh.close()
