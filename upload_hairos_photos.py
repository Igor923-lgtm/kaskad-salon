import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('92.246.128.94', username='root', password='kf24mP2c7KQBViNi', timeout=15)

sftp = ssh.open_sftp()
local = r'C:\Users\User\mimo\kaskad-multitenant\works_photos'

# Root photos
for f in os.listdir(local):
    fp = os.path.join(local, f)
    if os.path.isfile(fp) and f.lower().endswith(('.jpg', '.png', '.jpeg')):
        sftp.put(fp, f'/opt/hairos-bot/works_photos/{f}')
        print(f'  {f}')

# Subdirectory photos
for sub in os.listdir(local):
    subp = os.path.join(local, sub)
    if os.path.isdir(subp):
        ssh.exec_command(f'mkdir -p /opt/hairos-bot/works_photos/{sub}')
        for f in os.listdir(subp):
            fp = os.path.join(subp, f)
            if os.path.isfile(fp) and f.lower().endswith(('.jpg', '.png', '.jpeg')):
                sftp.put(fp, f'/opt/hairos-bot/works_photos/{sub}/{f}')
                print(f'  {sub}/{f}')

sftp.close()
ssh.close()
print('Done')
