import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

sftp = ssh.open_sftp()
sftp.put(r'C:\Users\User\mimo\kaskad-multitenant\api.py', '/opt/hairos-bot/api.py')
sftp.close()
print("Uploaded api.py")

stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-bot')
stdout.channel.recv_exit_status()
print("Restarted hairos-bot")

time.sleep(3)

# Check status
stdin, stdout, stderr = ssh.exec_command('systemctl is-active hairos-bot')
print(f"Status: {stdout.read().decode().strip()}")

# Health check
stdin, stdout, stderr = ssh.exec_command('curl -s -m 5 http://localhost:8005/health')
print(f"Health: {stdout.read().decode().strip()}")

# Test bookings grouped
stdin, stdout, stderr = ssh.exec_command('curl -s -m 5 http://localhost:8005/api/bookings/grouped | head -c 200')
print(f"Grouped: {stdout.read().decode().strip()}")

ssh.close()
