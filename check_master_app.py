import paramiko
import sqlite3
import os

TMP = os.environ.get('TEMP', 'C:\\Temp')

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('92.246.128.94', username='root', password='kf24mP2c7KQBViNi', timeout=15)

# Check master endpoints
print("=== Master Endpoints (hairos :8005) ===")
for path in ['master/login', 'master', 'master/dashboard', 'master/schedule', 'master/bookings']:
    code = ssh.exec_command(f'curl -s -o /dev/null -w %{{http_code}} http://localhost:8005/{path} --connect-timeout 5')[1].read().decode()
    print(f'  /{path:25s} HTTP {code}')

print("\n=== Master Endpoints (kaskad :8000) ===")
for path in ['master/login', 'master', 'master/dashboard', 'master/schedule', 'master/bookings']:
    code = ssh.exec_command(f'curl -s -o /dev/null -w %{{http_code}} http://localhost:8000/{path} --connect-timeout 5')[1].read().decode()
    print(f'  /{path:25s} HTTP {code}')

# Check master sessions in DB
print("\n=== Master Sessions ===")
for svc in ['kaskad', 'hairos']:
    sftp = ssh.open_sftp()
    sftp.get(f'/opt/{svc}-bot/bot_cache.db', os.path.join(TMP, f'{svc}_check.db'))
    sftp.close()
    db = sqlite3.connect(os.path.join(TMP, f'{svc}_check.db'))
    try:
        count = db.execute('SELECT count(*) FROM master_sessions').fetchone()[0]
        print(f'  {svc}: {count} sessions')
        sessions = db.execute('SELECT master_name, token, expires FROM master_sessions LIMIT 5').fetchall()
        for s in sessions:
            print(f'    {s[0]}: expires={s[2]}')
    except Exception as e:
        print(f'  {svc}: table not found or error: {e}')
    db.close()

# Check master_login page
print("\n=== Master Login Page (hairos) ===")
result = ssh.exec_command('curl -s http://localhost:8005/master/login --connect-timeout 5 | head -30')[1].read().decode()
print(result[:500])

# Check templates
print("\n=== Templates ===")
for svc in ['kaskad', 'hairos']:
    files = ssh.exec_command(f'ls /opt/{svc}-bot/templates/master* 2>/dev/null')[1].read().decode()
    print(f'  {svc}: {files.strip() if files else "нет master шаблонов"}')

ssh.close()
