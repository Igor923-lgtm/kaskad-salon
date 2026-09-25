import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)
sftp = ssh.open_sftp()

# Write restore script
with sftp.open('/opt/hairos-bot/restore_data.py', 'w') as f:
    f.write("""import sqlite3
db = sqlite3.connect('bot_cache.db')
cur = db.cursor()

# 1. Restore phone numbers
cur.execute("UPDATE masters SET phone='+375295949109' WHERE name='Кристина'")
print(f"Кристина: {cur.rowcount} rows")

cur.execute("UPDATE masters SET phone='+375333077592' WHERE name='Лиза'")
print(f"Лиза: {cur.rowcount} rows")

cur.execute("UPDATE masters SET phone='+375295040879', telegram_id=7846553706 WHERE name='Марина'")
print(f"Марина: {cur.rowcount} rows")

db.commit()

# 2. Verify
cur.execute("SELECT id, name, phone, telegram_id, role FROM masters")
for r in cur.fetchall():
    print(f"  id={r[0]} name={r[1]} phone={r[2]} tg_id={r[3]} role={r[4]}")

db.close()
print("Done!")
""")

sftp.close()

stdin, stdout, stderr = ssh.exec_command('cd /opt/hairos-bot && source venv/bin/activate && python3 restore_data.py 2>&1')
print(stdout.read().decode())
ssh.close()
