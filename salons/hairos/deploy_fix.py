import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

sftp = ssh.open_sftp()

# Upload api.py
local_api = r'C:\Users\User\mimo\kaskad-multitenant\api.py'
remote_api = '/opt/hairos-bot/api.py'
sftp.put(local_api, remote_api)
print(f"Uploaded api.py ({os.path.getsize(local_api)} bytes)")

# Upload master_dashboard.html
local_tpl = r'C:\Users\User\mimo\kaskad-multitenant\templates\master_dashboard.html'
remote_tpl = '/opt/hairos-bot/templates/master_dashboard.html'
sftp.put(local_tpl, remote_tpl)
print(f"Uploaded master_dashboard.html ({os.path.getsize(local_tpl)} bytes)")

sftp.close()

# Restart service
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot')
stdout.channel.recv_exit_status()
err = stderr.read().decode()
if err:
    print(f"Restart stderr: {err}")
else:
    print("Service hairos-bot restarted")

# Check status
stdin, stdout, stderr = ssh.exec_command('systemctl is-active hairos-bot')
status = stdout.read().decode().strip()
print(f"Service status: {status}")

# Quick health check
import time
time.sleep(2)
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/health')
health = stdout.read().decode().strip()
print(f"Health check: {health}")

ssh.close()
print("Deploy complete!")
