import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)
sftp = ssh.open_sftp()

with sftp.open('/opt/hairos-bot/check_m.py', 'w') as f:
    f.write("import sqlite3\n")
    f.write("db = sqlite3.connect('bot_cache.db')\n")
    f.write("cur = db.cursor()\n")
    f.write("print('=== MASTERS ===')\n")
    f.write("cur.execute('SELECT id, name, phone, role, is_active FROM masters')\n")
    f.write("for r in cur.fetchall(): print(r)\n")
    f.write("print('\\n=== SCHEDULE ===')\n")
    f.write("cur.execute('SELECT master_name, day_of_week, start_time, end_time, is_day_off FROM master_schedule')\n")
    f.write("for r in cur.fetchall(): print(r)\n")
    f.write("db.close()\n")

sftp.close()
stdin, stdout, stderr = ssh.exec_command('cd /opt/hairos-bot && source venv/bin/activate && python3 check_m.py')
print(stdout.read().decode())
ssh.close()
