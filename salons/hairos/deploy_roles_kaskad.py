import paramiko
import os
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

sftp = ssh.open_sftp()

files = [
    (r'C:\Users\User\mimo\kaskad-multitenant\api.py', '/opt/telegram-bot/api.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\db.py', '/opt/telegram-bot/db.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\master_login.html', '/opt/telegram-bot/templates/master_login.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\master_dashboard.html', '/opt/telegram-bot/templates/master_dashboard.html'),
]

for local, remote in files:
    sftp.put(local, remote)
    print(f"Kaskad: {os.path.basename(local)}")

sftp.close()

stdin, stdout, stderr = ssh.exec_command('systemctl restart crm-api telegram-bot')
stdout.channel.recv_exit_status()
print("Kaskad services restarted")

time.sleep(3)

stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8000/health')
print(f"Kaskad health: {stdout.read().decode().strip()}")

stdin, stdout, stderr = ssh.exec_command('systemctl is-active crm-api telegram-bot')
print(f"Kaskad services: {stdout.read().decode().strip()}")

ssh.close()
print("Done!")
