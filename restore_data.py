"""restore_data.py — Восстановление данных и проверка."""
import paramiko
import time

SERVER = "92.246.128.94"
USER = "root"
PASS = "kf24mP2c7KQBViNi"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, username=USER, password=PASS, timeout=15)
print("Connected\n")

# 1. Stop services
print("=== Остановка сервисов ===")
ssh.exec_command("systemctl stop hairos-crm hairos-polling")
ssh.exec_command("systemctl stop kaskad-crm kaskad-polling")
time.sleep(2)
out = ssh.exec_command("systemctl is-active hairos-crm hairos-polling kaskad-crm kaskad-polling")[1].read().decode()
print(out)

# 2. Upload DB files
print("\n=== Загрузка баз данных ===")
sftp = ssh.open_sftp()
sftp.put(r"C:\Users\User\mimo\kaskad-multitenant\salons\hairos\data\bot_cache.db", "/opt/hairos-bot/bot_cache.db")
print("hairos: OK (3 сентября)")
sftp.put(r"C:\Users\User\mimo\kaskad-multitenant\backups\_inspect_1553\bot_cache.db", "/opt/kaskad-bot/bot_cache.db")
print("kaskad: OK (24 августа)")
sftp.close()

# 3. Start services
print("\n=== Запуск сервисов ===")
ssh.exec_command("systemctl start hairos-crm hairos-polling")
ssh.exec_command("systemctl start kaskad-crm kaskad-polling")
time.sleep(5)
out = ssh.exec_command("systemctl is-active hairos-crm hairos-polling kaskad-crm kaskad-polling")[1].read().decode()
print(out)

# 4. Verify data
print("\n=== Проверка данных ===")
script = """import json, urllib.request
for name, port in [("hairos", 8005), ("kaskad", 8000)]:
    try:
        r = urllib.request.urlopen("http://localhost:" + str(port) + "/api/masters", timeout=5)
        masters = len(json.loads(r.read()))
        r2 = urllib.request.urlopen("http://localhost:" + str(port) + "/api/bookings", timeout=5)
        bookings = len(json.loads(r2.read()))
        print(name + ": " + str(masters) + " masters, " + str(bookings) + " bookings")
    except Exception as e:
        print(name + ": error " + str(e))
"""
sftp = ssh.open_sftp()
f = sftp.open("/tmp/count.py", "w")
f.write(script)
f.close()
sftp.close()
print(ssh.exec_command("cd /opt/kaskad-bot && source venv/bin/activate && python3 /tmp/count.py")[1].read().decode())

# 5. Health check
print("\n=== Health Check ===")
for name, port in [("kaskad", 8000), ("hairos", 8005)]:
    out = ssh.exec_command("curl -s http://localhost:" + str(port) + "/health --connect-timeout 5")[1].read().decode()
    print(name + ": " + out)

ssh.close()
print("\n=== ГОТОВО ===")
