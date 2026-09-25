import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

print("=== FULL HAIROS DEPLOY VERIFICATION ===\n")

checks = [
    ("Health", "curl -s http://localhost:8005/health"),
    ("CRM Dashboard", "curl -s http://localhost:8005/crm"),
    ("Settings page", "curl -s http://localhost:8005/settings"),
    ("Finance page", "curl -s http://localhost:8005/finance"),
    ("Schedule page", "curl -s http://localhost:8005/schedule"),
    ("Masters page", "curl -s http://localhost:8005/masters"),
    ("Widget page", "curl -s http://localhost:8005/widget"),
    ("Book page", "curl -s http://localhost:8005/book"),
    ("Bookings page", "curl -s http://localhost:8005/bookings"),
    ("Login page", "curl -s http://localhost:8005/login"),
    ("Master Login", "curl -s http://localhost:8005/master/login"),
    ("Client Analytics", "curl -s http://localhost:8005/client-analytics"),
    ("Users page", "curl -s http://localhost:8005/users"),
    ("Services page", "curl -s http://localhost:8005/services-page"),
    ("Services API", "curl -s http://localhost:8005/api/services"),
    ("Masters API", "curl -s http://localhost:8005/api/masters"),
    ("Bookings grouped", "curl -s -o /dev/null -w '%{http_code}' http://localhost:8005/api/bookings/grouped"),
]

for name, cmd in checks:
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode().strip()
    size = len(out)
    if size > 100:
        status = "OK"
    elif out.startswith("{") or out.startswith("["):
        status = "OK"
    elif out in ("200", "401", "403"):
        status = "HTTP " + out
    elif size == 0:
        status = "EMPTY"
    else:
        status = "WARN (" + out[:60] + ")"
    print(f"  {name:25s} {status:20s} ({size} bytes)")

print("\n--- Services ---")
stdin, stdout, stderr = ssh.exec_command("systemctl is-active hairos-bot hairos-polling")
print("  " + stdout.read().decode().strip().replace("\n", " | "))

print("\n--- Bot errors (last 10min) ---")
stdin, stdout, stderr = ssh.exec_command("journalctl -u hairos-polling --since 10min --no-pager 2>&1 | grep -i error | tail -5")
err = stdout.read().decode().strip()
print("  " + (err if err else "none"))

print("\n--- CRM errors (last 10min) ---")
stdin, stdout, stderr = ssh.exec_command("journalctl -u hairos-bot --since 10min --no-pager 2>&1 | grep -i error | tail -5")
err = stdout.read().decode().strip()
print("  " + (err if err else "none"))

print("\n--- Deployed file sizes ---")
stdin, stdout, stderr = ssh.exec_command("ls -la /opt/hairos-bot/api.py /opt/hairos-bot/bot.py /opt/hairos-bot/config.py /opt/hairos-bot/db.py /opt/hairos-bot/price_data.py /opt/hairos-bot/bot_cache.db")
print(stdout.read().decode())

print("\n--- Templates on server ---")
stdin, stdout, stderr = ssh.exec_command("ls /opt/hairos-bot/templates/")
print("  " + stdout.read().decode().strip().replace("\n", ", "))

ssh.close()
print("\n=== VERIFICATION COMPLETE ===")
