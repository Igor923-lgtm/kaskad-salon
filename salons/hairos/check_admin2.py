import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)
sftp = ssh.open_sftp()

with sftp.open('/opt/hairos-bot/check_admin.py', 'w') as f:
    f.write("""import sqlite3
db = sqlite3.connect('bot_cache.db')
cur = db.cursor()

print('=== CLIENTS with admin phones ===')
cur.execute("SELECT telegram_id, name, phone, client_type FROM clients WHERE phone IN ('+375298592000', '+375295040879') OR telegram_id IN (294308582, 7846553706)")
for r in cur.fetchall(): print(r)

print('\\n=== ALL masters ===')
cur.execute('SELECT id, name, phone, telegram_id, role FROM masters')
for r in cur.fetchall(): print(r)

print('\\n=== MASTER_SESSIONS (admin) ===')
cur.execute("SELECT * FROM master_sessions WHERE telegram_id IN (294308582, 7846553706)")
for r in cur.fetchall(): print(r)

db.close()
""")

sftp.close()
stdin, stdout, stderr = ssh.exec_command('cd /opt/hairos-bot && source venv/bin/activate && python3 check_admin.py 2>&1')
print(stdout.read().decode())
ssh.close()
