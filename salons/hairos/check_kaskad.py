import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password='25ELkJTNxhwCC7vF', timeout=15)

sftp = ssh.open_sftp()

# Check what's in /opt/telegram-bot
stdin, stdout, stderr = ssh.exec_command('ls /opt/telegram-bot/')
print("Files:", stdout.read().decode())

# Check if templates dir exists
stdin, stdout, stderr = ssh.exec_command('ls /opt/telegram-bot/templates/ 2>/dev/null')
print("Templates:", stdout.read().decode())

sftp.close()
ssh.close()
