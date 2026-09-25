"""setup_backup.py — Настройка автобэкапов на сервере."""
import paramiko

SERVER = "92.246.128.94"
USER = "root"
PASS = "kf24mP2c7KQBViNi"

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(SERVER, username=USER, password=PASS, timeout=15)

# 1. Create backup script
backup_script = """#!/bin/bash
BACKUP_DIR=/opt/backups
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR
cp /opt/hairos-bot/bot_cache.db $BACKUP_DIR/hairos_$DATE.db
cp /opt/kaskad-bot/bot_cache.db $BACKUP_DIR/kaskad_$DATE.db
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
"""

sftp = ssh.open_sftp()
f = sftp.open("/opt/backup_all.sh", "w")
f.write(backup_script)
f.close()
sftp.close()

# Make executable and test
print("Testing backup script...")
ssh.exec_command("chmod +x /opt/backup_all.sh")
ssh.exec_command("/opt/backup_all.sh")
import time
time.sleep(2)

out = ssh.exec_command("ls -la /opt/backups/")[1].read().decode()
print(out)

# 2. Add cron job (daily at 3 AM)
print("\nSetting up cron job...")
cron_cmd = "crontab -l 2>/dev/null; echo '0 3 * * * /opt/backup_all.sh'"
stdin, stdout, stderr = ssh.exec_command("echo '0 3 * * * /opt/backup_all.sh' | crontab -")
time.sleep(1)

out = ssh.exec_command("crontab -l")[1].read().decode()
print("Crontab:")
print(out)

ssh.close()
print("Done!")
