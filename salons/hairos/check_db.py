import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

# Write check script
sftp = ssh.open_sftp()
with sftp.open('/opt/hairos-bot/check_all.py', 'w') as f:
    f.write('import sqlite3\n')
    f.write('db = sqlite3.connect("bot_cache.db")\n')
    f.write('cur = db.cursor()\n')
    f.write('print("=== MASTERS ===")\n')
    f.write('try:\n')
    f.write('    cur.execute("SELECT * FROM masters")\n')
    f.write('    for r in cur.fetchall(): print(r)\n')
    f.write('except: print("empty")\n')
    f.write('print("=== USER_PERM ===")\n')
    f.write('try:\n')
    f.write('    cur.execute("SELECT * FROM user_permissions")\n')
    f.write('    for r in cur.fetchall(): print(r)\n')
    f.write('except: print("empty")\n')
    f.write('print("=== MASTER_SESSIONS ===")\n')
    f.write('try:\n')
    f.write('    cur.execute("SELECT * FROM master_sessions")\n')
    f.write('    for r in cur.fetchall(): print(r)\n')
    f.write('except: print("empty")\n')
    f.write('print("=== TABLES ===")\n')
    f.write('cur.execute(\'SELECT name FROM sqlite_master WHERE type="table"\')\n')
    f.write('for r in cur.fetchall(): print(r[0])\n')
    f.write('db.close()\n')
sftp.close()

# Run it
stdin, stdout, stderr = ssh.exec_command('cd /opt/hairos-bot && source venv/bin/activate && python3 check_all.py 2>&1')
print(stdout.read().decode())
ssh.close()
