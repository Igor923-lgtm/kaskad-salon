import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

sftp = ssh.open_sftp()

# Hairos
files_hairos = [
    (r'C:\Users\User\mimo\kaskad-multitenant\api.py', '/opt/hairos-bot/api.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\clients_page.html', '/opt/hairos-bot/templates/clients_page.html'),
]

# Kaskad
files_kaskad = [
    (r'C:\Users\User\mimo\kaskad-multitenant\api.py', '/opt/telegram-bot/api.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\clients_page.html', '/opt/telegram-bot/templates/clients_page.html'),
]

for local, remote in files_hairos:
    sftp.put(local, remote)
    print(f"Hairos: {os.path.basename(local)}")

for local, remote in files_kaskad:
    sftp.put(local, remote)
    print(f"Kaskad: {os.path.basename(local)}")

sftp.close()

# Restart both
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot crm-api')
stdout.channel.recv_exit_status()
print("Services restarted")

import time
time.sleep(3)

# Health checks
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/health')
print(f"Hairos: {stdout.read().decode().strip()}")
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8000/health')
print(f"Kaskad: {stdout.read().decode().strip()}")

ssh.close()
print("Done!")
