import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('92.246.128.94', username='root', password='kf24mP2c7KQBViNi', timeout=15)

env_content = """# === Салон ===
SALON_ID=kaskad

# === Telegram ===
BOT_TOKEN=8529669800:AAHnb6jtqxCLpZv6rtQ1UxzCwiZB5IcoMfE
ADMIN_IDS=1088102645

# === База данных ===
DB_PATH=bot_cache.db

# === CRM ===
CRM_PASSWORD=kaskad2026
CRM_SECRET=kaskad_secret_key_2026_unique
CRM_API_URL=

# === Прокси ===
SOCKS5_PROXY=

# === Салон: информация ===
SALON_NAME=Каскад
SALON_ADDRESS=Минск, Кальварийская ул., 52
SALON_PHONE=+375 29 120-61-01
SALON_PHONE_SECONDARY=
SALON_METRO=Молодёжная (680 м)
SALON_MAP_URL=https://yandex.by/maps/org/kaskad/1176196517/?ll=27.512334%2C53.908495&z=14
SALON_WHATSAPP=+375 29 120-61-01

# === Салон: часы работы ===
SALON_HOURS_START=10
SALON_HOURS_END=21
SALON_HOURS_SAT_START=10
SALON_HOURS_SAT_END=21
SALON_HOURS_SUN_START=10
SALON_HOURS_SUN_END=21

# === Часовой пояс ===
SALON_TIMEZONE=Europe/Moscow

# === Функции салона ===
DISCOUNTS_ENABLED=false
BIRTHDAY_ENABLED=false
"""

sftp = ssh.open_sftp()
f = sftp.open('/opt/kaskad-bot/.env', 'w')
f.write(env_content)
f.close()
sftp.close()

print("OK: .env Kaskad обновлён")

# Restart kaskad
import time
ssh.exec_command('systemctl restart kaskad-crm kaskad-polling')
time.sleep(3)
print(ssh.exec_command('systemctl is-active kaskad-crm kaskad-polling')[1].read().decode())

ssh.close()
