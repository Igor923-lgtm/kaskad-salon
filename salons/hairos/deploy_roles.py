import paramiko
import os
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

sftp = ssh.open_sftp()

files = [
    (r'C:\Users\User\mimo\kaskad-multitenant\api.py', '/opt/hairos-bot/api.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\db.py', '/opt/hairos-bot/db.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\master_login.html', '/opt/hairos-bot/templates/master_login.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\master_dashboard.html', '/opt/hairos-bot/templates/master_dashboard.html'),
]

for local, remote in files:
    sftp.put(local, remote)
    print(f"Uploaded {os.path.basename(local)} ({os.path.getsize(local)} bytes)")

sftp.close()

# Restart
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot hairos-polling')
stdout.channel.recv_exit_status()
print("Services restarted")

time.sleep(3)

# Health check
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/health')
print(f"Health: {stdout.read().decode().strip()}")

# Test users API (need to login first)
stdin, stdout, stderr = ssh.exec_command('curl -s -c /tmp/h.txt -L -d "password=hairos2026" http://localhost:8005/login -o /dev/null')
stdout.read()

# Test master auth request
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/api/users?token=test 2>&1 | head -c 100')
print(f"Users API: {stdout.read().decode().strip()}")

# Check services
stdin, stdout, stderr = ssh.exec_command('systemctl is-active hairos-bot hairos-polling')
print(f"Services: {stdout.read().decode().strip()}")

ssh.close()
print("Done!")
