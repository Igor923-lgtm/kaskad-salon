import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

sftp = ssh.open_sftp()
local_bot = r'C:\Users\User\mimo\kaskad-multitenant\bot.py'
remote_bot = '/opt/hairos-bot/bot.py'
sftp.put(local_bot, remote_bot)
print(f"Uploaded bot.py ({os.path.getsize(local_bot)} bytes)")
sftp.close()

# Restart polling
stdin, stdout, stderr = ssh.exec_command('systemctl restart hairos-polling')
stdout.channel.recv_exit_status()
print("Restarted hairos-polling")

import time
time.sleep(3)

# Check status
stdin, stdout, stderr = ssh.exec_command('systemctl is-active hairos-polling')
print(f"Status: {stdout.read().decode().strip()}")

# Verify edit booking exists
stdin, stdout, stderr = ssh.exec_command('grep -c "menu_edit_booking" /opt/hairos-bot/bot.py')
print(f"Edit booking: {stdout.read().decode().strip()} occurrences")

# Check bot logs
stdin, stdout, stderr = ssh.exec_command('journalctl -u hairos-polling --since 30s --no-pager | tail -5')
print(f"\nBot logs:\n{stdout.read().decode()}")

ssh.close()
print("Done!")
