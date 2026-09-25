import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)
sftp = ssh.open_sftp()

with sftp.open('/opt/hairos-bot/fix_marina_sched.py', 'w') as f:
    f.write("import sqlite3\n")
    f.write("db = sqlite3.connect('bot_cache.db')\n")
    f.write("cur = db.cursor()\n")
    f.write("for dow in range(7):\n")
    f.write("    cur.execute('INSERT OR IGNORE INTO master_schedule (master_name, day_of_week, start_time, end_time, is_day_off) VALUES (?, ?, ?, ?, ?)',\n")
    f.write("        ('Марина', dow, '10:00', '22:00', 0))\n")
    f.write("db.commit()\n")
    f.write("cur.execute('SELECT master_name, count(*) FROM master_schedule GROUP BY master_name')\n")
    f.write("for r in cur.fetchall(): print(r)\n")
    f.write("db.close()\n")

sftp.close()
stdin, stdout, stderr = ssh.exec_command('cd /opt/hairos-bot && source venv/bin/activate && python3 fix_marina_sched.py')
print(stdout.read().decode())
ssh.close()
