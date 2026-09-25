import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

print("=" * 50)
print("  HAIROS STUDIO — ПОЛНАЯ ПРОВЕРКА")
print("=" * 50)

# 1. Services
print("\n[1] Сервисы:")
for svc in ['hairos-bot', 'hairos-polling']:
    stdin, stdout, stderr = ssh.exec_command(f"systemctl is-active {svc}")
    status = stdout.read().decode().strip()
    print(f"  {svc}: {'OK' if status == 'active' else 'ERROR: ' + status}")

# 2. Health
print("\n[2] Health API:")
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/health")
print(f"  {stdout.read().decode().strip()}")

# 3. Masters
print("\n[3] Мастера:")
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/api/masters")
masters = stdout.read().decode()
if "Кристина" in masters and "Лиза" in masters:
    print("  OK: Кристина и Лиза найдены")
else:
    print(f"  ERROR: {masters[:200]}")

# 4. Services API
print("\n[4] Услуги:")
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/api/services")
services = stdout.read().decode()
if "Наращивание" in services and "Восстановление" in services:
    print("  OK: Услуги загружены")
else:
    print(f"  ERROR: {services[:200]}")

# 5. Salon hours
print("\n[5] Часы работы:")
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/api/salon-hours")
print(f"  {stdout.read().decode().strip()[:100]}")

# 6. Login page
print("\n[6] Логин CRM:")
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/login")
login = stdout.read().decode()
if "Hairos" in login:
    print("  OK: Страница логина работает")
else:
    print(f"  ERROR: {login[:200]}")

# 7. Master app
print("\n[7] Приложение мастера:")
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/master")
master_app = stdout.read().decode()
if "master" in master_app.lower():
    print("  OK: Приложение мастера работает")
else:
    print(f"  ERROR: {master_app[:200]}")

# 8. Masters-with-bookings
print("\n[8] Masters+Bookings API:")
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/api/masters-with-bookings")
mwb = stdout.read().decode()
if "Кристина" in mwb:
    print("  OK: API работает")
else:
    print(f"  ERROR: {mwb[:200]}")

# 9. Finance API
print("\n[9] Finance API:")
stdin, stdout, stderr = ssh.exec_command("curl -s http://localhost:8005/api/finance/summary")
finance = stdout.read().decode()
if "Unauthorized" in finance:
    print("  OK: Требует авторизации (как и должно)")
else:
    print(f"  {finance[:100]}")

# 10. Bot logs
print("\n[10] Логи бота (последние ошибки):")
stdin, stdout, stderr = ssh.exec_command("journalctl -u hairos-polling --since 10min --no-pager | grep -i error | tail -5")
errors = stdout.read().decode().strip()
print(f"  {errors if errors else 'Нет ошибок'}")

# 11. CRM logs
print("\n[11] Логи CRM (последние ошибки):")
stdin, stdout, stderr = ssh.exec_command("journalctl -u hairos-bot --since 10min --no-pager | grep -i error | tail -5")
errors = stdout.read().decode().strip()
print(f"  {errors if errors else 'Нет ошибок'}")

# 12. Database tables
print("\n[12] Таблицы БД:")
stdin, stdout, stderr = ssh.exec_command("cd /opt/hairos-bot && source venv/bin/activate && python3 -c \"import asyncio,aiosqlite; asyncio.run((lambda: (lambda db: db.execute('SELECT name FROM sqlite_master WHERE type=\\\"table\\\"'))(aiosqlite.connect('bot_cache.db')))())\"")
# Simpler check
stdin, stdout, stderr = ssh.exec_command("ls -la /opt/hairos-bot/bot_cache.db")
db_info = stdout.read().decode().strip()
print(f"  {db_info}")

# 13. Logo
print("\n[13] Логотип:")
stdin, stdout, stderr = ssh.exec_command("ls -la /opt/hairos-bot/logo.png /opt/hairos-bot/static/logo.png")
print(f"  {stdout.read().decode().strip()}")

# 14. Works photos
print("\n[14] Фото работ:")
stdin, stdout, stderr = ssh.exec_command("ls /opt/hairos-bot/works_photos/ | wc -l")
print(f"  {stdout.read().decode().strip()} фото")

# 15. Branding check
print("\n[15] Брендинг (проверка KASKAD):")
stdin, stdout, stderr = ssh.exec_command("grep -rc KASKAD /opt/hairos-bot/bot.py /opt/hairos-bot/templates/*.html /opt/hairos-bot/static/manifest.json 2>/dev/null | grep -v ':0$'")
kaskad_refs = stdout.read().decode().strip()
print(f"  {kaskad_refs if kaskad_refs else 'OK: Нет упоминаний KASKAD'}")

ssh.close()
print("\n" + "=" * 50)
print("  ПРОВЕРКА ЗАВЕРШЕНА")
print("=" * 50)
