import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)
sftp = ssh.open_sftp()

with sftp.open('/opt/hairos-bot/restore_admin.py', 'w') as f:
    f.write("""import sqlite3
db = sqlite3.connect('bot_cache.db')
cur = db.cursor()

# Check if Игорь already exists as master
cur.execute("SELECT id, name, phone, telegram_id, role FROM masters WHERE phone='+375298592000'")
existing = cur.fetchone()

if existing:
    print(f'Игорь already exists: id={existing[0]}, name={existing[1]}, role={existing[4]}')
    # Update role to super_admin if needed
    if existing[4] != 'super_admin':
        cur.execute("UPDATE masters SET role='super_admin', telegram_id=294308582 WHERE phone='+375298592000'")
        print('Updated role to super_admin')
    else:
        print('Already super_admin, no changes needed')
else:
    print('Игорь not found, inserting...')
    cur.execute("INSERT INTO masters (name, specialization, photo_file_id, description, categories, is_active, telegram_id, phone, role) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ('Игорь', 'Администратор', '', '', '', 1, 294308582, '+375298592000', 'super_admin'))
    print('Inserted Игорь as super_admin')

db.commit()

# Verify all masters
cur.execute("SELECT id, name, phone, telegram_id, role FROM masters")
print('\\nAll masters:')
for r in cur.fetchall():
    print(f'  id={r[0]} name={r[1]} phone={r[2]} tg_id={r[3]} role={r[4]}')

db.close()
print('\\nDone!')
""")

sftp.close()

stdin, stdout, stderr = ssh.exec_command('cd /opt/hairos-bot && source venv/bin/activate && python3 restore_admin.py 2>&1')
print(stdout.read().decode())
ssh.close()
