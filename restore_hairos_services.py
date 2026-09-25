"""restore_hairos_services.py — Восстановление услуг Hairos из price_data.py."""
import paramiko
import time

SERVER = "92.246.128.94"
USER = "root"
PASS = "kf24mP2c7KQBViNi"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, username=USER, password=PASS, timeout=15)
print("Connected\n")

# 1. Stop hairos
print("=== Остановка hairos ===")
ssh.exec_command("systemctl stop hairos-crm hairos-polling")
time.sleep(2)
print(ssh.exec_command("systemctl is-active hairos-crm hairos-polling")[1].read().decode())

# 2. Create script to rebuild services from price_data.py
restore_script = """import sqlite3
import sys
sys.path.insert(0, '/opt/hairos-bot')
from price_data import PRICE_SECTIONS

db = sqlite3.connect('/opt/hairos-bot/bot_cache.db')

# Clear existing services
db.execute('DELETE FROM services')
print('Cleared existing services')

# Rebuild from price_data.py
service_id = 1
for cat_idx, section in enumerate(PRICE_SECTIONS):
    title = section['title']
    note = section.get('note', '')

    for svc_idx, (name, price) in enumerate(section['services']):
        db.execute(
            'INSERT INTO services (id, category_title, category_note, category_index, service_index, name, price, gender, sort_order, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (service_id, title, note, cat_idx, svc_idx, name, str(price), 'all', svc_idx, 1)
        )
        service_id += 1
        print(f'  Added: {name} ({price})')

db.commit()
count = db.execute('SELECT count(*) FROM services').fetchone()[0]
print(f'\\nTotal services: {count}')
db.close()
"""

sftp = ssh.open_sftp()
f = sftp.open('/tmp/restore_services.py', 'w')
f.write(restore_script)
f.close()
sftp.close()

# 3. Run restore script
print("\n=== Восстановление услуг ===")
print(ssh.exec_command("cd /opt/hairos-bot && source venv/bin/activate && python3 /tmp/restore_services.py")[1].read().decode())

# 4. Start hairos
print("\n=== Запуск hairos ===")
ssh.exec_command("systemctl start hairos-crm hairos-polling")
time.sleep(5)
print(ssh.exec_command("systemctl is-active hairos-crm hairos-polling")[1].read().decode())

# 5. Verify
print("\n=== Проверка ===")
print(ssh.exec_command("curl -s http://localhost:8005/api/services --connect-timeout 5 | head -c 500")[1].read().decode())

ssh.close()
print("\n=== ГОТОВО ===")
