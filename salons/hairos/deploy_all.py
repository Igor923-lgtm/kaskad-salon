import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

sftp = ssh.open_sftp()

files = [
    (r'C:\Users\User\mimo\kaskad-multitenant\api.py', '/opt/hairos-bot/api.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\config.py', '/opt/hairos-bot/config.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\db.py', '/opt/hairos-bot/db.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\master_dashboard.html', '/opt/hairos-bot/templates/master_dashboard.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\master_login.html', '/opt/hairos-bot/templates/master_login.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\clients_page.html', '/opt/hairos-bot/templates/clients_page.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\crm_dashboard.html', '/opt/hairos-bot/templates/crm_dashboard.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\users_page.html', '/opt/hairos-bot/templates/users_page.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\_sidebar.html', '/opt/hairos-bot/templates/_sidebar.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\static\manifest.json', '/opt/hairos-bot/static/manifest.json'),
    (r'C:\Users\User\mimo\kaskad-multitenant\static\icon-192.png', '/opt/hairos-bot/static/icon-192.png'),
    (r'C:\Users\User\mimo\kaskad-multitenant\static\icon-512.png', '/opt/hairos-bot/static/icon-512.png'),
    (r'C:\Users\User\mimo\kaskad-multitenant\salons\hairos\.env', '/opt/hairos-bot/salons/hairos/.env'),
]

for local, remote in files:
    sftp.put(local, remote)
    print(f"Uploaded {os.path.basename(local)} ({os.path.getsize(local)} bytes)")

sftp.close()

# Restart services
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot hairos-polling')
stdout.channel.recv_exit_status()
print("Services restarted")

import time
time.sleep(2)

# Health check
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/health')
print(f"Health: {stdout.read().decode().strip()}")

# Test new endpoints
stdin, stdout, stderr = ssh.exec_command('curl -s -o /dev/null -w "%{http_code}" http://localhost:8005/api/bookings/grouped')
print(f"Bookings grouped: HTTP {stdout.read().decode().strip()}")

# Check bot is running
stdin, stdout, stderr = ssh.exec_command('systemctl is-active hairos-polling hairos-bot')
print(f"Services: {stdout.read().decode().strip()}")

ssh.close()
print("Deploy complete!")
