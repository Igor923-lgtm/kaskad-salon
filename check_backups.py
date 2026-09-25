import paramiko
import sqlite3
import os

TMP = os.environ.get('TEMP', 'C:\\Temp')
os.makedirs(TMP, exist_ok=True)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('92.246.128.94', username='root', password='kf24mP2c7KQBViNi', timeout=15)

# Download backup files locally
sftp = ssh.open_sftp()
sftp.get('/opt/hairos-bot/bot_cache.db', os.path.join(TMP, 'current_hairos.db'))
sftp.get('/tmp/hairos_backup1.db', os.path.join(TMP, 'hairos_backup1.db'))
sftp.get('/tmp/hairos_backup2.db', os.path.join(TMP, 'hairos_backup2.db'))
sftp.close()

# Check each
for label, fname in [('current', 'current_hairos.db'),
                     ('backup1 (Sep 2)', 'hairos_backup1.db'),
                     ('backup2 (Sep 2)', 'hairos_backup2.db')]:
    path = os.path.join(TMP, fname)
    try:
        db = sqlite3.connect(path)
        cats = db.execute('SELECT DISTINCT category_title FROM services').fetchall()
        count = db.execute('SELECT count(*) FROM services').fetchone()[0]
        masters = db.execute('SELECT name FROM masters').fetchall()
        print(f'{label}: {count} services, {len(masters)} masters')
        print(f'  Masters: {[m[0] for m in masters]}')
        print(f'  Service categories:')
        for c in cats:
            print(f'    - {c[0]}')
        db.close()
    except Exception as e:
        print(f'{label}: ERROR {e}')
    print()

ssh.close()
