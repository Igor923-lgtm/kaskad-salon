import paramiko, os, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)
sftp = ssh.open_sftp()

files = [
    (r'C:\Users\User\mimo\kaskad-multitenant\api.py', '/opt/hairos-bot/api.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\master_dashboard.html', '/opt/hairos-bot/templates/master_dashboard.html'),
    (r'C:\Users\User\mimo\kaskad-multitenant\api.py', '/opt/telegram-bot/api.py'),
    (r'C:\Users\User\mimo\kaskad-multitenant\templates\master_dashboard.html', '/opt/telegram-bot/templates/master_dashboard.html'),
]

for local, remote in files:
    sftp.put(local, remote)
    print(f"OK: {os.path.basename(local)} -> {remote.split('/')[2]}")

sftp.close()

stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot hairos-polling crm-api telegram-bot')
stdout.channel.recv_exit_status()
print("All restarted")

time.sleep(3)
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8005/health')
print(f"Hairos: {stdout.read().decode().strip()}")
stdin, stdout, stderr = ssh.exec_command('curl -s http://localhost:8000/health')
print(f"Kaskad: {stdout.read().decode().strip()}")

ssh.close()
print("Done!")
