import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)
sftp = ssh.open_sftp()

with sftp.open('/tmp/check_hairos.py', 'w') as f:
    f.write("import sqlite3\n")
    f.write("db = sqlite3.connect('bot_cache.db')\n")
    f.write("cur = db.cursor()\n")
    f.write("cur.execute('SELECT count(*) FROM clients')\n")
    f.write("print('Total clients:', cur.fetchone()[0])\n")
    f.write("cur.execute('SELECT telegram_id, name, phone, client_type FROM clients ORDER BY telegram_id')\n")
    f.write("for r in cur.fetchall(): print(r)\n")
    f.write("db.close()\n")

with sftp.open('/tmp/check_kaskad.py', 'w') as f:
    f.write("import sqlite3\n")
    f.write("db = sqlite3.connect('bot_cache.db')\n")
    f.write("cur = db.cursor()\n")
    f.write("cur.execute('SELECT count(*) FROM clients')\n")
    f.write("print('Total clients:', cur.fetchone()[0])\n")
    f.write("cur.execute('SELECT telegram_id, name, phone, client_type FROM clients ORDER BY telegram_id')\n")
    f.write("for r in cur.fetchall(): print(r)\n")
    f.write("db.close()\n")

sftp.close()

print("=== HAIROS DB ===")
stdin, stdout, stderr = ssh.exec_command('cd /opt/hairos-bot && source venv/bin/activate && python3 /tmp/check_hairos.py 2>&1')
print(stdout.read().decode())

print("=== KASKAD DB ===")
stdin, stdout, stderr = ssh.exec_command('cd /opt/telegram-bot && source venv/bin/activate && python3 /tmp/check_kaskad.py 2>&1')
print(stdout.read().decode())

ssh.close()
