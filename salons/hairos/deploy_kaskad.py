import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

sftp = ssh.open_sftp()

files = [
    (r'C:\Users\User\mimo\kaskad-multitenant\api.py', '/opt/telegram-bot/api.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\config.py', '/opt/telegram-bot/config.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\db.py', '/opt/telegram-bot/db.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\master_dashboard.html', '/opt/telegram-bot/templates/master_dashboard.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\master_login.html', '/opt/telegram-bot/templates/master_login.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\clients_page.html', '/opt/telegram-bot/templates/clients_page.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\crm_dashboard.html', '/opt/telegram-bot/templates/crm_dashboard.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\users_page.html', '/opt/telegram-bot/templates/users_page.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\_sidebar.html', '/opt/telegram-bot/templates/_sidebar.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\bookings_page.html', '/opt/telegram-bot/templates/bookings_page.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\static\manifest.json', '/opt/telegram-bot/static/manifest.json'),
    (r'C:\Users\User\mimo\kaskad-multitenant\static\icon-192.png', '/opt/telegram-bot/static/icon-192.png'),
    (r'C:\Users\User\mimo\kaskad-multitenant\static\icon-512.png', '/opt/telegram-bot/static/icon-512.png'),
    (r'C:\Users\User\mimo\kaskad-multitenant\salons\kaskad\.env', '/opt/telegram-bot/salons/kaskad/.env'),
]

for local, remote in files:
    sftp.put(local, remote)
    print(f"Uploaded {os.path.basename(local)} ({os.path.getsize(local)} bytes)")

sftp.close()

# Restart Kaskad services
stdin, stdout, stderr = ssh.exec_command('systemctl restart crm-api telegram-bot')
stdout.channel.recv_exit_status()
print("Services restarted")

import time
time.sleep(3)

# Health check
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8000/health')
print(f"Health: {stdout.read().decode().strip()}")

# Test bookings grouped (need to login first)
stdin, stdout, stderr = ssh.exec_command(f'curl -s -c /tmp/kaskad_cookies.txt -L -d "password={os.environ["QA_KASKAD_PW"]}" http://localhost:8000/login -o /dev/null -w "%{{http_code}}"')
print(f"Login: HTTP {stdout.read().decode().strip()}")

stdin, stdout, stderr = ssh.exec_command('curl -s -b /tmp/kaskad_cookies.txt http://localhost:8000/api/bookings/grouped | head -c 200')
print(f"Grouped: {stdout.read().decode().strip()}")

# Check services
stdin, stdout, stderr = ssh.exec_command('systemctl is-active crm-api telegram-bot')
print(f"Services: {stdout.read().decode().strip()}")

ssh.close()
print("Done!")
