import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)
sftp = ssh.open_sftp()

with sftp.open('/opt/hairos-bot/debug_finance.py', 'w') as f:
    f.write("import sqlite3\n")
    f.write("db = sqlite3.connect('bot_cache.db')\n")
    f.write("cur = db.cursor()\n")
    f.write("print('=== TRANSACTIONS ===')\n")
    f.write("cur.execute('SELECT count(*) FROM transactions')\n")
    f.write("print('Count:', cur.fetchone()[0])\n")
    f.write("cur.execute('SELECT * FROM transactions LIMIT 5')\n")
    f.write("for r in cur.fetchall(): print(r)\n")
    f.write("print('\\n=== BOOKINGS ===')\n")
    f.write("cur.execute('SELECT count(*), sum(CASE WHEN completed=1 THEN 1 ELSE 0 END) FROM bookings')\n")
    f.write("r = cur.fetchone()\n")
    f.write("print('Total:', r[0], 'Completed:', r[1])\n")
    f.write("print('\\n=== BOOKINGS SAMPLE ===')\n")
    f.write("cur.execute('SELECT master_name, service_name, price, date, time, completed FROM bookings LIMIT 5')\n")
    f.write("for r in cur.fetchall(): print(r)\n")
    f.write("db.close()\n")

sftp.close()
stdin, stdout, stderr = ssh.exec_command('cd /opt/hairos-bot && source venv/bin/activate && python3 debug_finance.py 2>&1')
print(stdout.read().decode())
ssh.close()
