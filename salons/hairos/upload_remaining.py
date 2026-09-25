import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

sftp = ssh.open_sftp()

files = [
    (r'C:\Users\User\mimo\kaskad-multitenant\db.py', '/opt/hairos-bot/db.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\salons\hairos\price_data.py', '/opt/hairos-bot/price_data.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\config.py', '/opt/hairos-bot/config.py'),
]

for local, remote in files:
    sftp.put(local, remote)
    print(f"Uploaded {os.path.basename(local)} ({os.path.getsize(local)} bytes)")

sftp.close()

# Restart both services
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot hairos-polling')
stdout.channel.recv_exit_status()
print("Services restarted")

import time
time.sleep(3)

# Final verification
stdin, stdout, stderr = ssh.exec_command('systemctl is-active hairos-bot hairos-polling')
statuses = stdout.read().decode().strip()
print(f"Services: {statuses}")

stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/health')
print(f"Health: {stdout.read().decode().strip()}")

ssh.close()
print("All done!")
