import os as _os, sys as _sys
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "..")))
import deploy_secrets
import paramiko
import os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('94.141.98.224', username='root', password=deploy_secrets.PASS_HAIROS_OLD, timeout=15)

sftp = ssh.open_sftp()

# Check what's in /opt/telegram-bot
stdin, stdout, stderr = ssh.exec_command('ls /opt/telegram-bot/')
print("Files:", stdout.read().decode())

# Check if templates dir exists
stdin, stdout, stderr = ssh.exec_command('ls /opt/telegram-bot/templates/ 2>/dev/null')
print("Templates:", stdout.read().decode())

sftp.close()
ssh.close()
